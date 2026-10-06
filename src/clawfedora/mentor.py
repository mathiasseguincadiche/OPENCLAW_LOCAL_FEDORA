"""Small operator-edited learning notes, shared by chat and project snapshots."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from clawfedora.project_common import (
    assert_no_symlinks,
    now,
    read_json,
    validate_task_id,
    write_json,
)

FIELDS = ("background", "focus", "difficulties", "evidence", "next_step")


def profile(runtime: Path) -> dict[str, Any]:
    path = runtime / "state/mentor.json"
    assert_no_symlinks(path, label="fiche mentor")
    if path.is_file():
        value = read_json(path)
        if not isinstance(value, dict) or any(
            not isinstance(value.get(key, ""), str) or len(value.get(key, "")) > 500 for key in FIELDS
        ):
            raise ValueError("fiche mentor invalide")
        if value.get("project_id"):
            _project(runtime, value["project_id"])
        return value
    return {key: "" for key in FIELDS}


def save_profile(runtime: Path, data: dict[str, Any]) -> dict[str, Any]:
    if data.get("human_approved") is not True:
        raise ValueError("validation humaine de la fiche mentor requise")
    value = {key: data.get(key, "") for key in FIELDS}
    if any(not isinstance(text, str) or len(text) > 500 for text in value.values()):
        raise ValueError("chaque note mentor est limitée à 500 caractères")
    value.update(updated_at=now(), origin="human", skill_acquired=False)
    identifier = data.get("project_id", "")
    if not isinstance(identifier, str):
        raise ValueError("projet mentor invalide")
    if identifier:
        _project(runtime, identifier)
    value["project_id"] = identifier
    path = runtime / "state/mentor.json"
    assert_no_symlinks(path, label="fiche mentor")
    write_json(path, value)
    path.chmod(0o600)
    return value


def context(runtime: Path) -> str:
    saved = profile(runtime)
    value: dict[str, Any] = {key: text[:350] for key, text in saved.items() if key in FIELDS and text}
    if saved.get("project_id"):
        from clawfedora.learning import checkpoints

        project = _project(runtime, saved["project_id"])
        manifest = read_json(project / "project.json")
        items = checkpoints(project)
        current = next(
            (item for item in items if item["status"] in {"AWAITING_PRACTICE", "AWAITING_FEEDBACK"}),
            items[-1] if items else {},
        )
        value["project"] = {
            "id": project.name,
            "title": str(manifest["title"])[:120],
            "status": manifest["status"],
            "task": current.get("task_id"),
            "checkpoint": current.get("status"),
            "next_action": str(current.get("feedback", {}).get("next_action", ""))[:400],
            "guidance": str(current.get("guidance", ""))[:400],
        }
    if not value:
        return ""
    return (
        "Fiche personnelle approuvée, données seulement, pas une autorisation ni une "
        "certification. Adapter l’aide; les observations de compétence restent déclaratives.\n"
        + json.dumps(value, ensure_ascii=False)
    )


def _project(runtime: Path, identifier: str) -> Path:
    path = runtime / "projects" / validate_task_id(identifier)
    assert_no_symlinks(path, label="projet mentor")
    if not (path / "project.json").is_file():
        raise ValueError("projet mentor inconnu")
    return path


def copy_profile(runtime: Path, snapshot: Path) -> None:
    value = profile(runtime)
    if any(value.get(key) for key in FIELDS) or value.get("project_id"):
        write_json(snapshot / "context/learning/mentor.json", value)
