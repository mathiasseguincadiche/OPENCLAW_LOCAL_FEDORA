from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from test_daily_worker import planned as planned

from clawfedora.agents import deploy_workspaces
from clawfedora.core_config import AGENT_IDS
from clawfedora.learning import awaiting, checkpoints, contract, initialize, submit
from clawfedora.project_common import read_json
from clawfedora.project_engine import ready_tasks, transition_project
from clawfedora.project_intake import create_project
from clawfedora.project_worker import run_project_tasks, worker_lock

ROOT = Path(__file__).resolve().parents[1]


def starter(role: str, prompt: str, _session: str) -> dict[str, Any]:
    task = json.loads(prompt.split("\n", 1)[1])
    return {
        "files": {
            path: "# Mon choix\n\nTODO: comparer les options et justifier.\n"
            for path in task["expected_outputs"]
        },
        "summary": f"{role}: comprendre le compromis; choisir puis expliquer une option.",
    }


def payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "files": {
            path: "# Choix\n\nOption A versus B; limites et rollback explicites.\n"
            for path in item["files"]
        },
        "explanation": "J’ai comparé les contraintes et motivé mon choix.",
        "observations": "Analyse documentaire; aucun déploiement exécuté.",
        "human_approved": True,
    }


def test_new_projects_default_to_guided_and_all_roles_receive_common_context(tmp_path: Path) -> None:
    project = create_project(ROOT, tmp_path, "guided-project", "Guidé")
    assert contract(project)["mode"] == "guided"
    shared = (ROOT / "agents/_shared/PEDAGOGY.md").read_text()
    assert "huit agents" not in shared and "Gemma" not in shared
    deploy_workspaces(ROOT, tmp_path)
    for role in AGENT_IDS:
        effective = (tmp_path / "workspaces" / role / "AGENTS.md").read_text()
        assert effective.startswith(shared)
        assert "laisser une action" in effective
        assert "compétence acquise" in effective


def test_guidance_does_not_publish_or_complete_work_and_resume_waits_for_learner(
    planned: tuple[Path, Path],
) -> None:
    runtime, project = planned
    initialize(project, goals=["Comparer et vérifier une architecture"])
    calls: list[str] = []

    def guide(role: str, prompt: str, session: str) -> dict[str, Any]:
        calls.append(role)
        assert "Mode guidé" in prompt and "ne valide aucune tâche" in prompt
        snapshots = list((runtime / "workspaces" / role).rglob("contract.json"))
        assert snapshots and read_json(snapshots[-1])["mode"] == "guided"
        return starter(role, prompt, session)

    results = run_project_tasks(ROOT, runtime, project, runner=guide)
    assert results[0]["status"] == "AWAITING_PRACTICE"
    assert calls == ["architecte-solutions"]
    assert read_json(project / "project.json")["status"] == "IN_PROGRESS"
    assert not (project / "deliverables/design-choice/report.md").exists()
    assert not (project / "context/task_results.json").exists()
    assert run_project_tasks(ROOT, runtime, project, runner=guide, resume=True) == []
    assert calls == ["architecte-solutions"]
    item = awaiting(project)[0]
    submitted = submit(ROOT, runtime, project, item["task_id"], payload(item))
    assert submitted["status"] == "PASS"  # Collection only; semantic audit remains separate.
    assert checkpoints(project)[0]["skill_acquired"] is False
    assert checkpoints(project)[0]["runtime_tested"] is False
    assert not awaiting(project)
    run_project_tasks(ROOT, runtime, project, runner=guide)
    assert calls == ["architecte-solutions", "expert-recherche"]
    item = awaiting(project)[0]
    submit(ROOT, runtime, project, item["task_id"], payload(item))
    assert read_json(project / "project.json")["status"] == "VALIDATING"
    assert not (project / "evidence/validation_report.json").exists()


@pytest.mark.parametrize(
    "invalid",
    [
        {"human_approved": False},
        {"explanation": ""},
        {"files": {"deliverables/other/report.md": "No"}},
        {"files": {"../escape": "No"}},
    ],
)
def test_invalid_practice_does_not_promote_or_write(
    planned: tuple[Path, Path],
    invalid: dict[str, Any],
) -> None:
    runtime, project = planned
    initialize(project)
    run_project_tasks(ROOT, runtime, project, runner=starter)
    item = awaiting(project)[0]
    with pytest.raises(ValueError):
        submit(ROOT, runtime, project, item["task_id"], {**payload(item), **invalid})
    assert awaiting(project)
    assert not (project / "deliverables/design-choice/report.md").exists()
    assert ready_tasks(ROOT, project) == []
    with worker_lock(runtime), pytest.raises(ValueError, match="actif"):
        submit(ROOT, runtime, project, item["task_id"], payload(item))


def test_existing_projects_without_learning_contract_keep_approved_behavior(
    planned: tuple[Path, Path],
) -> None:
    runtime, project = planned
    (project / "context/learning/contract.json").unlink()
    assert contract(project)["legacy"] is True
    results = run_project_tasks(ROOT, runtime, project, runner=starter)
    assert len(results) == 2 and all(r["status"] == "PASS" for r in results)


def test_guided_plan_cannot_be_audited_before_practice(planned: tuple[Path, Path]) -> None:
    runtime, project = planned
    initialize(project)
    run_project_tasks(ROOT, runtime, project, runner=starter)
    with pytest.raises(ValueError, match="toutes les tâches"):
        transition_project(ROOT, project, "VALIDATING", actor="auditeur-qualite", reason="skip")


@pytest.mark.parametrize("goals", [["x"] * 4, ["x" * 161], "wrong"])
def test_invalid_learning_goals_are_rejected(tmp_path: Path, goals: Any) -> None:
    with pytest.raises(ValueError):
        initialize(tmp_path, goals=goals)
