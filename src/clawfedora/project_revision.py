"""Approved revisions invalidate the dependency closure and archive stale artifacts."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from clawfedora.project_common import assert_no_symlinks, now, read_json, validate_task_id, write_json
from clawfedora.project_engine import current_status
from clawfedora.project_intake import validate_input_integrity


def impact(project: Path, task_id: str) -> list[str]:
    identifier = validate_task_id(task_id)
    plan = read_json(project / "context/project_plan.json")
    tasks = plan["tasks"]
    if identifier not in {task["id"] for task in tasks}:
        raise ValueError("tâche inconnue")
    affected = {identifier}
    while True:
        updated = affected | {
            task["id"] for task in tasks if affected.intersection(task.get("depends_on", []))
        }
        if updated == affected:
            return [str(task["id"]) for task in tasks if task["id"] in affected]
        affected = updated


def revise(
    project: Path, task_id: str, reason: str, *, human_approved: bool = False
) -> dict[str, Any]:
    if not human_approved:
        raise PermissionError("approbation humaine de la modification requise")
    if not reason.strip() or len(reason) > 2000:
        raise ValueError("motif de modification court requis")
    if current_status(project) not in {
        "IN_PROGRESS",
        "VALIDATING",
        "REVIEW",
        "PACKAGING",
        "COMPLETE",
    }:
        raise ValueError("un projet exécuté est requis pour une modification")
    assert_no_symlinks(project, label="révision")
    if validate_input_integrity(project):
        raise ValueError("intégrité des sources invalide")
    affected = impact(project, task_id)
    manifest_path = project / "project.json"
    manifest = read_json(manifest_path)
    assignments_path = project / "context/task_assignments.json"
    assignments = read_json(assignments_path)
    ledger_path = project / "context/revisions.json"
    ledger = read_json(ledger_path) if ledger_path.is_file() else {"revisions": []}
    if not isinstance(ledger.get("revisions"), list):
        raise ValueError("historique de révisions invalide")
    number = len(ledger["revisions"]) + 1
    archive = project / "history/revisions" / f"revision-{number:03d}"
    if archive.exists():
        raise ValueError("archive de révision déjà présente")
    history = manifest.get("orchestration", {}).get("history")
    if not isinstance(history, list):
        raise ValueError("historique du projet invalide")
    if {item["task_id"] for item in assignments["tasks"]}.issuperset(affected) is False:
        raise ValueError("assignations incomplètes")
    moves: list[Path] = []
    for identifier in affected:
        moves.extend(
            project / scope / identifier
            for scope in (
                "work",
                "deliverables",
                "diagrams",
                "evidence",
                "context/exchange",
            )
        )
        moves.append(project / "context/learning/tasks" / f"{identifier}.json")
    moves.extend(
        project / relative
        for relative in (
            "evidence/validation_report.json",
            "evidence/review_report.json",
            "evidence/final_report.json",
            "deliverables/package_manifest.json",
        )
    )
    # Read and validate all transaction-owned JSON before the first move.
    originals = {
        manifest_path: manifest_path.read_bytes(),
        assignments_path: assignments_path.read_bytes(),
    }
    if ledger_path.is_file():
        originals[ledger_path] = ledger_path.read_bytes()
    timestamp = now()
    entry = {
        "revision": number,
        "at": timestamp,
        "actor": "human",
        "task_id": task_id,
        "reason": reason.strip(),
        "affected_tasks": affected,
        "from_status": manifest["status"],
        "status": "APPROVED_REWORK_PENDING",
    }
    moved: list[tuple[Path, Path]] = []
    restored: list[Path] = []
    try:
        archive.mkdir(parents=True)
        for path in moves:
            if path.exists():
                destination = archive / path.relative_to(project)
                destination.parent.mkdir(parents=True, exist_ok=True)
                path.rename(destination)
                moved.append((path, destination))
        # Keep the current contributions of producers outside the revised dependency closure.
        # Copy only their latest PASS bundle, never obsolete runs of an affected producer.
        for consumer in affected:
            for producer in assignments["tasks"]:
                if producer["task_id"] in affected or producer.get("status") != "PASS":
                    continue
                relative = (
                    Path("context/exchange")
                    / consumer
                    / "dependencies"
                    / producer["task_id"]
                    / f"run-{int(producer['attempts']):03d}"
                )
                source = archive / relative
                if source.is_dir():
                    destination = project / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(source, destination)
                    restored.append(destination)
        for item in assignments["tasks"]:
            if item["task_id"] in affected:
                item.update(
                    status="PENDING",
                    revision_attempt_base=int(item.get("attempts", 0)),
                    revision=number,
                    revision_reason=reason.strip(),
                )
        ledger["revisions"].append(entry)
        history.append(
            {
                "at": timestamp,
                "from": manifest["status"],
                "to": "IN_PROGRESS",
                "actor": "human",
                "reason": "approved_revision",
                "revision": number,
            }
        )
        manifest.update(status="IN_PROGRESS", updated_at=timestamp, revision=number)
        write_json(assignments_path, assignments)
        write_json(ledger_path, ledger)
        write_json(archive / "revision.json", entry)
        write_json(manifest_path, manifest)
    except Exception:
        for path in restored:
            shutil.rmtree(path, ignore_errors=True)
        for path, destination in reversed(moved):
            if path.is_dir():
                shutil.rmtree(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            destination.rename(path)
        for path, content in originals.items():
            path.write_bytes(content)
        if ledger_path not in originals:
            ledger_path.unlink(missing_ok=True)
        shutil.rmtree(archive, ignore_errors=True)
        raise
    return entry
