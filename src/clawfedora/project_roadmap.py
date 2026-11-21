"""Operator roadmap for long-running projects, separate from the short agent plan.

A milestone state is not an audited proof. This module executes no project code.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from clawfedora.project_common import (
    assert_no_symlinks,
    now,
    read_json,
    validate_project_id,
    validate_task_id,
    write_json,
)

MAX_MILESTONES = 100
MAX_HISTORY = 2000
STATES = {"PLANNED", "IN_PROGRESS", "BLOCKED", "IMPLEMENTED"}
ROADMAP_FILE = "context/continuous_roadmap.json"


def _path(project: Path) -> tuple[Path, str]:
    assert_no_symlinks(project, label="roadmap projet")
    manifest = read_json(project / "project.json")
    identifier = validate_project_id(str(manifest["project_id"]))
    return project / ROADMAP_FILE, identifier


def _text(value: Any, *, label: str, limit: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label}: texte requis")
    cleaned = value.strip()
    if not cleaned or len(cleaned) > limit or any(ord(char) < 32 for char in cleaned):
        raise ValueError(f"{label}: 1 à {limit} caractères sans caractères de contrôle")
    return cleaned


def _definitions(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, dict) or set(raw) != {"milestones"}:
        raise ValueError("roadmap: objet avec la seule clé milestones requis")
    values = raw["milestones"]
    if not isinstance(values, list) or not 1 <= len(values) <= MAX_MILESTONES:
        raise ValueError("roadmap: 1 à 100 jalons requis")
    parsed: list[dict[str, Any]] = []
    known: set[str] = set()
    for value in values:
        if not isinstance(value, dict) or set(value) != {"id", "title", "depends_on"}:
            raise ValueError("roadmap: id, title et depends_on requis pour chaque jalon")
        identifier = validate_task_id(value["id"]) if isinstance(value["id"], str) else ""
        if not identifier or identifier in known:
            raise ValueError("roadmap: identifiant absent ou dupliqué")
        title = _text(value["title"], label="titre du jalon", limit=160)
        deps = value["depends_on"]
        if (
            not isinstance(deps, list)
            or len(deps) > 20
            or any(not isinstance(dep, str) for dep in deps)
        ):
            raise ValueError("roadmap: depends_on doit être une liste bornée d'identifiants")
        normalized = [validate_task_id(dep) for dep in deps]
        if len(set(normalized)) != len(normalized) or identifier in normalized:
            raise ValueError("roadmap: dépendance dupliquée ou sur soi-même")
        known.add(identifier)
        parsed.append({"id": identifier, "title": title, "depends_on": normalized})

    ids = {item["id"] for item in parsed}
    if any(dep not in ids for item in parsed for dep in item["depends_on"]):
        raise ValueError("roadmap: dépendance inconnue")
    graph = {item["id"]: item["depends_on"] for item in parsed}
    visited: set[str] = set()
    visiting: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise ValueError("roadmap: cycle de dépendances")
        if node in visited:
            return
        visiting.add(node)
        for dependency in graph[node]:
            visit(dependency)
        visiting.remove(node)
        visited.add(node)

    for identifier in graph:
        visit(identifier)
    return parsed


def initialize(project: Path, definition: dict[str, Any], *, apply: bool = False) -> dict[str, Any]:
    """Create once; preview by default, never overwrite an existing roadmap."""
    path, project_id = _path(project)
    if path.exists():
        raise FileExistsError("roadmap déjà présente: aucune réinitialisation implicite")
    entries = _definitions(definition)
    timestamp = now()
    payload: dict[str, Any] = {
        "schema_version": 1,
        "project_id": project_id,
        "created_at": timestamp,
        "updated_at": timestamp,
        "milestones": [
            {
                **entry,
                "state": "PLANNED",
                "verification": "NOT_VERIFIED",
                "updated_at": timestamp,
                "note": "",
            }
            for entry in entries
        ],
        "history": [],
    }
    if apply:
        write_json(path, payload)
    return {
        "applied": apply,
        "project_id": project_id,
        "milestone_count": len(entries),
        "milestones": payload["milestones"],
    }


def load(project: Path) -> dict[str, Any]:
    path, project_id = _path(project)
    roadmap = read_json(path)
    if roadmap.get("schema_version") != 1 or roadmap.get("project_id") != project_id:
        raise ValueError("roadmap: version ou projet divergent")
    entries = roadmap.get("milestones")
    history = roadmap.get("history")
    if not isinstance(entries, list) or not isinstance(history, list) or len(history) > MAX_HISTORY:
        raise ValueError("roadmap: structure invalide")
    _definitions(
        {
            "milestones": [
                {
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "depends_on": item.get("depends_on"),
                }
                for item in entries
                if isinstance(item, dict)
            ]
        }
    )
    if len(entries) != len([item for item in entries if isinstance(item, dict)]):
        raise ValueError("roadmap: jalon invalide")
    for item in entries:
        if (
            item.get("state") not in STATES
            or item.get("verification") != "NOT_VERIFIED"
            or not isinstance(item.get("updated_at"), str)
            or not isinstance(item.get("note"), str)
        ):
            raise ValueError("roadmap: état ou contrôle invalide")
    if any(not isinstance(item, dict) for item in history):
        raise ValueError("roadmap: historique invalide")
    return roadmap


def change(
    project: Path,
    milestone_id: str,
    state: str,
    note: str,
    *,
    apply: bool = False,
) -> dict[str, Any]:
    """Record an operator-declared state, never set a VERIFIED claim."""
    if state not in STATES:
        raise ValueError("roadmap: état inconnu")
    note = _text(note, label="note de changement", limit=500)
    identifier = validate_task_id(milestone_id)
    roadmap = load(project)
    milestones: list[dict[str, Any]] = roadmap["milestones"]
    found = next((item for item in milestones if item["id"] == identifier), None)
    if found is None:
        raise ValueError("roadmap: jalon inconnu")
    previous = str(found["state"])
    if state == previous:
        raise ValueError("roadmap: état inchangé")
    if state == "IMPLEMENTED":
        states = {item["id"]: item["state"] for item in milestones}
        missing = [dep for dep in found["depends_on"] if states[dep] != "IMPLEMENTED"]
        if missing:
            raise ValueError("roadmap: dépendances non réalisées: " + ", ".join(missing))
    history: list[dict[str, Any]] = roadmap["history"]
    if len(history) >= MAX_HISTORY:
        raise ValueError("roadmap: historique plein, archiver manuellement avant poursuite")
    result = {
        "applied": apply,
        "project_id": roadmap["project_id"],
        "milestone_id": identifier,
        "previous": previous,
        "next": state,
        "verification": "NOT_VERIFIED",
        "note": note,
    }
    if apply:
        timestamp = now()
        found["state"] = state
        found["note"] = note
        found["updated_at"] = timestamp
        roadmap["updated_at"] = timestamp
        history.append(
            {
                "milestone_id": identifier,
                "previous": previous,
                "next": state,
                "note": note,
                "at": timestamp,
            }
        )
        path, _ = _path(project)
        write_json(path, roadmap)
    return result
