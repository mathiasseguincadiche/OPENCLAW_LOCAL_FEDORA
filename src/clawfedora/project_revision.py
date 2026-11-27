"""Approved revisions invalidate the dependency closure and archive stale artifacts."""

from __future__ import annotations

import json
import shutil
from hashlib import sha256
from pathlib import Path
from typing import Any

from clawfedora.project_common import (
    assert_no_symlinks,
    now,
    read_json,
    safe_output,
    sha256_file,
    validate_task_id,
    write_json,
)
from clawfedora.project_engine import TASK_PROMOTION_PATH, audited_inventory, current_status
from clawfedora.project_intake import validate_input_integrity

_AUDIT_REPORTS = {
    "validation": "evidence/validation_report.json",
    "review": "evidence/review_report.json",
}
_AUDIT_STATE = {"VALIDATING": "validation", "REVIEW": "review"}


def _failed_audit(project: Path) -> tuple[str, str, dict[str, Any]] | None:
    kind = _AUDIT_STATE.get(current_status(project))
    if kind is None:
        return None
    path = project / _AUDIT_REPORTS[kind]
    if not path.is_file() or path.resolve() != path.absolute():
        return None
    raw = path.read_bytes()
    report = json.loads(raw)
    if (
        not isinstance(report, dict) or report.get("verdict") != "FAIL"
        or report.get("reviewer") != "auditeur-qualite"
        or not isinstance(report.get("session_id"), str) or not report["session_id"]
        or not isinstance(report.get("snapshot_files"), dict)
        or not isinstance(report.get("criteria"), dict)
    ):
        return None
    return kind, sha256(raw).hexdigest(), report


def _task_findings(task: dict[str, Any], report: dict[str, Any]) -> list[dict[str, Any]]:
    approved = task["acceptance_criteria"]
    rows = report["criteria"].get(task["id"])
    if not isinstance(rows, list) or len(rows) != len(approved):
        return []
    findings: list[dict[str, Any]] = []
    for number, (criterion, row) in enumerate(zip(approved, rows, strict=True), 1):
        if not isinstance(row, dict) or type(row.get("passed")) is not bool:
            return []
        if row["passed"] is False:
            evidence = row.get("evidence")
            if not isinstance(evidence, str) or not evidence.strip():
                return []
            findings.append({"number": number, "criterion": criterion,
                             "evidence": evidence.strip()[:1000]})
    return findings


def audit_corrections(project: Path) -> dict[str, Any] | None:
    """Read-only suggestions for revising a task from the current independent FAIL."""
    current = _failed_audit(project)
    if current is None:
        return None
    kind, digest, report = current
    plan = read_json(project / "context/project_plan.json")
    tasks = []
    for task in plan["tasks"]:
        findings = _task_findings(task, report)
        if findings:
            tasks.append({"task_id": task["id"], "role": task["role"], "findings": findings})
    return {"kind": kind, "sha256": digest, "tasks": tasks} if tasks else None


def _approved_correction(
    project: Path, task_id: str, digest: str, *, revision: int, project_id: str,
) -> dict[str, Any]:
    current = _failed_audit(project)
    if current is None or current[1] != digest:
        raise ValueError("audit de correction absent, remplacé ou empreinte divergente")
    kind, _, report = current
    sealed = report.get("sealed_inventory")
    if not isinstance(sealed, dict) or audited_inventory(project) != sealed:
        raise ValueError("audit de correction périmé : fichiers ou plan modifiés")
    plan = read_json(project / "context/project_plan.json")
    task = next(item for item in plan["tasks"] if item["id"] == task_id)
    findings = _task_findings(task, report)
    if not findings:
        raise ValueError("aucun critère refusé ne correspond à cette tâche")
    previous = [
        {"path": path, "sha256": sealed[path]}
        for path in task["expected_outputs"]
        if path in sealed and report["snapshot_files"].get(path) == sealed[path]
    ]
    return {
        "schema_version": "1.0.0", "project_id": project_id, "revision": revision,
        "task_id": task_id, "producer_role": task["role"],
        "audit": {"kind": kind, "sha256": digest, "session_id": report["session_id"]},
        "findings": findings, "previous_outputs": previous,
    }


def stage_audit_correction(
    project: Path, snapshot: Path, task: dict[str, Any], assignment: dict[str, Any],
) -> bool:
    """Copy the checked revision inputs for just the operator-selected producer."""
    expected = assignment.get("audit_correction_sha256")
    if expected is None:
        return False
    revision = assignment.get("revision")
    if type(revision) is not int or revision < 1:
        raise ValueError("reprise issue d'audit : numéro de révision invalide")
    archive = project / "history/revisions" / f"revision-{revision:03d}"
    packet = archive / "audit-correction.json"
    if packet.resolve(strict=True) != packet.absolute() or sha256_file(packet) != expected:
        raise ValueError("reprise issue d'audit : fiche archivée modifiée")
    data = read_json(packet)
    audit = data["audit"]
    source = archive / _AUDIT_REPORTS[audit["kind"]]
    if (
        data["revision"] != revision or data["task_id"] != task["id"]
        or data["producer_role"] != task["role"]
        or data["project_id"] != read_json(project / "project.json")["project_id"]
        or source.resolve(strict=True) != source.absolute() or sha256_file(source) != audit["sha256"]
    ):
        raise ValueError("reprise issue d'audit : provenance de la fiche divergente")
    for item in data["previous_outputs"]:
        relative = item["path"]
        if relative not in task["expected_outputs"]:
            raise ValueError("reprise issue d'audit : sortie historique hors de la tâche")
        archived = safe_output(archive, relative)
        target = snapshot / "context/previous-outputs" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(archived, target)
        if sha256_file(target) != item["sha256"]:
            raise ValueError("reprise issue d'audit : sortie historique modifiée")
    write_json(snapshot / "context/audit-correction.json", data)
    return True


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
    project: Path, task_id: str, reason: str, *,
    human_approved: bool = False, audit_sha256: str | None = None,
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
    if (project / TASK_PROMOTION_PATH).exists():
        raise ValueError("terminer la publication interrompue avant d’approuver une nouvelle reprise")
    if validate_input_integrity(project):
        raise ValueError("intégrité des sources invalide")
    task_id = validate_task_id(task_id)
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
    correction = (
        _approved_correction(project, task_id, audit_sha256, revision=number,
                             project_id=manifest["project_id"])
        if audit_sha256 is not None else None
    )
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
                "context/operator-proofs",
            )
        )
        moves.append(project / "context/document-sources" / f"{identifier}.json")
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
        if correction is not None:
            packet = archive / "audit-correction.json"
            write_json(packet, correction)
            entry["audit"] = correction["audit"]
            entry["audit_correction_sha256"] = sha256_file(packet)
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
                item.pop("audit_correction_sha256", None)
                item.pop("failure_code", None)
                if correction is not None and item["task_id"] == task_id:
                    item["audit_correction_sha256"] = entry["audit_correction_sha256"]
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
