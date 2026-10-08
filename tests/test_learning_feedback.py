from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from test_daily_worker import planned as planned
from test_guided_learning import payload, reviewer, starter

from clawfedora.learning import awaiting, initialize, pending_feedback, submit, task_mode
from clawfedora.project_common import read_json, write_json
from clawfedora.project_engine import ready_tasks, record_task_result
from clawfedora.project_worker import run_project_tasks

ROOT = Path(__file__).resolve().parents[1]


def prepare(runtime: Path, project: Path) -> dict[str, Any]:
    initialize(project, mode="guided")
    run_project_tasks(ROOT, runtime, project, runner=starter)
    item = awaiting(project)[0]
    submit(ROOT, runtime, project, item["task_id"], payload(item))
    return item


def test_reviewed_draft_has_matching_proof_and_only_then_unlocks_dependents(
    planned: tuple[Path, Path],
) -> None:
    runtime, project = planned
    item = prepare(runtime, project)
    with pytest.raises(ValueError, match="retour pédagogique requis"):
        record_task_result(
            ROOT,
            project,
            task_id=item["task_id"],
            agent=item["role"],
            status="PASS",
            outputs=[],
            summary="bypass",
        )

    def review(role: str, prompt: str, session: str) -> dict[str, Any]:
        data = json.loads(prompt.split("\n", 1)[1])
        snapshot = Path(data["snapshot"])
        assert (snapshot / "context/project_analysis.json").is_file()
        assert (snapshot / "context/learning/contract.json").is_file()
        assert "Option A" in (snapshot / next(iter(item["files"]))).read_text()
        return reviewer(role, prompt, session)

    result = run_project_tasks(ROOT, runtime, project, runner=review)
    assert result[0]["status"] == "REVIEWED"
    assert result[0]["feedback"]["runtime_tested"] is False
    assert result[0]["feedback"]["skill_acquired"] is False
    receipt = project / "evidence/design-choice/learning-feedback.json"
    assert receipt.is_file()
    assert ready_tasks(ROOT, project)[0]["task_id"] == "research-check"
    history = read_json(project / "evidence/task_results.json")["results"]
    assert "evidence/design-choice/learning-feedback.json" in history[-1]["outputs"]


def test_correction_preserves_draft_and_waits_for_resubmission(planned: tuple[Path, Path]) -> None:
    runtime, project = planned
    item = prepare(runtime, project)

    def revise(role: str, prompt: str, session: str) -> dict[str, Any]:
        value = reviewer(role, prompt, session)
        value.update(
            verdict="REVISE",
            feedback="Le rollback manque.",
            next_action="Explique comment revenir au choix précédent.",
        )
        value["criteria"][0]["passed"] = False
        return value

    result = run_project_tasks(ROOT, runtime, project, runner=revise)
    assert result[0]["status"] == "AWAITING_PRACTICE"
    assert not (project / next(iter(item["files"]))).exists()
    assert ready_tasks(ROOT, project) == []
    assert run_project_tasks(ROOT, runtime, project, runner=revise, resume=True) == []
    updated = awaiting(project)[0]
    assert "Option A" in updated["files"][next(iter(item["files"]))]
    submit(ROOT, runtime, project, item["task_id"], payload(updated))
    assert len(pending_feedback(project)[0]["submissions"]) == 2
    assert run_project_tasks(ROOT, runtime, project, runner=reviewer)[0]["status"] == "REVIEWED"


@pytest.mark.parametrize("problem", ["contradiction", "missing-criteria", "write", "static-fail"])
def test_false_or_mutating_review_does_not_publish(
    planned: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    problem: str,
) -> None:
    runtime, project = planned
    item = prepare(runtime, project)
    if problem == "static-fail":
        checkpoint = pending_feedback(project)[0]
        checkpoint["files"] = {"deliverables/design-choice/report.md": "---\nbad: [\n---"}
        # Force a deterministic blocking controller result independently of optional binaries.
        monkeypatch.setattr("clawfedora.learning_feedback.lint", lambda *_args: {"status": "FAIL"})
        # Use YAML format for this test's approved output.
        packet_path = project / "context/tasks/design-choice.json"
        packet = read_json(packet_path)
        packet["task"]["expected_outputs"] = ["deliverables/design-choice/report.yaml"]
        write_json(packet_path, packet)
        checkpoint["files"] = {"deliverables/design-choice/report.yaml": "bad: ["}
        write_json(project / "context/learning/tasks/design-choice.json", checkpoint)

    def bad(role: str, prompt: str, session: str) -> dict[str, Any]:
        value = reviewer(role, prompt, session)
        if problem == "contradiction":
            value["criteria"][0]["passed"] = False
        elif problem == "missing-criteria":
            value["criteria"] = []
        elif problem == "write":
            snapshot = Path(json.loads(prompt.split("\n", 1)[1])["snapshot"])
            path = snapshot / next(iter(item["files"]))
            path.chmod(0o600)
            path.write_text("silently corrected")
        return value

    with pytest.raises(ValueError):
        run_project_tasks(ROOT, runtime, project, runner=bad)
    assert pending_feedback(project)
    assert not (project / "context/task_results.json").exists()
    assert not (project / next(iter(item["files"]))).exists()


def test_feedback_retry_budget_resets_only_on_human_resubmission(planned: tuple[Path, Path]) -> None:
    runtime, project = planned
    item = prepare(runtime, project)
    count = 0

    def failing(*_args: Any) -> dict[str, Any]:
        nonlocal count
        count += 1
        raise ValueError("model unavailable")

    for _ in range(3):
        with pytest.raises(ValueError):
            run_project_tasks(ROOT, runtime, project, runner=failing)
    assert count == 2
    submit(ROOT, runtime, project, item["task_id"], payload(item))
    assert pending_feedback(project)[0]["feedback_attempts"] == 0
    run_project_tasks(ROOT, runtime, project, runner=reviewer)


def test_adaptive_support_uses_approved_plan_and_global_override(planned: tuple[Path, Path]) -> None:
    _runtime, project = planned
    initialize(project, mode="adaptive")
    assert task_mode(project, {"role": "architecte-solutions"}) == "direct"
    assert task_mode(project, {"role": "redacteur-pedagogique"}) == "direct"
    assert task_mode(project, {"role": "architecte-solutions", "learning_mode": "guided"}) == "direct"
    assert task_mode(project, {"role": "architecte-solutions", "learning_mode": "guided", "practice_opt_in": "true"}) == "direct"
    assert task_mode(project, {"role": "architecte-solutions", "learning_mode": "guided", "practice_opt_in": True}) == "guided"
    initialize(project, mode="guided")
    assert task_mode(project, {"role": "expert-recherche", "learning_mode": "direct"}) == "guided"
