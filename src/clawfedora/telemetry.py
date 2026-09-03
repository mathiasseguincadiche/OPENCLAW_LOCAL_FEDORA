from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from clawfedora.core_config import core_contract

RESERVED_FIELDS = {"event", "at"}


@dataclass(frozen=True)
class TelemetryEvent:
    event: str
    at: str
    fields: dict[str, Any]

    def payload(self) -> dict[str, Any]:
        return {**self.fields, "event": self.event, "at": self.at}


def _policy(repo_root: Path) -> dict[str, Any]:
    return core_contract(repo_root, "telemetry_policy.yaml")


def _confined_path(runtime_root: Path, relative: str) -> Path:
    value = Path(relative)
    if not relative or value.is_absolute() or ".." in value.parts:
        raise ValueError(f"telemetry: relative_path interdit: {relative}")
    runtime = runtime_root.resolve()
    target = (runtime / value).resolve(strict=False)
    if target == runtime or runtime not in target.parents:
        raise ValueError(f"telemetry: chemin hors runtime: {relative}")
    return target


def _event_path(repo_root: Path, runtime_root: Path) -> Path:
    policy = _policy(repo_root)
    retention = policy.get("retention", {})
    if not isinstance(retention, dict):
        raise ValueError("telemetry: retention invalide")
    relative = str(retention.get("relative_path", ""))
    return _confined_path(runtime_root, relative)


def _validate_fields(repo_root: Path, event: str, fields: dict[str, Any]) -> None:
    policy = _policy(repo_root)
    if policy.get("local_only") is not True:
        raise ValueError("telemetry: local_only=true requis")
    allowed = {str(item) for item in policy.get("allowed_fields", [])}
    forbidden = {str(item).casefold() for item in policy.get("forbidden_content", [])}
    if not event.strip():
        raise ValueError("telemetry: event vide")
    reserved = sorted(set(fields) & RESERVED_FIELDS)
    if reserved:
        raise ValueError(f"telemetry: champs réservés interdits: {reserved}")
    unknown = sorted(set(fields) - allowed)
    if unknown:
        raise ValueError(f"telemetry: champs non autorisés: {unknown}")
    for key, value in fields.items():
        lowered_key = key.casefold()
        text = str(value).casefold()
        if any(marker in lowered_key for marker in forbidden):
            raise ValueError(f"telemetry: champ interdit: {key}")
        sensitive_patterns = {"bearer "}
        for marker in forbidden:
            sensitive_patterns.add(f"{marker}=")
            sensitive_patterns.add(f"{marker}:")
        if any(pattern in text for pattern in sensitive_patterns):
            raise ValueError("telemetry: contenu sensible détecté")


def emit_event(
    repo_root: Path,
    runtime_root: Path,
    event: str,
    **fields: Any,
) -> Path:
    _validate_fields(repo_root, event, fields)
    path = _event_path(repo_root, runtime_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = TelemetryEvent(
        event=event.strip(),
        at=datetime.now(UTC).isoformat(),
        fields=fields,
    ).payload()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def read_events(repo_root: Path, runtime_root: Path, *, limit: int = 100) -> list[dict[str, Any]]:
    if limit < 1:
        raise ValueError("telemetry: limit doit être >= 1")
    path = _event_path(repo_root, runtime_root)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        value = json.loads(line)
        if isinstance(value, dict):
            rows.append(value)
    return rows
