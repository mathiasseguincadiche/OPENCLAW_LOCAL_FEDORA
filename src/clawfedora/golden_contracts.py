from __future__ import annotations

from pathlib import Path
from typing import Any

from clawfedora.core_config import AGENT_IDS, root_contract
from clawfedora.project_common import validate_task_id

EXPECTED_SCHEMA = "1.0.0"
EXPECTED_GATE = "L7"


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label}: objet attendu")
    return value


def _task_failures(project_id: str, raw_tasks: Any) -> list[str]:
    failures: list[str] = []
    if not isinstance(raw_tasks, list) or not raw_tasks:
        return [f"{project_id}: au moins une tâche requise"]
    tasks = [item for item in raw_tasks if isinstance(item, dict)]
    if len(tasks) != len(raw_tasks):
        failures.append(f"{project_id}: tasks doit contenir uniquement des objets")
        return failures
    ids: set[str] = set()
    dependencies: dict[str, list[str]] = {}
    for task in tasks:
        try:
            task_id = validate_task_id(str(task.get("id", "")))
        except ValueError as exc:
            failures.append(f"{project_id}: {exc}")
            continue
        if task_id in ids:
            failures.append(f"{project_id}: task id dupliqué: {task_id}")
            continue
        ids.add(task_id)
        role = str(task.get("role", ""))
        if role not in AGENT_IDS:
            failures.append(f"{project_id}/{task_id}: rôle inconnu: {role}")
        for field in ("title", "objective"):
            if not str(task.get(field, "")).strip():
                failures.append(f"{project_id}/{task_id}: {field} vide")
        depends = task.get("depends_on", [])
        outputs = task.get("expected_outputs", [])
        criteria = task.get("acceptance_criteria", [])
        if not isinstance(depends, list):
            failures.append(f"{project_id}/{task_id}: depends_on doit être une liste")
            depends = []
        if not isinstance(outputs, list) or not outputs:
            failures.append(f"{project_id}/{task_id}: expected_outputs requis")
            outputs = []
        if not isinstance(criteria, list) or not criteria:
            failures.append(f"{project_id}/{task_id}: acceptance_criteria requis")
        dependencies[task_id] = [str(value) for value in depends]
        for relative in outputs:
            value = Path(str(relative))
            parts = value.parts
            if (
                value.is_absolute()
                or ".." in parts
                or len(parts) < 3
                or parts[0] != "deliverables"
                or parts[1] != task_id
            ):
                failures.append(
                    f"{project_id}/{task_id}: sortie non namespacée: {relative}"
                )
    for task_id, values in dependencies.items():
        unknown = sorted(value for value in values if value not in ids)
        if unknown:
            failures.append(f"{project_id}/{task_id}: dépendances inconnues: {unknown}")
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visiting:
            failures.append(f"{project_id}: cycle de dépendances autour de {task_id}")
            return
        if task_id in visited or task_id not in dependencies:
            return
        visiting.add(task_id)
        for dependency in dependencies[task_id]:
            visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in dependencies:
        visit(task_id)
    return failures


def _project_failures(raw: Any, *, representative: bool) -> list[str]:
    label = "representative_project" if representative else "golden_project"
    if not isinstance(raw, dict):
        return [f"{label}: objet attendu"]
    project_id = str(raw.get("id", "")).strip()
    failures: list[str] = []
    if not project_id:
        failures.append(f"{label}: id requis")
        project_id = label
    if not str(raw.get("title", "")).strip():
        failures.append(f"{project_id}: title requis")
    if not str(raw.get("objective", "")).strip():
        failures.append(f"{project_id}: objective requis")
    sources = raw.get("sources", [])
    if (
        not isinstance(sources, list)
        or not sources
        or any(not str(value).strip() for value in sources)
    ):
        failures.append(f"{project_id}: au moins une source texte non vide requise")
    failures.extend(_task_failures(project_id, raw.get("tasks")))
    if representative and isinstance(raw.get("tasks"), list):
        roles = {
            str(item.get("role", ""))
            for item in raw["tasks"]
            if isinstance(item, dict)
        }
        missing_roles = sorted(set(AGENT_IDS) - roles)
        if missing_roles:
            failures.append(
                f"{project_id}: les huit rôles doivent être exercés, absents={missing_roles}"
            )
    return failures


def validate_golden_contracts(repo_root: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    failures: list[str] = []
    warnings: list[str] = []
    try:
        contract = root_contract(repo_root, "golden_projects.yaml")
        if contract.get("schema_version") != EXPECTED_SCHEMA:
            failures.append("l7: schema_version doit être 1.0.0")
        if contract.get("gate") != EXPECTED_GATE:
            failures.append("l7: gate doit être L7")
        policy = _mapping(contract.get("policy"), "l7.policy")
        required_policy = {
            "local_only": True,
            "cloud_allowed": False,
            "remote_publication_allowed": False,
            "final_human_completion_allowed": False,
            "telemetry_required": True,
            "finops_required": True,
            "required_golden_projects": 5,
            "required_representative_projects": 1,
            "required_terminal_status": "PACKAGING",
            "required_validation_verdict": "PASS",
            "required_review_verdict": "PASS",
            "require_package_integrity": True,
            "require_human_gate_preserved": True,
        }
        for key, expected in required_policy.items():
            if policy.get(key) != expected:
                failures.append(f"l7.policy.{key}: attendu={expected!r}")
        limitations = contract.get("limitations", [])
        if not isinstance(limitations, list) or len(limitations) < 3:
            failures.append("l7: au moins trois limites documentées sont requises")

        goldens = contract.get("golden_projects", [])
        if not isinstance(goldens, list) or len(goldens) != 5:
            failures.append("l7: exactement cinq Golden Projects sont requis")
            goldens = []
        seen_ids: set[str] = set()
        for raw in goldens:
            failures.extend(_project_failures(raw, representative=False))
            if isinstance(raw, dict):
                project_id = str(raw.get("id", "")).strip()
                if project_id in seen_ids:
                    failures.append(f"l7: project id dupliqué: {project_id}")
                seen_ids.add(project_id)

        representative = contract.get("representative_project")
        failures.extend(_project_failures(representative, representative=True))
        if isinstance(representative, dict):
            representative_id = str(representative.get("id", "")).strip()
            if representative_id in seen_ids:
                failures.append(
                    f"l7: representative project id dupliqué: {representative_id}"
                )

        if not failures:
            warnings.append(
                "L7 harness prêt; le PASS L7 exige l'exécution des cinq Golden Projects "
                "et du projet représentatif"
            )
    except (FileNotFoundError, ValueError) as exc:
        failures.append(f"l7: {exc}")
    return tuple(failures), tuple(warnings)
