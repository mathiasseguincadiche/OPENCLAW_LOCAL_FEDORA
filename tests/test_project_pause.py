from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from test_daily_worker import planned as planned

from clawfedora import artifact_exchange, project_engine
from clawfedora.project_common import read_json, sha256_file
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


@pytest.mark.parametrize("boundary", ["consumer-bundle", "assignment", "history"])
def test_resume_finishes_publication_without_running_the_producer_again(
    planned: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, boundary: str,
) -> None:
    runtime, project = planned
    producer = "design-choice"
    first_output = "deliverables/design-choice/report.md"
    bundle = project / "context/exchange/design-choice/self/run-001"
    consumer_bundle = project / "context/exchange/research-check/dependencies/design-choice/run-001"
    history = project / "evidence/task_results.json"
    journal = project / project_engine.TASK_PROMOTION_PATH
    calls: list[str] = []

    def runner(role: str, prompt: str, _session: str) -> dict[str, Any]:
        task = json.loads(prompt.split("\n", 1)[1])
        calls.append(role)
        return {"files": {task["expected_outputs"][0]: f"Version de {role}"}, "summary": "collecté"}

    write_engine = project_engine.write_json
    write_exchange = artifact_exchange.write_json

    def interrupt_state(path: Path, value: dict[str, Any]) -> None:
        if boundary == "assignment" and path.name == "task_assignments.json":
            raise KeyboardInterrupt
        write_engine(path, value)
        if boundary == "history" and path == history:
            raise KeyboardInterrupt

    def interrupt_bundle(path: Path, value: dict[str, Any]) -> None:
        if boundary == "consumer-bundle" and consumer_bundle.parent in path.parents:
            raise KeyboardInterrupt
        write_exchange(path, value)

    with monkeypatch.context() as intercept:
        intercept.setattr(project_engine, "write_json", interrupt_state)
        intercept.setattr(artifact_exchange, "write_json", interrupt_bundle)
        with pytest.raises(KeyboardInterrupt):
            run_project_tasks(ROOT, runtime, project, runner=runner)
    assert progress(runtime)["phase"] == "interrupted"
    assert journal.is_file() and bundle.is_dir()
    original = sha256_file(bundle / "manifest.json")
    if boundary == "consumer-bundle":
        staging = consumer_bundle.with_name(".run-001.staging")
        staging.mkdir()
        (staging / "incomplet").write_text("copie interrompue", encoding="utf-8")

    results = run_project_tasks(ROOT, runtime, project, runner=runner, resume=True)
    assert calls == ["architecte-solutions", "expert-recherche"]
    assert [row["task_id"] for row in results] == [producer, "research-check"]
    assert all(row["attempt"] == 1 and row["status"] == "PASS" for row in results)
    assert not journal.exists()
    assert sha256_file(bundle / "manifest.json") == original
    assert (project / first_output).read_text() == "Version de architecte-solutions"
    assert [row["task_id"] for row in read_json(history)["results"]] == [producer, "research-check"]
    indexed = read_json(project / "context/exchange/index.json")["records"]
    assert len({row["bundle"] for row in indexed}) == len(indexed) == 3


def test_resume_refuses_modified_output_of_an_interrupted_publication(
    planned: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, project = planned
    original_write = project_engine.write_json

    def collect(_role: str, prompt: str, _session: str) -> dict[str, Any]:
        task = json.loads(prompt.split("\n", 1)[1])
        return {"files": {task["expected_outputs"][0]: "# Rapport"}, "summary": "collecté"}

    def interrupt(path: Path, value: dict[str, Any]) -> None:
        if path.name == "task_assignments.json":
            raise KeyboardInterrupt
        original_write(path, value)

    with monkeypatch.context() as intercept:
        intercept.setattr(project_engine, "write_json", interrupt)
        with pytest.raises(KeyboardInterrupt):
            run_project_tasks(ROOT, runtime, project, runner=collect)
    (project / "deliverables/design-choice/report.md").write_text("# Changé", encoding="utf-8")

    def never(*_args: Any) -> dict[str, Any]:
        pytest.fail("le modèle ne doit pas être relancé sur une publication divergente")

    with pytest.raises(ValueError, match="sorties modifiées"):
        run_project_tasks(ROOT, runtime, project, runner=never, resume=True)
    assert (project / project_engine.TASK_PROMOTION_PATH).is_file()
    assert not (project / "deliverables/research-check/report.md").exists()
