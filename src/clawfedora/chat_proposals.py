"""Documents written in the chat, kept in the project as proposals until the user accepts them.

A proposal is the text of a model answer, saved by the ``!garder`` command. It is data, not a
deliverable: accepting it adds a note to ``context/chat/notes`` that the roles and the chat can
read, with its origin. Nothing here touches ``intake``, ``deliverables`` or the project status,
so the independent audit and the packaging of the atelier are unchanged; turning a note into a
deliverable goes through a task and its audit (a later step of the plan).
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from clawfedora.project_common import assert_no_symlinks, now, read_json, write_json

PROPOSALS = "context/chat/proposals"
NOTES = "context/chat/notes"
MAX_TEXT_BYTES = 100_000
MAX_PROPOSALS = 60
MAX_TITLE = 80
STATUSES = ("pending", "accepted", "refused")


def _folder(project: Path, relative: str) -> Path:
    path = project / relative
    for part in (project / "context", project / "context/chat", path):
        if part.is_symlink():
            raise ValueError("dossier de propositions lié interdit")
    return path


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def clean_title(title: str, text: str) -> str:
    """A short single-line title: the one given, else the first line of the text."""
    candidate = title.strip()
    if not candidate:
        candidate = next((line for line in text.splitlines() if line.strip()), "")
    candidate = re.sub(r"[#*`|>\[\]\r\n]+", " ", candidate)
    candidate = re.sub(r"\s+", " ", candidate).strip()
    return candidate[:MAX_TITLE] or "Sans titre"


def _path(project: Path, number: int) -> Path:
    if not 1 <= number <= 999:
        raise ValueError("numéro de proposition invalide")
    return _folder(project, PROPOSALS) / f"proposition-{number:03d}.json"


def load_all(project: Path) -> list[dict[str, Any]]:
    folder = _folder(project, PROPOSALS)
    if not folder.is_dir():
        return []
    rows = []
    for path in sorted(folder.glob("proposition-*.json"))[: MAX_PROPOSALS + 10]:
        if path.is_symlink():
            continue
        try:
            record = read_json(path)
        except (OSError, ValueError):
            continue
        if (
            isinstance(record.get("number"), int)
            and record.get("status") in STATUSES
            and isinstance(record.get("text"), str)
        ):
            rows.append(record)
    return rows


def get(project: Path, number: int) -> dict[str, Any]:
    path = _path(project, number)
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"proposition {number} introuvable (`!propositions`)")
    record = read_json(path)
    if record.get("status") not in STATUSES or not isinstance(record.get("text"), str):
        raise ValueError(f"proposition {number} illisible")
    return record


def save(project: Path, text: str, title: str, route: str, model: str) -> dict[str, Any]:
    """Store a model answer as a pending proposal. The caller holds the worker lock."""
    body = text.strip()
    if not body:
        raise ValueError("aucune réponse à garder: demandez d'abord le document au rôle")
    if len(body.encode()) > MAX_TEXT_BYTES:
        raise ValueError(f"réponse trop longue pour une proposition ({MAX_TEXT_BYTES // 1000} Ko)")
    assert_no_symlinks(project, label="projet")
    rows = load_all(project)
    if len(rows) >= MAX_PROPOSALS:
        raise ValueError("trop de propositions: en refuser quelques-unes d'abord")
    number = max((r["number"] for r in rows), default=0) + 1
    if number > 999:
        raise ValueError("trop de propositions dans ce projet")
    record = {
        "number": number,
        "title": clean_title(title, body),
        "created_at": now(),
        "route": route if route in {"local", "cloud"} else "local",
        "model": re.sub(r"[^\w .:/·()+-]", "", model)[:60],
        "sha256": digest(body),
        "size": len(body.encode()),
        "status": "pending",
        "text": body,
    }
    write_json(_path(project, number), record)
    return record


def pending_digest(project: Path, number: int) -> str | None:
    """What an approval of this proposal covers now: its hash, or None when it can't be approved."""
    try:
        record = get(project, number)
    except (OSError, ValueError):
        return None
    if record["status"] != "pending" or digest(record["text"]) != record.get("sha256"):
        return None
    return str(record["sha256"])


def refuse(project: Path, number: int) -> dict[str, Any]:
    record = get(project, number)
    if record["status"] != "pending":
        raise ValueError(f"la proposition {number} est déjà décidée")
    record.update(status="refused", decided_at=now())
    write_json(_path(project, number), record)
    return record


def accept(project: Path, number: int, expected_sha256: str) -> dict[str, Any]:
    """Add the proposal to the project notes. Only called after a valid approval phrase."""
    record = get(project, number)
    if record["status"] != "pending":
        raise ValueError(f"la proposition {number} est déjà décidée")
    if digest(record["text"]) != expected_sha256 or record.get("sha256") != expected_sha256:
        raise ValueError("la proposition a changé depuis le code: rien n'est accepté")
    notes = _folder(project, NOTES)
    notes.mkdir(parents=True, exist_ok=True)
    header = (
        f"<!-- Note acceptée par l'utilisateur depuis le chat. Texte écrit par un modèle "
        f"({record['route']}, {record['model']}), non vérifié. proposition {number}, "
        f"sha256 {expected_sha256} -->\n\n"
    )
    target = notes / f"note-{number:03d}.md"
    target.write_text(header + record["text"] + "\n", encoding="utf-8")
    record.update(status="accepted", decided_at=now(), note=target.relative_to(project).as_posix())
    write_json(_path(project, number), record)
    return record


def accepted_notes(project: Path, limit: int = 10) -> list[dict[str, Any]]:
    rows = [r for r in load_all(project) if r["status"] == "accepted"]
    return [
        {
            "number": r["number"],
            "title": r["title"],
            "file": r.get("note", ""),
            "excerpt": r["text"][:300],
        }
        for r in rows[-limit:]
    ]
