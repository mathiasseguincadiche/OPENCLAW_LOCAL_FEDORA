"""Runtime state of the cloud route: the local gateway token and the activation record.

The cloud is off unless an activation record proves that every control required by
``config/core/cloud_policy.yaml`` was verified. Nothing here talks to the network.
"""

from __future__ import annotations

import json
import os
import secrets
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from clawfedora.core_config import core_contract

CLOUD_STATE = "state/cloud"
TOKEN_FILE = "gateway.token"
ACTIVATION_FILE = "activation.json"


def _directory(runtime: Path) -> Path:
    return runtime / CLOUD_STATE


def ensure_gateway_token(runtime: Path) -> str:
    """Local token OpenClaw presents to the gateway. It is not the upstream key.

    OpenClaw resolves the secrets of every configured provider before any turn, so a missing
    token would also break local turns: the runtime environment always defines it. Outside a
    managed runtime (no ``state`` directory) nothing is written and a throwaway value is used.
    """
    if not (runtime / "state").is_dir():
        return secrets.token_urlsafe(32)
    directory = _directory(runtime)
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(0o700)
    path = directory / TOKEN_FILE
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        fd = os.open(path, flags, 0o600)
    except FileExistsError:
        token = path.read_text(encoding="utf-8").strip()
        if len(token) >= 32:
            return token
        raise ValueError("jeton cloud invalide: supprimer le fichier pour le régénérer") from None
    token = secrets.token_urlsafe(32)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(token + "\n")
    return token


def read_activation(runtime: Path) -> dict[str, Any]:
    path = _directory(runtime) / ACTIVATION_FILE
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def write_activation(runtime: Path, verified: Mapping[str, str]) -> Path:
    """Record an activation. Only the activation command, after its self-tests, calls this."""
    directory = _directory(runtime)
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(0o700)
    path = directory / ACTIVATION_FILE
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "enabled": True,
                "verified": dict(verified),
                "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.chmod(0o600)
    temporary.replace(path)
    return path


def revoke_activation(runtime: Path) -> None:
    """Switch the cloud off: the single rollback."""
    (_directory(runtime) / ACTIVATION_FILE).unlink(missing_ok=True)


def cloud_status(runtime: Path, repo_root: Path) -> tuple[bool, str]:
    """(ready, reason). Ready only if the policy allows it and every control is verified."""
    policy = core_contract(repo_root, "cloud_policy.yaml")["policy"]
    required = set(policy.get("requires", []))
    if not required:
        return False, "politique cloud sans contrôles requis"
    record = read_activation(runtime)
    if record.get("enabled") is not True:
        return False, "cloud non activé"
    verified = record.get("verified")
    if not isinstance(verified, dict):
        return False, "activation sans preuve des contrôles"
    missing = sorted(name for name in required if not str(verified.get(name, "")).strip())
    if missing:
        return False, "contrôles non vérifiés: " + ", ".join(missing)
    return True, "cloud activé"


def require_cloud_ready(runtime: Path, repo_root: Path) -> None:
    ready, reason = cloud_status(runtime, repo_root)
    if not ready:
        raise ValueError(f"route cloud refusée: {reason}")


def recent_events(runtime: Path, since: float) -> list[dict[str, Any]]:
    """Gateway decisions recorded since ``since`` (epoch seconds). They hold no content."""
    path = _directory(runtime) / "events.jsonl"
    cutoff = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(since)))
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-200:]
    except OSError:
        return []
    result: list[dict[str, Any]] = []
    for line in lines:
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict) and str(record.get("at", "")) >= cutoff:
            result.append(record)
    return result
