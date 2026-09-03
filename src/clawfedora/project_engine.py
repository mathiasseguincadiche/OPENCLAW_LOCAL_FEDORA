from __future__ import annotations

from pathlib import Path
from typing import Any

from clawfedora.artifact_exchange import (
    publish_task_outputs,
    validate_exchange_completeness,
)
from clawfedora.core_config import AGENT_IDS, core_contract
from clawfedora.project_common import (
    aggregate_records,
    now,
    read_json,
    safe_output,
    sha256_file,
    validate_task_id,
    write_json,
)
from clawfedora.project_intake import validate_input_integrity

ANALYSIS_FIELDS = {
    "summary",
    "objectives",
    "constraints",
    "deliverables",
    "ambiguities",
    "missing_information",
    "risks",
    "decisions_required",
    "source_coverage",
}
_EARLY_ANALYSIS_STATES = {"INTAKE_READY", "ANALYZED", "CLARIFICATION_REQUIRED"}


def manifest(project: Path) -> dict[str, Any]:
    return read_json(project / "project.json")


def current_status(project: Path) -> str:
    return str(manifest(project).get("status", ""))


def _policy(repo_root: Path) -> dict[str, Any]:
    return core_contract(repo_root, "orchestration_policy.yaml")


def _artifact(repo_root: Path, project: Path, artifact_id: str) -> Path:
    relative = dict(_policy(repo_root)["artifacts"]).get(artifact_id)
    if not relative:
        raise KeyError(f"artefact orchestration inconnu: {artifact_id}")
    return project / str(relative)


def _require(repo_root: Path, project: Path, artifact_id: str) -> dict[str, Any]:
    path = _artifact(repo_root, project, artifact_id)
    if not path.is_file():
        raise ValueError(f"artefact requis absent: {path.relative_to(project)}")
    return read_json(path)


def _assert_input_integrity(project: Path) -> None:
    failures = validate_input_integrity(project)
    if failures:
        raise ValueError(f"intégrité des entrées invalide: {failures}")


def _validate_ingestion_index(project: Path) -> list[dict[str, Any]]:
    index = read_json(project / "context" / "ingestion" / "index.json")
    documents = index.get("documents", [])
    if not isinstance(documents, list):
        raise ValueError("index ingestion: documents invalide")
    intake = (project / "intake").resolve()
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for raw in documents:
        if not isinstance(raw, dict):
            raise ValueError("index ingestion: entrée document invalide")
        document_id = str(raw.get("document_id", ""))
        relative = str(raw.get("path", ""))
        if not document_id or document_id in seen_ids:
            raise ValueError(f"index ingestion: document_id invalide/dupliqué: {document_id}")
        if relative in seen_paths:
            raise ValueError(f"index ingestion: chemin dupliqué: {relative}")
        seen_ids.add(document_id)
        seen_paths.add(relative)
        value = Path(relative)
        if value.is_absolute() or not value.parts or value.parts[0] != "intake":
            raise ValueError(f"index ingestion: chemin hors intake: {relative}")
        target = (project / value).resolve()
        if intake not in target.parents or not target.is_file():
            raise ValueError(f"index ingestion: source absente/hors intake: {relative}")
        if target.is_symlink():
            raise ValueError(f"index ingestion: source liée interdite: {relative}")
        if sha256_file(target) != str(raw.get("sha256", "")):
            raise ValueError(f"index ingestion: SHA-256 divergent: {relative}")
        if target.stat().st_size != int(raw.get("size", -1)):
            raise ValueError(f"index ingestion: taille divergente: {relative}")
        normalized.append(raw)
    actual_files = {
        f"intake/{path.relative_to(intake).as_posix()}"
        for path in intake.rglob("*")
        if path.is_file()
    }
    if seen_paths != actual_files:
        missing = sorted(actual_files - seen_paths)
        extra = sorted(seen_paths - actual_files)
        raise ValueError(
            f"index ingestion périmé: missing={missing} extra={extra}"
        )
    if int(index.get("source_count", -1)) != len(normalized):
        raise ValueError("index ingestion: source_count divergent")
    return normalized


def _coverage_gate(repo_root: Path, project: Path, payload: dict[str, Any]) -> None:
    _assert_input_integrity(project)
    documents = _validate_ingestion_index(project)
    coverage = payload.get("source_coverage", [])
    if not isinstance(coverage, list):
        raise ValueError("source_coverage invalide")
    if any(not isinstance(item, dict) for item in coverage):
        raise ValueError("source_coverage doit contenir des objets")
    by_id = {str(item.get("document_id")): item for item in coverage}
    if len(by_id) != len(coverage):
        raise ValueError("source_coverage: document_id vide ou dupliqué")
    expected = {str(item["document_id"]): item for item in documents}
    if set(by_id) != set(expected):
        missing = sorted(set(expected) - set(by_id))
        extra = sorted(set(by_id) - set(expected))
        raise ValueError(
            f"source_coverage incomplète: missing={missing} extra={extra}"
        )
    ingestion_policy = core_contract(repo_root, "document_ingestion_policy.yaml")
    statuses = set(ingestion_policy["coverage_statuses"])
    methods = set(ingestion_policy["coverage_methods"])
    unreadable = 0
    for document_id, source in expected.items():
        item = by_id[document_id]
        status = str(item.get("status", ""))
        method = str(item.get("method", ""))
        if status not in statuses or method not in methods:
            raise ValueError(f"source_coverage invalide pour {document_id}")
        kind = str(source.get("kind", ""))
        required_method = str(source.get("method", ""))
        if (
            kind in {"pdf", "image"}
            and status != "UNREADABLE"
            and method != required_method
        ):
            raise ValueError(
                f"{document_id}: lecture réelle via {required_method} requise"
            )
        if status == "UNREADABLE":
            unreadable += 1
    missing_information = payload.get("missing_information", [])
    if unreadable and (
        not isinstance(missing_information, list) or not missing_information
    ):
        raise ValueError(
            "document UNREADABLE: missing_information doit exposer la limite"
        )


def store_analysis(repo_root: Path, project: Path, payload: dict[str, Any]) -> Path:
    if current_status(project) not in _EARLY_ANALYSIS_STATES:
        raise ValueError("analyse modifiable uniquement avant la planification")
    missing = sorted(ANALYSIS_FIELDS - set(payload))
    if missing:
        raise ValueError(f"analyse incomplète: {', '.join(missing)}")
    if not str(payload["summary"]).strip():
        raise ValueError("analyse: summary vide")
    for field in ANALYSIS_FIELDS - {"summary"}:
        if not isinstance(payload[field], list):
            raise ValueError(f"analyse: {field} doit être une liste")
    _coverage_gate(repo_root, project, payload)
    path = _artifact(repo_root, project, "analysis")
    write_json(
        path,
        {"schema_version": "1.0.0", "generated_at": now(), **payload},
    )
    return path


def _question(value: Any) -> tuple[str, bool]:
    if isinstance(value, dict):
        text = str(
            value.get("question")
            or value.get("description")
            or value.get("text")
            or ""
        ).strip()
        return text, bool(value.get("blocking", True))
    return str(value).strip(), True


def create_clarifications(repo_root: Path, project: Path) -> Path:
    if current_status(project) not in _EARLY_ANALYSIS_STATES:
        raise ValueError("clarifications modifiables uniquement avant la planification")
    analysis = _require(repo_root, project, "analysis")
    items: list[dict[str, Any]] = []
    for source_name in ("ambiguities", "missing_information", "decisions_required"):
        values = analysis.get(source_name, [])
        if not isinstance(values, list):
            raise ValueError(f"analyse: {source_name} invalide")
        for value in values:
            text, blocking = _question(value)
            if not text:
                continue
            items.append(
                {
                    "id": f"clarification-{len(items) + 1:03d}",
                    "source": source_name,
                    "question": text,
                    "blocking": blocking,
                    "status": "OPEN",
                    "answer": None,
                }
            )
    path = _artifact(repo_root, project, "clarifications")
    write_json(
        path,
        {"schema_version": "1.0.0", "generated_at": now(), "items": items},
    )
    return path


def open_blocking_clarifications(
    repo_root: Path,
    project: Path,
) -> list[dict[str, Any]]:
    path = _artifact(repo_root, project, "clarifications")
    if not path.is_file():
        return []
    items = read_json(path).get("items", [])
    if not isinstance(items, list):
        raise ValueError("clarifications: items invalide")
    return [
        item
        for item in items
        if isinstance(item, dict)
        and item.get("blocking") is True
        and item.get("status") != "RESOLVED"
    ]


def resolve_clarification(
    repo_root: Path,
    project: Path,
    clarification_id: str,
    answer: str,
    *,
    actor: str = "human",
) -> dict[str, Any]:
    if current_status(project) != "CLARIFICATION_REQUIRED":
        raise ValueError("résolution autorisée uniquement en CLARIFICATION_REQUIRED")
    if not answer.strip():
        raise ValueError("réponse de clarification vide")
    path = _artifact(repo_root, project, "clarifications")
    payload = read_json(path)
    items = payload.get("items", [])
    if not isinstance(items, list):
        raise ValueError("clarifications: items invalide")
    for item in items:
        if isinstance(item, dict) and item.get("id") == clarification_id:
            item.update(
                {
                    "status": "RESOLVED",
                    "answer": answer.strip(),
                    "resolved_at": now(),
                    "resolved_by": actor,
                }
            )
            write_json(path, payload)
            return item
    raise KeyError(f"clarification inconnue: {clarification_id}")


def _validate_plan(tasks: list[dict[str, Any]]) -> None:
    if not tasks:
        raise ValueError("plan: au moins une tâche requise")
    ids: set[str] = set()
    dependencies: dict[str, list[str]] = {}
    for task in tasks:
        task_id = validate_task_id(str(task.get("id", "")))
        if task_id in ids:
            raise ValueError(f"task id dupliqué: {task_id}")
        ids.add(task_id)
        role = str(task.get("role", ""))
        if role not in AGENT_IDS:
            raise ValueError(f"{task_id}: rôle inconnu: {role}")
        for field in ("title", "objective"):
            if not str(task.get(field, "")).strip():
                raise ValueError(f"{task_id}: {field} vide")
        for field in ("depends_on", "expected_outputs", "acceptance_criteria"):
            if not isinstance(task.get(field, []), list):
                raise ValueError(f"{task_id}: {field} doit être une liste")
        dependencies[task_id] = [str(item) for item in task.get("depends_on", [])]
    for task_id, values in dependencies.items():
        unknown = [value for value in values if value not in ids]
        if unknown:
            raise ValueError(f"{task_id}: dépendances inconnues: {unknown}")
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visiting:
            raise ValueError(f"cycle de dépendances autour de {task_id}")
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency in dependencies[task_id]:
            visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in dependencies:
        visit(task_id)


def store_plan(repo_root: Path, project: Path, payload: dict[str, Any]) -> Path:
    if current_status(project) != "ANALYZED":
        raise ValueError("plan modifiable uniquement en ANALYZED")
    if open_blocking_clarifications(repo_root, project):
        raise ValueError("clarifications bloquantes non résolues")
    _assert_input_integrity(project)
    tasks = payload.get("tasks", [])
    workstreams = payload.get("workstreams", [])
    if not isinstance(tasks, list) or any(
        not isinstance(item, dict) for item in tasks
    ):
        raise ValueError("plan: tasks doit être une liste d'objets")
    if not isinstance(workstreams, list):
        raise ValueError("plan: workstreams doit être une liste")
    _validate_plan(tasks)
    path = _artifact(repo_root, project, "plan")
    write_json(
        path,
        {
            "schema_version": "1.0.0",
            "generated_at": now(),
            "workstreams": workstreams,
            "tasks": tasks,
        },
    )
    return path


def create_assignments(repo_root: Path, project: Path) -> Path:
    if current_status(project) != "PLANNED":
        raise ValueError("assignation autorisée uniquement en PLANNED")
    _assert_input_integrity(project)
    plan = _require(repo_root, project, "plan")
    tasks = plan.get("tasks", [])
    if not isinstance(tasks, list):
        raise ValueError("plan: tasks invalide")
    assignments: list[dict[str, Any]] = []
    packet_root = project / "context" / "tasks"
    packet_root.mkdir(parents=True, exist_ok=True)
    for raw in tasks:
        if not isinstance(raw, dict):
            raise ValueError("plan: task invalide")
        task_id = validate_task_id(str(raw["id"]))
        write_json(
            packet_root / f"{task_id}.json",
            {
                "schema_version": "1.0.0",
                "project_id": manifest(project)["project_id"],
                "task": raw,
                "output_roots": {
                    "work": f"work/{task_id}",
                    "deliverables": f"deliverables/{task_id}",
                    "evidence": f"evidence/{task_id}",
                    "diagrams": f"diagrams/{task_id}",
                },
            },
        )
        assignments.append(
            {
                "task_id": task_id,
                "role": raw["role"],
                "depends_on": list(raw.get("depends_on", [])),
                "status": "PENDING",
                "attempts": 0,
            }
        )
    path = _artifact(repo_root, project, "assignments")
    write_json(
        path,
        {"schema_version": "1.0.0", "generated_at": now(), "tasks": assignments},
    )
    return path


def ready_tasks(repo_root: Path, project: Path) -> list[dict[str, Any]]:
    if current_status(project) != "IN_PROGRESS":
        return []
    assignments = _require(repo_root, project, "assignments")
    tasks = assignments.get("tasks", [])
    if not isinstance(tasks, list):
        raise ValueError("assignments: tasks invalide")
    by_id = {
        str(item.get("task_id")): item
        for item in tasks
        if isinstance(item, dict)
    }
    maximum = int(dict(_policy(repo_root)["execution"])["max_task_attempts"])
    ready: list[dict[str, Any]] = []
    for item in tasks:
        if not isinstance(item, dict):
            continue
        dependencies = item.get("depends_on", [])
        if not isinstance(dependencies, list):
            raise ValueError("assignments: depends_on invalide")
        if (
            item.get("status") != "PASS"
            and int(item.get("attempts", 0)) < maximum
            and all(
                by_id.get(str(dependency), {}).get("status") == "PASS"
                for dependency in dependencies
            )
        ):
            ready.append(item)
    return ready


def _outputs_are_namespaced(task_id: str, outputs: list[str]) -> None:
    for relative in outputs:
        parts = Path(relative).parts
        if len(parts) < 3 or parts[1] != task_id:
            raise ValueError(f"{task_id}: sortie non namespacée: {relative}")


def record_task_result(
    repo_root: Path,
    project: Path,
    *,
    task_id: str,
    agent: str,
    status: str,
    outputs: list[str],
    summary: str,
) -> dict[str, Any]:
    if current_status(project) != "IN_PROGRESS":
        raise ValueError("résultat tâche autorisé uniquement en IN_PROGRESS")
    _assert_input_integrity(project)
    normalized_task_id = validate_task_id(task_id)
    normalized = status.strip().upper()
    if normalized not in {"PASS", "FAIL"}:
        raise ValueError("résultat tâche: PASS ou FAIL requis")
    assignments_path = _artifact(repo_root, project, "assignments")
    assignments = read_json(assignments_path)
    tasks = assignments.get("tasks", [])
    if not isinstance(tasks, list):
        raise ValueError("assignments: tasks invalide")
    by_id = {
        str(item.get("task_id")): item
        for item in tasks
        if isinstance(item, dict)
    }
    task = by_id.get(normalized_task_id)
    if task is None:
        raise KeyError(f"tâche inconnue: {normalized_task_id}")
    if str(task.get("role")) != agent:
        raise PermissionError(
            f"{normalized_task_id}: agent attendu={task.get('role')} reçu={agent}"
        )
    dependencies = task.get("depends_on", [])
    if not isinstance(dependencies, list):
        raise ValueError(f"{normalized_task_id}: depends_on invalide")
    if any(
        by_id.get(str(dependency), {}).get("status") != "PASS"
        for dependency in dependencies
    ):
        raise ValueError(f"{normalized_task_id}: dépendances non PASS")
    maximum = int(dict(_policy(repo_root)["execution"])["max_task_attempts"])
    attempt = int(task.get("attempts", 0)) + 1
    if attempt > maximum:
        raise ValueError(f"{normalized_task_id}: limite de tentatives atteinte")
    _outputs_are_namespaced(normalized_task_id, outputs)
    for output in outputs:
        safe_output(project, output)
    bundles = publish_task_outputs(
        repo_root,
        project,
        producer_task_id=normalized_task_id,
        agent=agent,
        attempt=attempt,
        status=normalized,
        outputs=outputs,
    )
    task.update({"status": normalized, "attempts": attempt, "updated_at": now()})
    write_json(assignments_path, assignments)
    history_path = project / "evidence" / "task_results.json"
    history = (
        read_json(history_path)
        if history_path.is_file()
        else {"schema_version": "1.0.0", "results": []}
    )
    results = history.setdefault("results", [])
    if not isinstance(results, list):
        raise ValueError("task_results: results invalide")
    result = {
        "at": now(),
        "task_id": normalized_task_id,
        "agent": agent,
        "attempt": attempt,
        "status": normalized,
        "summary": summary.strip(),
        "outputs": outputs,
        "bundles": bundles,
    }
    results.append(result)
    write_json(history_path, history)
    return result


def all_tasks_pass(repo_root: Path, project: Path) -> bool:
    tasks = _require(repo_root, project, "assignments").get("tasks", [])
    if not isinstance(tasks, list) or not tasks:
        return False
    return all(
        isinstance(item, dict) and item.get("status") == "PASS" for item in tasks
    )


def store_verdict(
    repo_root: Path,
    project: Path,
    kind: str,
    verdict: str,
    findings: list[dict[str, Any]],
    *,
    reviewer: str,
) -> Path:
    if kind not in {"validation", "review"}:
        raise ValueError("kind doit être validation ou review")
    if reviewer != "auditeur-qualite":
        raise PermissionError("validation/review réservée à auditeur-qualite")
    normalized = verdict.strip().upper()
    if normalized not in {"PASS", "FAIL"}:
        raise ValueError("verdict doit être PASS ou FAIL")
    if any(not isinstance(item, dict) for item in findings):
        raise ValueError("findings doit être une liste d'objets")
    expected_status = "VALIDATING" if kind == "validation" else "REVIEW"
    if current_status(project) != expected_status:
        raise ValueError(f"{kind}: état {expected_status} requis")
    _assert_input_integrity(project)
    path = _artifact(repo_root, project, kind)
    write_json(
        path,
        {
            "schema_version": "1.0.0",
            "generated_at": now(),
            "verdict": normalized,
            "reviewer": reviewer,
            "findings": findings,
        },
    )
    return path


def _verdict(repo_root: Path, project: Path, kind: str) -> str:
    return str(_require(repo_root, project, kind).get("verdict", "")).upper()


def _deliverable_records(project: Path) -> list[dict[str, Any]]:
    deliverables = project / "deliverables"
    records: list[dict[str, Any]] = []
    for path in sorted(deliverables.rglob("*")):
        if not path.is_file() or path.name == "package_manifest.json":
            continue
        records.append(
            {
                "path": path.relative_to(project).as_posix(),
                "sha256": sha256_file(path),
                "size": path.stat().st_size,
            }
        )
    return records


def validate_package(repo_root: Path, project: Path) -> list[str]:
    failures: list[str] = []
    package_manifest = _require(repo_root, project, "package_manifest")
    raw_files = package_manifest.get("files", [])
    if not isinstance(raw_files, list) or any(
        not isinstance(item, dict) for item in raw_files
    ):
        return ["package_manifest: files invalide"]
    observed = _deliverable_records(project)
    if raw_files != observed:
        failures.append("package_manifest: inventaire livrables divergent")
    if str(package_manifest.get("aggregate_sha256", "")) != aggregate_records(observed):
        failures.append("package_manifest: digest agrégé divergent")
    expected_deliverables = manifest(project).get("expected_deliverables", [])
    if not isinstance(expected_deliverables, list):
        failures.append("project.json: expected_deliverables invalide")
    else:
        observed_paths = {str(item["path"]) for item in observed}
        missing = sorted(
            str(value) for value in expected_deliverables if str(value) not in observed_paths
        )
        if missing:
            failures.append(f"package_manifest: livrables attendus absents: {missing}")
    final_report = _require(repo_root, project, "final_report")
    if final_report.get("project_id") != manifest(project).get("project_id"):
        failures.append("final_report: project_id divergent")
    if final_report.get("validation") != "PASS":
        failures.append("final_report: validation PASS absente")
    if final_report.get("review") != "PASS":
        failures.append("final_report: review PASS absente")
    if final_report.get("human_approval_required") is not True:
        failures.append("final_report: gate humain absent")
    return failures


def _assert_transition(
    repo_root: Path,
    project: Path,
    current: str,
    target: str,
    *,
    human_approved: bool,
) -> None:
    _assert_input_integrity(project)
    if target == "ANALYZED":
        _require(repo_root, project, "analysis")
        if (
            current == "CLARIFICATION_REQUIRED"
            and open_blocking_clarifications(repo_root, project)
        ):
            raise ValueError("clarifications bloquantes non résolues")
    elif target == "CLARIFICATION_REQUIRED":
        if not open_blocking_clarifications(repo_root, project):
            raise ValueError("aucune clarification bloquante ouverte")
    elif target == "PLANNED":
        _require(repo_root, project, "plan")
        if open_blocking_clarifications(repo_root, project):
            raise ValueError("clarifications bloquantes non résolues")
    elif target in {"ASSIGNED", "IN_PROGRESS"}:
        _require(repo_root, project, "assignments")
    elif target == "VALIDATING":
        if not all_tasks_pass(repo_root, project):
            raise ValueError("toutes les tâches doivent être PASS")
        exchange_failures = validate_exchange_completeness(repo_root, project)
        if exchange_failures:
            raise ValueError(f"artifact exchange invalide: {exchange_failures}")
    elif target == "REVIEW":
        if _verdict(repo_root, project, "validation") != "PASS":
            raise ValueError("validation PASS requise")
    elif target == "PACKAGING":
        if _verdict(repo_root, project, "review") != "PASS":
            raise ValueError("review PASS requise")
    elif target == "COMPLETE":
        package_failures = validate_package(repo_root, project)
        if package_failures:
            raise ValueError(f"package final invalide: {package_failures}")
        if not human_approved:
            raise PermissionError("approbation humaine finale requise")


def transition_project(
    repo_root: Path,
    project: Path,
    target: str,
    *,
    actor: str,
    reason: str,
    human_approved: bool = False,
) -> dict[str, Any]:
    if not actor.strip() or not reason.strip():
        raise ValueError("transition: actor et reason sont requis")
    payload = manifest(project)
    current = str(payload.get("status", ""))
    transitions = dict(_policy(repo_root)["transitions"])
    allowed = list(transitions.get(current, []))
    if target not in allowed:
        raise ValueError(f"transition interdite: {current} -> {target}")
    _assert_transition(
        repo_root,
        project,
        current,
        target,
        human_approved=human_approved,
    )
    timestamp = now()
    orchestration = payload.setdefault("orchestration", {"history": []})
    if not isinstance(orchestration, dict):
        raise ValueError("project.json: orchestration invalide")
    history = orchestration.setdefault("history", [])
    if not isinstance(history, list):
        raise ValueError("project.json: orchestration.history invalide")
    history.append(
        {
            "at": timestamp,
            "from": current,
            "to": target,
            "actor": actor,
            "reason": reason,
        }
    )
    payload["status"] = target
    payload["updated_at"] = timestamp
    write_json(project / "project.json", payload)
    return payload


def package_project(
    repo_root: Path,
    project: Path,
    *,
    actor: str,
) -> tuple[Path, Path]:
    _assert_input_integrity(project)
    if current_status(project) == "REVIEW":
        transition_project(
            repo_root,
            project,
            "PACKAGING",
            actor=actor,
            reason="review_passed",
        )
    if current_status(project) != "PACKAGING":
        raise ValueError("PACKAGING requis")
    records = _deliverable_records(project)
    expected_deliverables = manifest(project).get("expected_deliverables", [])
    if not isinstance(expected_deliverables, list):
        raise ValueError("project.json: expected_deliverables invalide")
    observed_paths = {str(item["path"]) for item in records}
    missing = sorted(
        str(value) for value in expected_deliverables if str(value) not in observed_paths
    )
    if missing:
        raise ValueError(f"livrables attendus absents: {missing}")
    package_manifest = _artifact(repo_root, project, "package_manifest")
    write_json(
        package_manifest,
        {
            "schema_version": "1.0.0",
            "generated_at": now(),
            "files": records,
            "aggregate_sha256": aggregate_records(records),
        },
    )
    assignments = _require(repo_root, project, "assignments")
    tasks = assignments.get("tasks", [])
    final_report = _artifact(repo_root, project, "final_report")
    write_json(
        final_report,
        {
            "schema_version": "1.0.0",
            "generated_at": now(),
            "project_id": manifest(project)["project_id"],
            "status": "PACKAGING",
            "task_count": len(tasks) if isinstance(tasks, list) else 0,
            "validation": _verdict(repo_root, project, "validation"),
            "review": _verdict(repo_root, project, "review"),
            "human_approval_required": True,
        },
    )
    package_failures = validate_package(repo_root, project)
    if package_failures:
        raise ValueError(f"package généré invalide: {package_failures}")
    return package_manifest, final_report
