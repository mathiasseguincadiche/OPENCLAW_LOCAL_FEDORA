"""Approvals typed in the chat: a single-use phrase that the model can neither write nor see.

The bridge generates a short code and shows it in a reply of its own, which is never sent to a
model (see ``chat_projects.sanitize_history``). The phrase ``approuver <action> <CODE>`` counts
only if it is the whole last message of the user, the code matches a record kept on disk, it is
not expired, it has not been used, and what is approved still has the same SHA-256 as when the
code was issued. The record lives in ``state/chat-approvals`` and is removed on first use.
"""

from __future__ import annotations

import fcntl
import os
import re
import secrets
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from clawfedora.project_common import read_json, validate_project_id, write_json

TTL_SECONDS = 15 * 60
MAX_FAILURES = 5
MAX_PENDING = 20
# No 0/O/1/I/L: the code is read on screen and typed by hand.
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 4
ACTIONS = ("proposition", "creation", "analyse", "plan", "revision", "livraison")
# Scope of an approval that belongs to no project yet (creating one).
GLOBAL = "_global"

_PHRASE = re.compile(
    rf"approuver ([a-z]{{3,20}}) ([a-z0-9]{{{CODE_LENGTH}}})", re.IGNORECASE
)


def _clock() -> float:
    return time.time()


@dataclass(frozen=True)
class Pending:
    code: str
    action: str
    target: str
    digest: str
    summary: str
    expires_at: float
    payload: dict[str, Any] | None = None

    def phrase(self) -> str:
        return phrase(self.action, self.code)


@dataclass(frozen=True)
class Outcome:
    ok: bool
    reason: str
    pending: Pending | None = None


def phrase(action: str, code: str) -> str:
    return f"approuver {action} {code}"


def parse_phrase(text: str) -> tuple[str, str] | None:
    """(action, CODE) when the whole message is an approval phrase, else None."""
    match = _PHRASE.fullmatch(text.strip())
    if match is None or match.group(1).lower() not in ACTIONS:
        return None
    return match.group(1).lower(), match.group(2).upper()


def _store(runtime: Path) -> Path:
    directory = runtime / "state/chat-approvals"
    for part in (runtime / "state", directory):
        if part.is_symlink():
            raise ValueError("dossier d'approbations lié interdit")
    directory.mkdir(parents=True, exist_ok=True)
    return directory


@contextmanager
def _locked(runtime: Path, project_id: str) -> Iterator[Path]:
    """The records of one project, under an exclusive lock: a code cannot be used twice."""
    if project_id != GLOBAL:
        project_id = validate_project_id(project_id)
    directory = _store(runtime)
    lock = directory / f"{project_id}.lock"
    fd = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield directory / f"{project_id}.json"
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _load(path: Path, now: float) -> dict[str, Any]:
    if not path.is_file():
        return {"pending": {}, "failures": []}
    value = read_json(path)
    pending = value.get("pending")
    failures = value.get("failures")
    if not isinstance(pending, dict) or not isinstance(failures, list):
        return {"pending": {}, "failures": []}
    # Expired records and old failures are dropped whenever the file is read.
    return {
        "pending": {
            code: item
            for code, item in pending.items()
            if isinstance(item, dict) and float(item.get("expires_at", 0)) > now
        },
        "failures": [t for t in failures if isinstance(t, int | float) and now - t < TTL_SECONDS],
    }


def _save(path: Path, state: dict[str, Any]) -> None:
    write_json(path, state)
    path.chmod(0o600)


def _pending(code: str, item: dict[str, Any]) -> Pending:
    return Pending(
        code=code,
        action=str(item["action"]),
        target=str(item["target"]),
        digest=str(item["digest"]),
        summary=str(item.get("summary", "")),
        expires_at=float(item["expires_at"]),
        payload=item["payload"] if isinstance(item.get("payload"), dict) else None,
    )


def issue(
    runtime: Path,
    project_id: str,
    action: str,
    target: str,
    digest: str,
    summary: str,
    *,
    payload: dict[str, Any] | None = None,
    now: Callable[[], float] = _clock,
) -> Pending:
    """A new code for (project, action, target). An older code for the same target is revoked."""
    if action not in ACTIONS:
        raise ValueError("action à approuver inconnue")
    moment = now()
    with _locked(runtime, project_id) as path:
        state = _load(path, moment)
        pending = {
            code: item
            for code, item in state["pending"].items()
            if (item["action"], item["target"]) != (action, target)
        }
        if len(pending) >= MAX_PENDING:
            raise ValueError("trop d'approbations en attente: attendre leur expiration")
        code = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))
        while code in pending:
            code = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))
        pending[code] = {
            "action": action,
            "target": target,
            "digest": digest,
            "summary": summary[:300],
            "expires_at": moment + TTL_SECONDS,
            **({"payload": payload} if payload is not None else {}),
        }
        _save(path, {"pending": pending, "failures": state["failures"]})
        return _pending(code, pending[code])


def consume(
    runtime: Path,
    project_id: str,
    action: str,
    code: str,
    current_digest: Callable[[Pending], str | None],
    *,
    now: Callable[[], float] = _clock,
) -> Outcome:
    """Use a code once. ``current_digest`` recomputes what is being approved right now."""
    moment = now()
    with _locked(runtime, project_id) as path:
        state = _load(path, moment)
        if len(state["failures"]) >= MAX_FAILURES:
            _save(path, {"pending": {}, "failures": state["failures"]})
            return Outcome(False, "blocked")
        item = state["pending"].get(code)
        if item is None or item["action"] != action:
            state["failures"].append(moment)
            _save(path, state)
            return Outcome(False, "unknown")
        found = _pending(code, item)
        del state["pending"][code]
        # Spent before anything else is checked: a changed target never reuses its code.
        _save(path, state)
        if current_digest(found) != found.digest:
            return Outcome(False, "changed", found)
        return Outcome(True, "ok", found)


def pending_for(
    runtime: Path, project_id: str, *, now: Callable[[], float] = _clock
) -> list[Pending]:
    with _locked(runtime, project_id) as path:
        state = _load(path, now())
        return [_pending(code, item) for code, item in state["pending"].items()]


def revoke_all(runtime: Path, project_id: str) -> None:
    with _locked(runtime, project_id) as path:
        if path.is_file():
            _save(path, {"pending": {}, "failures": []})
