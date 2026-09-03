from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from clawfedora.core_config import core_contract
from clawfedora.project_common import (
    aggregate_records,
    assert_no_symlinks,
    chmod_read_only_files,
    now,
    read_json,
    safe_output,
    sha256_file,
    write_json,
)


def _orchestration_artifact(repo_root: Path, project: Path, artifact_id: str) -> Path:
    policy = core_contract(repo_root, "orchestration_policy.yaml")
    relative = dict(policy["artifacts"]).get(artifact_id)
    if not relative:
        raise KeyError(f"artefact orchestration inconnu: {artifact_id}")
    return project / str(relative)


def _plan_tasks(repo_root: Path, project: Path) -> dict[str, dict[str, Any]]:
    plan_path = _orchestration_artifact(repo_root, project, "plan")
    payload = read_json(plan_path)
    tasks = payload.get("tasks", [])
    if not isinstance(tasks, list):
        raise ValueError("project_plan.json: tasks invalide")
    result: dict[str, dict[str, Any]] = {}
    for raw in tasks:
        if not isinstance(raw, dict):
            raise ValueError("project_plan.json: task invalide")
        task_id = str(raw.get("id", ""))
        if not task_id:
            raise ValueError("project_plan.json: task sans id")
        result[task_id] = raw
    return result


def _dependencies(repo_root: Path, project: Path) -> dict[str, list[str]]:
    return {
        task_id: [str(value) for value in raw.get("depends_on", [])]
        for task_id, raw in _plan_tasks(repo_root, project).items()
    }


def _dependents(
    dependencies: dict[str, list[str]],
    producer: str,
    *,
    transitive: bool,
) -> list[tuple[str, bool]]:
    if producer not in dependencies:
        raise KeyError(f"tâche productrice inconnue: {producer}")
    direct = sorted(task for task, values in dependencies.items() if producer in values)
    if not transitive:
        return [(task, True) for task in direct]
    discovered = set(direct)
    queue = list(direct)
    while queue:
        upstream = queue.pop(0)
        for task, values in dependencies.items():
            if upstream in values and task not in discovered:
                discovered.add(task)
                queue.append(task)
    return [(task, task in direct) for task in sorted(discovered)]


def _bundle_path(project: Path, producer: str, consumer: str | None, attempt: int) -> Path:
    root = project / "context" / "exchange"
    if consumer is None:
        return root / producer / "self" / f"run-{attempt:03d}"
    return root / consumer / "dependencies" / producer / f"run-{attempt:03d}"


def _make_bundle(
    project: Path,
    *,
    producer: str,
    consumer: str | None,
    agent: str,
    attempt: int,
    status: str,
    outputs: list[str],
    direct_dependency: bool | None,
) -> Path:
    destination = _bundle_path(project, producer, consumer, attempt)
    if destination.exists():
        raise FileExistsError(f"bundle existe déjà: {destination.relative_to(project)}")
    artifact_root = destination / "artifacts"
    artifact_root.mkdir(parents=True, exist_ok=False)
    records: list[dict[str, Any]] = []
    for relative in sorted(set(outputs)):
        source = safe_output(project, relative)
        target = artifact_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        records.append(
            {
                "path": relative,
                "sha256": sha256_file(target),
                "size": target.stat().st_size,
            }
        )
    manifest = {
        "schema_version": "1.0.0",
        "generated_at": now(),
        "producer_task_id": producer,
        "consumer_task_id": consumer,
        "producer_agent": agent,
        "attempt": attempt,
        "producer_status": status,
        "direct_dependency": direct_dependency,
        "files": records,
        "aggregate_sha256": aggregate_records(records),
        "immutable_provenance": True,
        "consumer_must_not_modify_in_place": True,
    }
    write_json(destination / "manifest.json", manifest)
    assert_no_symlinks(destination, label="bundle d'échange")
    chmod_read_only_files(destination)
    return destination


def publish_task_outputs(
    repo_root: Path,
    project: Path,
    *,
    producer_task_id: str,
    agent: str,
    attempt: int,
    status: str,
    outputs: list[str],
) -> list[str]:
    if attempt < 1:
        raise ValueError("attempt doit être >= 1")
    normalized = status.strip().upper()
    if normalized not in {"PASS", "FAIL"}:
        raise ValueError(f"statut tâche invalide: {status}")
    policy = core_contract(repo_root, "artifact_exchange_policy.yaml")
    dependencies = _dependencies(repo_root, project)
    published = [
        _make_bundle(
            project,
            producer=producer_task_id,
            consumer=None,
            agent=agent,
            attempt=attempt,
            status=normalized,
            outputs=outputs,
            direct_dependency=None,
        )
    ]
    propagation = dict(policy["propagation"])
    if normalized == "PASS" and bool(propagation["direct_dependents"]):
        for consumer, direct in _dependents(
            dependencies,
            producer_task_id,
            transitive=bool(propagation["transitive_dependents"]),
        ):
            published.append(
                _make_bundle(
                    project,
                    producer=producer_task_id,
                    consumer=consumer,
                    agent=agent,
                    attempt=attempt,
                    status=normalized,
                    outputs=outputs,
                    direct_dependency=direct,
                )
            )
    index_path = project / str(policy.get("root", "context/exchange")) / "index.json"
    index = (
        read_json(index_path)
        if index_path.is_file()
        else {"schema_version": "1.0.0", "records": []}
    )
    records = index.setdefault("records", [])
    if not isinstance(records, list):
        raise ValueError("index artifact exchange invalide")
    for bundle in published:
        bundle_manifest = read_json(bundle / "manifest.json")
        records.append(
            {
                "at": now(),
                "producer_task_id": producer_task_id,
                "consumer_task_id": bundle_manifest["consumer_task_id"],
                "attempt": attempt,
                "status": normalized,
                "bundle": bundle.relative_to(project).as_posix(),
            }
        )
    index["updated_at"] = now()
    write_json(index_path, index)
    return [bundle.relative_to(project).as_posix() for bundle in published]


def validate_bundle(project: Path, bundle: Path) -> list[str]:
    failures: list[str] = []
    try:
        resolved = bundle.resolve(strict=True)
        if project.resolve() not in resolved.parents:
            return [f"bundle hors projet: {bundle}"]
        assert_no_symlinks(bundle, label="bundle d'échange")
    except (FileNotFoundError, ValueError) as exc:
        return [str(exc)]
    manifest_path = bundle / "manifest.json"
    if not manifest_path.is_file():
        return [f"manifest absent: {bundle.relative_to(project)}"]
    bundle_manifest = read_json(manifest_path)
    raw_files = bundle_manifest.get("files", [])
    if not isinstance(raw_files, list):
        return ["manifest files invalide"]
    observed: list[dict[str, Any]] = []
    for raw in raw_files:
        if not isinstance(raw, dict):
            failures.append("entrée manifeste invalide")
            continue
        relative = str(raw.get("path", ""))
        value = Path(relative)
        target = (bundle / "artifacts" / value).resolve()
        artifact_root = (bundle / "artifacts").resolve()
        if artifact_root not in target.parents or not target.is_file():
            failures.append(f"artefact absent ou hors bundle: {relative}")
            continue
        digest = sha256_file(target)
        size = target.stat().st_size
        if digest != str(raw.get("sha256", "")) or size != int(raw.get("size", -1)):
            failures.append(f"artefact modifié: {relative}")
        observed.append({"path": relative, "sha256": digest, "size": size})
    if aggregate_records(observed) != str(bundle_manifest.get("aggregate_sha256", "")):
        failures.append("digest agrégé invalide")
    return failures


def validate_exchange_completeness(repo_root: Path, project: Path) -> list[str]:
    policy = core_contract(repo_root, "artifact_exchange_policy.yaml")
    assignments_path = _orchestration_artifact(repo_root, project, "assignments")
    assignments = read_json(assignments_path)
    raw_tasks = assignments.get("tasks", [])
    if not isinstance(raw_tasks, list):
        raise ValueError("task_assignments.json: tasks invalide")
    dependencies = _dependencies(repo_root, project)
    transitive = bool(dict(policy["propagation"])["transitive_dependents"])
    failures: list[str] = []
    for raw in raw_tasks:
        if not isinstance(raw, dict):
            failures.append("assignation invalide")
            continue
        task_id = str(raw.get("task_id", ""))
        attempts = int(raw.get("attempts", 0))
        status = str(raw.get("status", ""))
        if attempts < 1:
            continue
        self_bundle = _bundle_path(project, task_id, None, attempts)
        if not self_bundle.is_dir():
            failures.append(f"self-history absent: {task_id} run-{attempts:03d}")
        else:
            failures.extend(validate_bundle(project, self_bundle))
        if status != "PASS":
            continue
        for consumer, _ in _dependents(
            dependencies,
            task_id,
            transitive=transitive,
        ):
            bundle = _bundle_path(project, task_id, consumer, attempts)
            if not bundle.is_dir():
                failures.append(
                    f"propagation absente: {task_id} -> {consumer} run-{attempts:03d}"
                )
            else:
                failures.extend(validate_bundle(project, bundle))
    return failures
