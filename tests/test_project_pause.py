from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from test_daily_worker import planned as planned

from clawfedora.project_control import clear_pause, progress, request_pause
from clawfedora.project_worker import run_project_tasks

ROOT = Path(__file__).resolve().parents[1]


def test_pause_finishes_current_task_and_resume_skips_passed_tasks(
    planned: tuple[Path, Path],
) -> None:
    runtime, project = planned
    sessions: list[str] = []

    def first(_role: str, prompt: str, session: str) -> dict[str, Any]:
        task = json.loads(prompt.split("\n", 1)[1])
        sessions.append(session)
        request_pause(runtime, project)
        return {
            "files": {task["expected_outputs"][0]: "Original validated collection"},
            "summary": "collecté",
        }

    results = run_project_tasks(ROOT, runtime, project, runner=first)
    assert len(results) == 1 and results[0]["status"] == "PASS"
    assert progress(runtime)["phase"] == "paused" and not progress(runtime)["active"]
    assert run_project_tasks(ROOT, runtime, project, runner=first) == []
    clear_pause(runtime, project)

    def second(role: str, prompt: str, session: str) -> dict[str, Any]:
        assert role == "expert-recherche" and session not in sessions
        task = json.loads(prompt.split("\n", 1)[1])
        return {"files": {task["expected_outputs"][0]: "Second task"}, "summary": "collecté"}

    assert len(run_project_tasks(ROOT, runtime, project, runner=second)) == 1
    assert (
        project / "deliverables/design-choice/report.md"
    ).read_text() == "Original validated collection"
    assert progress(runtime)["phase"] == "awaiting_validation"


def test_interrupted_task_is_detected_and_retried_with_fresh_session(
    planned: tuple[Path, Path],
) -> None:
    runtime, project = planned
    sessions: list[str] = []

    def interrupted(_role: str, _prompt: str, session: str) -> dict[str, Any]:
        sessions.append(session)
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_project_tasks(ROOT, runtime, project, runner=interrupted)
    assert progress(runtime)["phase"] == "interrupted"

    def resumed(_role: str, prompt: str, session: str) -> dict[str, Any]:
        assert session not in sessions
        task = json.loads(prompt.split("\n", 1)[1])
        request_pause(runtime, project)
        return {"files": {task["expected_outputs"][0]: "Fresh result"}, "summary": "repris"}

    result = run_project_tasks(ROOT, runtime, project, runner=resumed)
    assert result[0]["task_id"] == "design-choice" and result[0]["status"] == "PASS"
