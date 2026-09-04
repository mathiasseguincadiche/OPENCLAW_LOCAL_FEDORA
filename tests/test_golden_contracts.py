from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from clawfedora import golden_contracts

ROOT = Path(__file__).resolve().parents[1]


def test_l7_contract_passes_repository_contract() -> None:
    failures, warnings = golden_contracts.validate_golden_contracts(ROOT)
    assert failures == ()
    assert warnings == (
        "L7 harness prêt; le PASS L7 exige l'exécution des cinq Golden Projects "
        "et du projet représentatif",
    )


def test_l7_contract_reports_missing_file(tmp_path: Path) -> None:
    failures, warnings = golden_contracts.validate_golden_contracts(tmp_path)
    assert len(failures) == 1
    assert failures[0].startswith("l7:")
    assert warnings == ()


def _task(task_id: str, role: str = "redacteur-technique") -> dict[str, Any]:
    return {
        "id": task_id,
        "role": role,
        "title": "Task",
        "objective": "Objective",
        "depends_on": [],
        "expected_outputs": [f"deliverables/{task_id}/result.md"],
        "acceptance_criteria": ["pass"],
    }


def _project(project_id: str, tasks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": project_id,
        "title": "Project",
        "objective": "Objective",
        "sources": ["source"],
        "tasks": tasks,
    }


def _valid_contract() -> dict[str, Any]:
    goldens = [_project(f"golden-{index}", [_task(f"task-{index}")]) for index in range(5)]
    representative_tasks = [
        _task("chef", "chef-operations"),
        _task("research", "expert-recherche"),
        _task("architecture", "architecte-solutions"),
        _task("devops", "ingenieur-devops"),
        _task("security", "ingenieur-securite"),
        _task("release", "ingenieur-release-forges"),
        _task("docs", "redacteur-technique"),
        _task("audit", "auditeur-qualite"),
    ]
    return {
        "schema_version": "1.0.0",
        "gate": "L7",
        "policy": {
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
        },
        "limitations": ["one", "two", "three"],
        "golden_projects": goldens,
        "representative_project": _project("representative", representative_tasks),
    }


def test_l7_contract_is_fail_closed_on_policy_and_project_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = _valid_contract()
    contract["schema_version"] = "0"
    contract["gate"] = "L6"
    policy = contract["policy"]
    assert isinstance(policy, dict)
    policy["cloud_allowed"] = True
    policy["final_human_completion_allowed"] = True
    policy["required_golden_projects"] = 4
    contract["limitations"] = ["only one"]
    goldens = contract["golden_projects"]
    assert isinstance(goldens, list)
    goldens.pop()
    representative = contract["representative_project"]
    assert isinstance(representative, dict)
    tasks = representative["tasks"]
    assert isinstance(tasks, list)
    tasks.pop()

    monkeypatch.setattr(golden_contracts, "root_contract", lambda *_args: contract)
    failures, warnings = golden_contracts.validate_golden_contracts(ROOT)
    joined = "\n".join(failures)
    assert warnings == ()
    assert "schema_version doit être 1.0.0" in joined
    assert "gate doit être L7" in joined
    assert "cloud_allowed" in joined
    assert "final_human_completion_allowed" in joined
    assert "required_golden_projects" in joined
    assert "trois limites documentées" in joined
    assert "exactement cinq Golden Projects" in joined
    assert "les huit rôles doivent être exercés" in joined


def test_l7_contract_rejects_unsafe_outputs_dependencies_and_cycles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = _valid_contract()
    goldens = contract["golden_projects"]
    assert isinstance(goldens, list)
    first = goldens[0]
    assert isinstance(first, dict)
    tasks = first["tasks"]
    assert isinstance(tasks, list)
    task = tasks[0]
    assert isinstance(task, dict)
    task["expected_outputs"] = ["../escape.md"]
    task["depends_on"] = ["missing-task"]

    second = goldens[1]
    assert isinstance(second, dict)
    second["tasks"] = [
        {
            **_task("task-a"),
            "depends_on": ["task-b"],
        },
        {
            **_task("task-b"),
            "depends_on": ["task-a"],
        },
    ]
    monkeypatch.setattr(golden_contracts, "root_contract", lambda *_args: contract)
    failures, _ = golden_contracts.validate_golden_contracts(ROOT)
    joined = "\n".join(failures)
    assert "sortie non namespacée" in joined
    assert "dépendances inconnues" in joined
    assert "cycle de dépendances" in joined


def test_l7_contract_rejects_invalid_and_normalized_duplicate_project_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = _valid_contract()
    goldens = contract["golden_projects"]
    assert isinstance(goldens, list)
    first = goldens[0]
    second = goldens[1]
    assert isinstance(first, dict)
    assert isinstance(second, dict)
    first["id"] = "../escape"
    second["id"] = "Golden-2"
    third = goldens[2]
    assert isinstance(third, dict)
    third["id"] = "golden-2"

    monkeypatch.setattr(golden_contracts, "root_contract", lambda *_args: contract)
    failures, _ = golden_contracts.validate_golden_contracts(ROOT)
    joined = "\n".join(failures)
    assert "project_id invalide" in joined
    assert "project id dupliqué: golden-2" in joined
