"""Bind private Notion audits to an authorized, local worker task."""
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from clawfedora import notion_duplicates as dup
from clawfedora import notion_inventory_diff as nd
from clawfedora import notion_rationalization as rational
from clawfedora import notion_references as refs
from clawfedora import notion_source_truth as truth
from clawfedora import notion_write as nw
from clawfedora.project_common import (
    project_path,
    read_json,
    sha256_file,
    validate_project_id,
    validate_task_id,
    write_json,
)

TOOL = "clawfedora_notion_audit"
ROLES = frozenset({
    "chef-operations", "architecte-solutions", "redacteur-pedagogique", "auditeur-qualite",
})
OPERATIONS = frozenset({"inventory", "compare", "duplicates", "references", "sources", "plan"})
INPUT_NAMES = ("inventory", "before", "annotations", "registry", "reference_capture", "observations")
MARKER = "context/notion-audit-tool.json"
SESSION = re.compile(r"[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}")


def _approved_operations(role: str) -> frozenset[str]:
    if role not in ROLES:
        return frozenset()
    return OPERATIONS - {"plan"} if role == "auditeur-qualite" else OPERATIONS


def _task_dir(runtime: Path, project_id: str, task_id: str) -> Path:
    state = runtime / "state/notion-audit"
    return state / validate_project_id(project_id) / validate_task_id(task_id)


def _private_dir(path: Path) -> None:
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise nw.NotionWriteError("répertoire Notion privé lié")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    nd._private_path(path / "check")


def _validate_id(value: object, pattern: re.Pattern[str], message: str) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise nw.NotionWriteError(message)
    return value


def _sealed(
    value: object, field: str, fields: set[str],
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields | {field}:
        raise nw.NotionWriteError("format de preuve Notion invalide")
    if value[field] != nw._digest({key: value[key] for key in fields}):
        raise nw.NotionWriteError("empreinte de preuve Notion divergente")
    return value


APPROVAL_FIELDS = {
    "schema", "project_id", "task_id", "role", "task_sha256", "root_page", "operations", "inputs",
}
ARTIFACT_FIELDS = {
    "schema", "project_id", "task_id", "session_id", "role", "operation", "approval_sha256",
    "counts", "report",
}


def _approval(path: Path) -> dict[str, Any]:
    record = _sealed(nd._load_snapshot(path), "approval_sha256", APPROVAL_FIELDS)
    role, operations = record["role"], record["operations"]
    if (
        type(record["schema"]) is not int or record["schema"] != 1
        or not isinstance(role, str) or not isinstance(record["inputs"], dict)
        or not isinstance(operations, list) or not operations
        or not all(isinstance(op, str) and op in _approved_operations(role) for op in operations)
        or operations != sorted(set(operations))
    ):
        raise nw.NotionWriteError("autorisation Notion incompatible")
    return record


def _attached_inventory(
    inputs: dict[str, Any], root: str,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    capture = inputs.get("reference_capture")
    supplied = inputs.get("inventory")
    if capture is not None and not isinstance(capture, dict):
        raise nw.NotionWriteError("capture de références invalide")
    if capture is not None:
        snapshot, _, _ = refs._validated_bundle(capture, root)
        if supplied is not None:
            selected, _ = nd._validated(supplied, root)
            if snapshot["structure_sha256"] != selected["structure_sha256"]:
                raise nw.NotionWriteError("capture de références issue d'un autre inventaire")
        else:
            supplied = snapshot
    inventory, _ = nd._validated(supplied, root)
    return inventory, capture


def _compute(record: dict[str, Any], operation: str) -> tuple[dict[str, Any], dict[str, int]]:
    inputs, root = record["inputs"], record["root_page"]
    inventory, capture = _attached_inventory(inputs, root)
    when = refs._utc(inputs["as_of"]) if "as_of" in inputs else None
    annotations = inputs.get("annotations")
    registry = inputs.get("registry")
    observations = inputs.get("observations")
    if operation == "inventory":
        return inventory, dict(inventory["counts"])
    if operation == "compare":
        report = nd.compare(inputs.get("before"), inventory, root_page=root)
        return report, {key: len(report[key]) for key in ("added", "absent", "modified", "reordered")}
    if operation == "duplicates":
        report = dup.analyze(inventory, root_page=root, evidence=annotations)
        return report, {
            "findings": len(report["findings"]), "protected": len(report["protected_objects"]),
        }
    if operation == "references":
        if capture is None:
            raise nw.NotionWriteError("capture de références requise")
        when = when if when is not None else refs._utc(capture["inventory"]["captured_at"])
        report = refs.audit(capture, root_page=root, as_of=when, observations=observations)
        return report, dict(report["counts_by_status"])
    if operation == "sources":
        report = truth.audit(inventory, root_page=root, registry=registry,
                             annotations=annotations, reference_capture=capture)
        return report, {"subjects": len(report["subjects"])}
    if operation != "plan":
        raise nw.NotionWriteError("opération Notion inconnue")
    report = rational.plan(
        inventory, root_page=root, before=inputs.get("before"), annotations=annotations,
        registry=registry, reference_capture=capture, observations=observations, as_of=when,
    )
    return report, {"issues": len(report["issues"])}


def approve(
    runtime: Path, project_id: str, task_id: str, root_page: str, operations: list[str],
    inputs: dict[str, Any], *, replace_sha256: str | None = None,
) -> str:
    """Freeze an operator-selected set of inputs for an existing assigned task."""
    from clawfedora.project_worker import worker_lock

    project_id, task_id = validate_project_id(project_id), validate_task_id(task_id)
    root = nw._id(root_page)
    with worker_lock(runtime, allow_gaming=True):
        project = project_path(runtime, project_id)
        if read_json(project / "project.json").get("status") not in {"ASSIGNED", "IN_PROGRESS"}:
            raise nw.NotionWriteError("tâche d'un projet assigné requise")
        task = read_json(project / "context/tasks" / f"{task_id}.json")["task"]
        assignments = read_json(project / "context/task_assignments.json")["tasks"]
        assignment = next((item for item in assignments if item.get("task_id") == task_id), None)
        if assignment is None:
            raise nw.NotionWriteError("tâche Notion non assignée")
        if assignment.get("revision_reason"):
            task = {**task, "approved_revision": assignment["revision_reason"]}
        role = task.get("role")
        selected = sorted(set(operations))
        if (
            not isinstance(role, str) or not selected
            or not set(selected) <= _approved_operations(role)
        ):
            raise nw.NotionWriteError("opération Notion non autorisée pour le rôle de la tâche")
        if set(inputs) - (set(INPUT_NAMES) | {"as_of"}):
            raise nw.NotionWriteError("entrée Notion non reconnue")
        record = {
            "schema": 1, "project_id": project_id, "task_id": task_id, "role": role,
            "task_sha256": nw._digest(task), "root_page": root, "operations": selected,
            "inputs": inputs,
        }
        digest = nw._digest(record)
        sealed = {**record, "approval_sha256": digest}
        if _json_size(sealed) > nd.MAX_BYTES:
            raise nw.NotionWriteError("autorisation Notion trop volumineuse")
        for operation in selected:
            _compute(record, operation)
        target = _task_dir(runtime, project_id, task_id) / "approval.json"
        _private_dir(target.parent)
        if replace_sha256 is None:
            nd._write_private_report(target, sealed)
        else:
            if _approval(target)["approval_sha256"] != replace_sha256:
                raise nw.NotionWriteError("autorisation Notion remplacée entre-temps")
            with tempfile.TemporaryDirectory(dir=target.parent) as name:
                staged = Path(name) / "approval.json"
                nw._private_new(staged, sealed)
                os.replace(staged, target)
        return digest


def _json_size(value: dict[str, Any]) -> int:
    return len(json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")) + 1


def bind_snapshot(
    runtime: Path, project_id: str, task: dict[str, Any], snapshot: Path, *, local: bool,
) -> dict[str, Any] | None:
    """Stage only the authorized envelope fingerprint in the worker snapshot."""
    role = task.get("role")
    if not local or not isinstance(role, str) or role not in ROLES:
        return None
    task_id = validate_task_id(str(task["id"]))
    path = _task_dir(runtime, project_id, task_id) / "approval.json"
    if not path.exists() and not path.is_symlink():
        return None
    record = _approval(path)
    if (
        record["project_id"] != project_id or record["task_id"] != task_id
        or record["role"] != role or record["task_sha256"] != nw._digest(task)
    ):
        raise nw.NotionWriteError("autorisation Notion périmée pour cette tâche")
    binding = {"approval_sha256": record["approval_sha256"], "operations": record["operations"],
               "role": role}
    write_json(snapshot / MARKER, binding)
    return binding



def _active(
    runtime: Path, workspace: Path, role: str, scope: str, operation: str,
) -> tuple[dict[str, Any], tuple[str, str, str]]:
    from clawfedora.project_control import is_paused, progress

    state = progress(runtime)
    if (
        state.get("active") is not True or state.get("phase") != "running"
        or state.get("role") != role or operation not in _approved_operations(role)
    ):
        raise nw.NotionWriteError("outil Notion réservé au rôle de la tâche locale active")
    project_id = validate_project_id(str(state.get("project_id", "")))
    task_id = validate_task_id(str(state.get("task_id", "")))
    session = _validate_id(state.get("session_id"), SESSION, "session Notion invalide")
    expected = f"projects/{project_id}/{task_id}/{session}"
    if scope != expected or is_paused(runtime, project_path(runtime, project_id)):
        raise nw.NotionWriteError("outil Notion hors du snapshot courant ou en pause")
    snapshot = workspace / expected
    marker, guard = snapshot / MARKER, snapshot / ".openclaw-fedora-input-guard.json"
    if (
        any(parent.is_symlink() for parent in (marker, *marker.parents))
        or guard.is_symlink() or not marker.is_file() or not guard.is_file()
        or read_json(guard).get("files", {}).get(MARKER) != sha256_file(marker)
    ):
        raise nw.NotionWriteError("autorisation Notion absente du snapshot protégé")
    binding = read_json(marker)
    record = _approval(_task_dir(runtime, project_id, task_id) / "approval.json")
    if (
        binding.get("approval_sha256") != record["approval_sha256"]
        or binding.get("role") != role or binding.get("operations") != record["operations"]
        or record["role"] != role or record["project_id"] != project_id
        or record["task_id"] != task_id or operation not in record["operations"]
    ):
        raise nw.NotionWriteError("opération non approuvée ou autorisation Notion modifiée")
    return record, (project_id, task_id, session)


def _report_path(runtime: Path, project_id: str, task_id: str, session: str, operation: str) -> Path:
    session = _validate_id(session, SESSION, "session Notion invalide")
    if operation not in OPERATIONS:
        raise nw.NotionWriteError("opération Notion inconnue")
    return _task_dir(runtime, project_id, task_id) / session / f"{operation}.json"


def _verified_report(
    runtime: Path, project_id: str, task_id: str, session: str, operation: str, expected_sha256: str,
) -> tuple[Path, dict[str, Any]]:
    path = _report_path(runtime, project_id, task_id, session, operation)
    evidence = _sealed(nd._load_snapshot(path), "artifact_sha256", ARTIFACT_FIELDS)
    if (
        evidence["artifact_sha256"] != expected_sha256 or type(evidence["schema"]) is not int
        or evidence["schema"] != 1 or evidence["project_id"] != project_id
        or evidence["task_id"] != task_id or evidence["session_id"] != session
        or evidence["operation"] != operation
    ):
        raise nw.NotionWriteError("rapport Notion lié à une autre tâche, session ou empreinte")
    return path, evidence


def verify(
    runtime: Path, project_id: str, task_id: str, session: str, operation: str, expected_sha256: str,
) -> Path:
    """Validate the selected report for human review using its collected fingerprint."""
    path, _ = _verified_report(runtime, project_id, task_id, session, operation, expected_sha256)
    return path


def run(
    runtime: Path, workspace: Path, role: str, data: dict[str, Any],
) -> dict[str, Any]:
    from clawfedora.specialist_tools import receipt

    scope, operation = data.get("scope"), data.get("operation")
    if (
        set(data) != {"scope", "operation"}
        or not isinstance(scope, str) or not isinstance(operation, str)
    ):
        raise nw.NotionWriteError("scope courant et opération Notion requis")
    approval, (project_id, task_id, session) = _active(runtime, workspace, role, scope, operation)
    report, counts = _compute(approval, operation)
    current, current_scope = _active(runtime, workspace, role, scope, operation)
    if current_scope != (project_id, task_id, session) or current != approval:
        raise nw.NotionWriteError("autorisation Notion modifiée pendant l'analyse")
    envelope = {
        "schema": 1, "project_id": project_id, "task_id": task_id, "session_id": session,
        "role": role, "operation": operation, "approval_sha256": approval["approval_sha256"],
        "counts": counts, "report": report,
    }
    fingerprint = nw._digest(envelope)
    artifact = {**envelope, "artifact_sha256": fingerprint}
    if _json_size(artifact) > nd.MAX_BYTES:
        raise nw.NotionWriteError("rapport Notion trop volumineux")
    path = _report_path(runtime, project_id, task_id, session, operation)
    _private_dir(path.parent)
    try:
        nd._write_private_report(path, artifact)
    except FileExistsError:
        verify(runtime, project_id, task_id, session, operation, fingerprint)
    result = {
        "scope": scope, "role": role, "status": "REVIEW_REQUIRED",
        "operation": operation, "counts": counts, "approval_sha256": approval["approval_sha256"],
        "artifact_sha256": fingerprint, "remote_write": False,
    }
    return {**result, "receipt": receipt(workspace, TOOL, result)}


def validate_receipt(
    runtime: Path, proof: dict[str, Any], scope: str, binding: dict[str, Any] | None,
) -> None:
    if (
        binding is None or proof.get("scope") != scope or proof.get("role") != binding.get("role")
        or proof.get("approval_sha256") != binding.get("approval_sha256")
        or proof.get("operation") not in binding.get("operations", [])
        or proof.get("status") != "REVIEW_REQUIRED" or proof.get("remote_write") is not False
    ):
        raise nw.NotionWriteError("preuve Notion hors du snapshot courant")
    parts = scope.split("/")
    if len(parts) != 4 or parts[0] != "projects":
        raise nw.NotionWriteError("périmètre de preuve Notion invalide")
    _, envelope = _verified_report(
        runtime, parts[1], parts[2], parts[3], proof["operation"], proof.get("artifact_sha256", ""),
    )
    if (
        envelope["role"] != proof["role"] or envelope["approval_sha256"] != proof["approval_sha256"]
        or envelope["counts"] != proof.get("counts")
    ):
        raise nw.NotionWriteError("rapport et preuve Notion divergents")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Autoriser ou vérifier un audit Notion du worker")
    parser.add_argument("--runtime", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("approve", "verify"):
        cmd = commands.add_parser(name)
        cmd.add_argument("--project", required=True)
        cmd.add_argument("--task", required=True)
        if name == "approve":
            cmd.add_argument("--page", required=True)
            cmd.add_argument(
                "--operation", action="append", choices=sorted(OPERATIONS), required=True,
            )
            for item in INPUT_NAMES:
                cmd.add_argument("--" + item.replace("_", "-"), type=Path)
            cmd.add_argument("--as-of")
            cmd.add_argument("--replace-sha256")
        else:
            cmd.add_argument("--session", required=True)
            cmd.add_argument("--operation", choices=sorted(OPERATIONS), required=True)
            cmd.add_argument("--sha256", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "approve":
            inputs: dict[str, Any] = {key: truth._optional_json(path) for key in INPUT_NAMES
                      if (path := getattr(args, key)) is not None}
            if args.as_of is not None:
                inputs["as_of"] = refs._utc(args.as_of).isoformat()
            digest = approve(args.runtime, args.project, args.task, args.page, args.operation,
                             inputs, replace_sha256=args.replace_sha256)
            print(f"NOTION_WORKER=APPROVED approval_sha256={digest}")
        else:
            path = verify(args.runtime, args.project, args.task, args.session,
                          args.operation, args.sha256)
            print(f"NOTION_WORKER=VERIFIED {path}")
        return 0
    except nw.NotionWriteError as exc:
        print(f"NOTION_WORKER=REFUSED {exc}")
        return 2
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        print("NOTION_WORKER=REFUSED entrées, tâche ou rapport invalides")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
