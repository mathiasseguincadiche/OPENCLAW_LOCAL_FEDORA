from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from clawfedora.core_config import root_contract
from clawfedora.finops import append_cost_event, summarize
from clawfedora.golden_contracts import validate_golden_contracts
from clawfedora.project_common import read_json, validate_project_id, validate_task_id
from clawfedora.project_engine import (
    create_assignments,
    create_clarifications,
    current_status,
    package_project,
    ready_tasks,
    record_task_result,
    store_analysis,
    store_plan,
    store_verdict,
    transition_project,
    validate_package,
)
from clawfedora.project_intake import create_project
from clawfedora.telemetry import emit_event, read_events

REPORT_SCHEMA = "1.0.0"


@dataclass(frozen=True)
class GoldenProjectResult:
    project_id: str
    kind: str
    verdict: str
    terminal_status: str
    task_count: int
    validation: str
    review: str
    package_integrity: bool
    human_gate_preserved: bool
    duration_ms: int
    project_path: str
    failure: str | None = None

    def payload(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "kind": self.kind,
            "verdict": self.verdict,
            "terminal_status": self.terminal_status,
            "task_count": self.task_count,
            "validation": self.validation,
            "review": self.review,
            "package_integrity": self.package_integrity,
            "human_gate_preserved": self.human_gate_preserved,
            "duration_ms": self.duration_ms,
            "project_path": self.project_path,
            "failure": self.failure,
        }


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label}: objet attendu")
    return value


def _run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")


def _project_id(spec: dict[str, Any]) -> str:
    return validate_project_id(str(spec.get("id", "")))


def _l7_policy(repo_root: Path) -> dict[str, Any]:
    contract = root_contract(repo_root, "golden_projects.yaml")
    return _mapping(contract.get("policy"), "L7.policy")


def _task_map(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_tasks = spec.get("tasks", [])
    if not isinstance(raw_tasks, list):
        raise ValueError("L7: tasks invalide")
    tasks: dict[str, dict[str, Any]] = {}
    for raw in raw_tasks:
        task = _mapping(raw, "L7.task")
        task_id = validate_task_id(str(task.get("id", "")))
        if task_id in tasks:
            raise ValueError(f"L7: task id dupliqué: {task_id}")
        tasks[task_id] = task
    if not tasks:
        raise ValueError("L7: au moins une tâche requise")
    return tasks


def _expected_deliverables(spec: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for task in _task_map(spec).values():
        raw = task.get("expected_outputs", [])
        if not isinstance(raw, list):
            raise ValueError("L7: expected_outputs invalide")
        values.extend(str(value) for value in raw)
    return sorted(set(values))


def _source_files(run_root: Path, spec: dict[str, Any]) -> list[Path]:
    project_id = _project_id(spec)
    inputs_root = (run_root.resolve() / "inputs").resolve(strict=False)
    source_root = (inputs_root / project_id).resolve(strict=False)
    if source_root.parent != inputs_root:
        raise ValueError(f"L7: répertoire source hors racine: {project_id}")
    source_root.mkdir(parents=True, exist_ok=False)

    sources = spec.get("sources", [])
    if not isinstance(sources, list) or not sources:
        raise ValueError(f"L7: sources absentes pour {project_id}")
    paths: list[Path] = []
    for index, source in enumerate(sources, start=1):
        text = str(source).strip()
        if not text:
            raise ValueError(f"L7: source vide pour {project_id}")
        path = source_root / f"source-{index:02d}.md"
        path.write_text(
            f"# Source L7 — {project_id}\n\n{text}\n",
            encoding="utf-8",
        )
        paths.append(path)
    return paths


def _coverage(project: Path) -> list[dict[str, Any]]:
    index = read_json(project / "context" / "ingestion" / "index.json")
    documents = index.get("documents", [])
    if not isinstance(documents, list):
        raise ValueError("L7: index ingestion invalide")
    coverage: list[dict[str, Any]] = []
    for raw in documents:
        document = _mapping(raw, "L7.document")
        coverage.append(
            {
                "document_id": document["document_id"],
                "status": "READ",
                "method": document["method"],
            }
        )
    return coverage


def _analysis_payload(
    spec: dict[str, Any],
    coverage: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "summary": str(spec["objective"]),
        "objectives": [str(spec["objective"])],
        "constraints": [
            "local-first",
            "cloud-disabled",
            "remote-publication-disabled",
            "final-human-approval-preserved",
        ],
        "deliverables": _expected_deliverables(spec),
        "ambiguities": [],
        "missing_information": [],
        "risks": ["L7 utilise des sorties déterministes pour valider le moteur projet."],
        "decisions_required": [],
        "source_coverage": coverage,
    }


def _plan_payload(spec: dict[str, Any]) -> dict[str, Any]:
    tasks: list[dict[str, Any]] = []
    for task_id, raw in _task_map(spec).items():
        task = dict(raw)
        task["id"] = task_id
        depends = task.get("depends_on", [])
        if not isinstance(depends, list):
            raise ValueError(f"L7: depends_on invalide pour {task_id}")
        task["depends_on"] = [validate_task_id(str(value)) for value in depends]
        tasks.append(task)
    return {"workstreams": ["l7-golden-project"], "tasks": tasks}


def _write_outputs(
    project: Path,
    task: dict[str, Any],
    project_id: str,
) -> list[str]:
    task_id = validate_task_id(str(task.get("id", "")))
    raw_outputs = task.get("expected_outputs", [])
    if not isinstance(raw_outputs, list) or not raw_outputs:
        raise ValueError(f"L7: expected_outputs absent pour {task_id}")
    dependencies = task.get("depends_on", [])
    if not isinstance(dependencies, list):
        raise ValueError(f"L7: depends_on invalide pour {task_id}")
    dependency_text = (
        ", ".join(str(value) for value in dependencies)
        if dependencies
        else "aucune"
    )

    project_root = project.resolve()
    outputs: list[str] = []
    for raw in raw_outputs:
        relative = str(raw)
        value = Path(relative)
        parts = value.parts
        if (
            value.is_absolute()
            or ".." in parts
            or len(parts) < 3
            or parts[0] != "deliverables"
            or parts[1] != task_id
        ):
            raise ValueError(f"L7: sortie non namespacée/interdite: {relative}")
        path = (project_root / value).resolve(strict=False)
        if project_root not in path.parents:
            raise ValueError(f"L7: sortie hors projet: {relative}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(
                [
                    f"# {task['title']}",
                    "",
                    f"Projet: {project_id}",
                    f"Rôle: {task['role']}",
                    f"Objectif: {task['objective']}",
                    "Dépendances: " + dependency_text,
                    "",
                    "L7 deterministic local evidence: PASS",
                    "Cloud: disabled",
                    "Remote publication: disabled",
                    "Final human approval: preserved",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        outputs.append(relative)
    return outputs


def _task_count(spec: dict[str, Any]) -> int:
    raw = spec.get("tasks", [])
    return len(raw) if isinstance(raw, list) else 0


def _run_project(
    repo_root: Path,
    run_root: Path,
    spec: dict[str, Any],
    *,
    kind: str,
) -> GoldenProjectResult:
    started = time.perf_counter()
    project: Path | None = None
    project_id = str(spec.get("id", "invalid-project"))
    try:
        project_id = _project_id(spec)
        sources = _source_files(run_root, spec)
        project = create_project(
            repo_root,
            run_root,
            project_id,
            str(spec["title"]),
            intake_items=sources,
            expected_deliverables=_expected_deliverables(spec),
        )
        store_analysis(repo_root, project, _analysis_payload(spec, _coverage(project)))
        create_clarifications(repo_root, project)
        transition_project(
            repo_root,
            project,
            "ANALYZED",
            actor="chef-operations",
            reason="l7_analysis_ready",
        )
        store_plan(repo_root, project, _plan_payload(spec))
        transition_project(
            repo_root,
            project,
            "PLANNED",
            actor="chef-operations",
            reason="l7_plan_ready",
        )
        create_assignments(repo_root, project)
        transition_project(
            repo_root,
            project,
            "ASSIGNED",
            actor="chef-operations",
            reason="l7_assignments_ready",
        )
        transition_project(
            repo_root,
            project,
            "IN_PROGRESS",
            actor="chef-operations",
            reason="l7_execution_start",
        )

        tasks = _task_map(spec)
        completed: set[str] = set()
        while len(completed) < len(tasks):
            ready = ready_tasks(repo_root, project)
            pending = [
                item
                for item in ready
                if str(item.get("task_id")) not in completed
            ]
            if not pending:
                raise ValueError(
                    f"L7: graphe bloqué pour {project_id}; completed={sorted(completed)}"
                )
            for assignment in pending:
                task_id = validate_task_id(str(assignment["task_id"]))
                task = tasks[task_id]
                outputs = _write_outputs(project, task, project_id)
                record_task_result(
                    repo_root,
                    project,
                    task_id=task_id,
                    agent=str(task["role"]),
                    status="PASS",
                    outputs=outputs,
                    summary="L7 deterministic project-engine evidence PASS",
                )
                completed.add(task_id)

        transition_project(
            repo_root,
            project,
            "VALIDATING",
            actor="auditeur-qualite",
            reason="l7_tasks_pass",
        )
        store_verdict(
            repo_root,
            project,
            "validation",
            "PASS",
            [],
            reviewer="auditeur-qualite",
        )
        transition_project(
            repo_root,
            project,
            "REVIEW",
            actor="auditeur-qualite",
            reason="l7_validation_pass",
        )
        store_verdict(
            repo_root,
            project,
            "review",
            "PASS",
            [],
            reviewer="auditeur-qualite",
        )
        package_project(repo_root, project, actor="ingenieur-release-forges")

        policy = _l7_policy(repo_root)
        package_failures = validate_package(repo_root, project)
        final_report = read_json(project / "evidence" / "final_report.json")
        status = current_status(project)
        validation = str(final_report.get("validation", ""))
        review = str(final_report.get("review", ""))
        package_integrity = not package_failures
        human_gate = final_report.get("human_approval_required") is True
        required_state = str(policy["required_terminal_status"])
        required_validation = str(policy["required_validation_verdict"])
        required_review = str(policy["required_review_verdict"])
        verdict = "PASS" if all(
            (
                package_integrity,
                human_gate,
                status == required_state,
                validation == required_validation,
                review == required_review,
            )
        ) else "FAIL"
        failures: list[str] = list(package_failures)
        if status != required_state:
            failures.append(f"terminal_status={status} expected={required_state}")
        if validation != required_validation:
            failures.append(
                f"validation={validation} expected={required_validation}"
            )
        if review != required_review:
            failures.append(f"review={review} expected={required_review}")
        if not human_gate:
            failures.append("final human approval gate missing")

        duration_ms = max(0, int((time.perf_counter() - started) * 1000))
        return GoldenProjectResult(
            project_id=project_id,
            kind=kind,
            verdict=verdict,
            terminal_status=status,
            task_count=len(tasks),
            validation=validation,
            review=review,
            package_integrity=package_integrity,
            human_gate_preserved=human_gate,
            duration_ms=duration_ms,
            project_path=str(project),
            failure="; ".join(failures) if failures else None,
        )
    except (
        FileExistsError,
        FileNotFoundError,
        KeyError,
        OSError,
        PermissionError,
        ValueError,
    ) as exc:
        duration_ms = max(0, int((time.perf_counter() - started) * 1000))
        return GoldenProjectResult(
            project_id=project_id,
            kind=kind,
            verdict="FAIL",
            terminal_status=current_status(project) if project is not None else "NOT_CREATED",
            task_count=_task_count(spec),
            validation="",
            review="",
            package_integrity=False,
            human_gate_preserved=False,
            duration_ms=duration_ms,
            project_path=str(project) if project is not None else "",
            failure=f"{type(exc).__name__}: {exc}",
        )


def dry_run(repo_root: Path) -> dict[str, Any]:
    failures, warnings = validate_golden_contracts(repo_root)
    if failures:
        raise ValueError("; ".join(failures))
    contract = root_contract(repo_root, "golden_projects.yaml")
    goldens = contract.get("golden_projects", [])
    representative = _mapping(
        contract.get("representative_project"),
        "representative_project",
    )
    if not isinstance(goldens, list):
        raise ValueError("L7: golden_projects invalide")
    golden_ids = [
        _project_id(_mapping(item, "golden_project"))
        for item in goldens
    ]
    return {
        "schema_version": REPORT_SCHEMA,
        "gate": "L7",
        "verdict": "READY",
        "golden_projects": golden_ids,
        "representative_project": _project_id(representative),
        "project_count": len(goldens) + 1,
        "task_count": sum(
            len(_task_map(_mapping(item, "golden_project"))) for item in goldens
        )
        + len(_task_map(representative)),
        "cloud_calls_allowed": False,
        "remote_publication_allowed": False,
        "final_human_completion_allowed": False,
        "warnings": list(warnings),
    }


def _record_local_accounting(
    repo_root: Path,
    run_root: Path,
    result: GoldenProjectResult,
) -> None:
    emit_event(
        repo_root,
        run_root,
        "l7_project",
        project_id=result.project_id,
        phase=result.kind,
        status=result.verdict,
        duration_ms=result.duration_ms,
    )
    append_cost_event(
        repo_root,
        run_root,
        event="reservation",
        amount_eur=0.0,
        reason="L7 local-only project verification",
        provider="local",
        project_id=result.project_id,
    )
    append_cost_event(
        repo_root,
        run_root,
        event="release",
        amount_eur=0.0,
        reason="L7 local-only project verification complete",
        provider="local",
        project_id=result.project_id,
    )


def run_golden_suite(repo_root: Path, runtime_root: Path) -> tuple[int, Path]:
    failures, _ = validate_golden_contracts(repo_root)
    if failures:
        raise ValueError("; ".join(failures))
    contract = root_contract(repo_root, "golden_projects.yaml")
    policy = _mapping(contract.get("policy"), "L7.policy")
    goldens = contract.get("golden_projects", [])
    representative = _mapping(
        contract.get("representative_project"),
        "representative_project",
    )
    if not isinstance(goldens, list):
        raise ValueError("L7: golden_projects invalide")

    run_id = _run_id()
    run_root = runtime_root.resolve() / "proofs" / "l7" / "runs" / run_id
    run_root.mkdir(parents=True, exist_ok=False)
    results: list[GoldenProjectResult] = []

    for raw in goldens:
        spec = _mapping(raw, "golden_project")
        result = _run_project(repo_root, run_root, spec, kind="golden")
        results.append(result)
        _record_local_accounting(repo_root, run_root, result)

    representative_result = _run_project(
        repo_root,
        run_root,
        representative,
        kind="representative",
    )
    results.append(representative_result)
    _record_local_accounting(repo_root, run_root, representative_result)

    telemetry = read_events(repo_root, run_root, limit=100)
    finops = summarize(repo_root, run_root)
    result_failures = [
        f"{result.project_id}: {result.failure or result.verdict}"
        for result in results
        if result.verdict != "PASS"
    ]
    goldens_pass = sum(
        result.kind == "golden" and result.verdict == "PASS" for result in results
    )
    representative_pass = sum(
        result.kind == "representative" and result.verdict == "PASS"
        for result in results
    )
    if goldens_pass != int(policy["required_golden_projects"]):
        result_failures.append(
            f"golden_projects_pass={goldens_pass}/{policy['required_golden_projects']}"
        )
    if representative_pass != int(policy["required_representative_projects"]):
        result_failures.append(
            "representative_projects_pass="
            f"{representative_pass}/{policy['required_representative_projects']}"
        )
    if len(telemetry) != len(results):
        result_failures.append(
            f"telemetry_events={len(telemetry)} expected={len(results)}"
        )
    if int(finops.get("events", 0)) != len(results) * 2:
        result_failures.append(
            f"finops_events={finops.get('events')} expected={len(results) * 2}"
        )
    if float(finops.get("net_exposure_eur", 0.0)) != 0.0:
        result_failures.append("finops net exposure must remain 0 EUR")
    if any(not result.human_gate_preserved for result in results):
        result_failures.append("final human gate not preserved for every project")

    verdict = "PASS" if not result_failures else "FAIL"
    report = {
        "schema_version": REPORT_SCHEMA,
        "generated_at": datetime.now(UTC).isoformat(),
        "gate": "L7",
        "run_id": run_id,
        "verdict": verdict,
        "golden_projects_pass": goldens_pass,
        "representative_projects_pass": representative_pass,
        "projects": [result.payload() for result in results],
        "telemetry": {
            "events": len(telemetry),
            "local_only": True,
            "raw_prompt_or_response_persisted": False,
        },
        "finops": finops,
        "limitations": list(contract.get("limitations", [])),
        "cloud_calls_allowed": False,
        "remote_publication_allowed": False,
        "automatic_human_approval": False,
        "final_human_completion": False,
        "failures": result_failures,
    }
    report_path = run_root / "L7_REPORT.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return (0 if verdict == "PASS" else 2), report_path
