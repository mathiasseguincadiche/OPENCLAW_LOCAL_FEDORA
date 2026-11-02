"""A08: a timeout or an unexpected error ends every background job in a visible state.

A model call can raise ``subprocess.TimeoutExpired`` (OpenClaw CLI killed after its
deadline) or any other exception. Before the fix, chat and dashboard threads only caught a
few types: the thread died and the job stayed "en cours" for ever. No model is called here.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
from test_daily_worker import planned as planned

from clawfedora import chat_flow, chat_run, dashboard
from clawfedora.project_common import failure_message, write_json

TIMEOUT = subprocess.TimeoutExpired(["openclaw", "agent"], 630)


def _project(tmp_path: Path) -> tuple[Path, Path]:
    runtime = tmp_path / "runtime"
    project = runtime / "projects/demo-project"
    project.mkdir(parents=True)
    return runtime, project


def test_failure_message_names_timeouts_and_unexpected_errors() -> None:
    assert failure_message(TIMEOUT).startswith("délai dépassé (630 s)")
    assert failure_message(ValueError("Modèle absent")) == "Modèle absent"
    assert failure_message(TypeError("bad")) == "erreur interne (TypeError) : bad"
    assert failure_message(ZeroDivisionError()) == "erreur interne (ZeroDivisionError)"
    assert len(failure_message(ValueError("x" * 5000))) == 1000


@pytest.mark.parametrize(
    ("error", "expected"),
    [(TIMEOUT, "délai dépassé"), (TypeError("champ inattendu"), "erreur interne (TypeError)")],
)
def test_chat_job_ends_failed_instead_of_running_for_ever(
    tmp_path: Path, error: BaseException, expected: str
) -> None:
    runtime, project = _project(tmp_path)

    def action() -> str:
        raise error

    chat_run._start(runtime, project, "run", action)
    chat_run.wait_idle()
    line = chat_run.job_line(runtime, project.name)
    assert "en échec" in line and expected in line
    assert "en cours" not in line


def test_chat_job_left_running_by_a_dead_process_is_reported_interrupted(
    tmp_path: Path,
) -> None:
    runtime, project = _project(tmp_path)
    path = runtime / "state/chat-jobs/demo-project.json"
    path.parent.mkdir(parents=True)
    # What a crash or restart leaves behind: "running" and no thread in this process.
    write_json(path, {"project_id": "demo-project", "kind": "validation", "status": "running"})
    line = chat_run.job_line(runtime, project.name)
    assert "interrompu" in line and "relancez" in line


def test_chat_job_still_running_is_reported_running(tmp_path: Path) -> None:
    import threading

    runtime, project = _project(tmp_path)
    release = threading.Event()
    chat_run._start(runtime, project, "run", lambda: release.wait(5) and "ok")
    try:
        assert "en cours" in chat_run.job_line(runtime, project.name)
    finally:
        release.set()
        chat_run.wait_idle()
    assert "terminé" in chat_run.job_line(runtime, project.name)


def test_chat_draft_timeout_is_a_visible_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, project = _project(tmp_path)

    def timed_out(*_args: Any, **_kwargs: Any) -> None:
        raise TIMEOUT

    monkeypatch.setattr(chat_flow.project_cloud, "project_runner", lambda *_a, **_k: None)
    monkeypatch.setattr(chat_flow.project_ui, "propose", timed_out)
    flow = chat_flow.Flow(tmp_path, runtime, project.name, None, lambda **_k: {})
    chat_flow._draft_job(flow, project, "analysis")
    line = chat_flow.job_line(runtime, project.name)
    assert line is not None and "a échoué" in line and "délai dépassé" in line


@pytest.mark.parametrize("error", [TIMEOUT, TypeError("réponse inattendue")])
def test_dashboard_jobs_record_timeouts_and_unexpected_errors(
    planned: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, error: BaseException
) -> None:
    runtime, project = planned

    def failing(*_args: Any, **_kwargs: Any) -> Any:
        raise error

    monkeypatch.setattr(dashboard, "run_project_tasks", failing)
    monkeypatch.setattr(dashboard.project_ui, "propose", failing)
    server = dashboard.make_server(Path(__file__).resolve().parents[1], runtime, 0)
    try:
        handler = object.__new__(dashboard.DashboardHandler)
        handler.server = server
        handler._run(project)
        assert server.errors[project.name] == failure_message(error)
        server.errors.clear()
        handler._prepare(project, "analysis")
        assert server.errors[project.name] == failure_message(error)
    finally:
        server.server_close()


def test_bridge_answers_a_model_timeout_with_a_clear_409_and_frees_the_lock(
    tmp_path: Path,
) -> None:
    import json
    import threading

    from test_webui_bridge import TOKEN, request

    from clawfedora.project_worker import worker_lock
    from clawfedora.webui_bridge import MODEL_IDS, make_server

    def runner(_role: str, _prompt: str, _session: str) -> dict[str, Any]:
        raise TIMEOUT

    root = Path(__file__).resolve().parents[1]
    with make_server(root, tmp_path, TOKEN, 0, runner=runner) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            payload = {
                "model": MODEL_IDS[0],
                "messages": [{"role": "user", "content": "Comment diagnostiquer ?"}],
            }
            status, raw = request(server, "/v1/chat/completions", payload)
            assert status == 409
            assert "délai dépassé" in json.loads(raw)["error"]["message"]
            with worker_lock(tmp_path):  # released: the next generation may start
                pass
        finally:
            server.shutdown()
            thread.join(timeout=5)
