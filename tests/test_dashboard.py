from __future__ import annotations

import io
import json
import threading
from collections.abc import Iterator
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

import pytest
from test_daily_worker import planned as planned

from clawfedora import dashboard
from clawfedora.dashboard import DashboardServer, make_server, snapshot
from clawfedora.project_control import is_paused

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def server(planned: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch) -> Iterator[DashboardServer]:
    runtime, _project = planned
    monkeypatch.setattr(dashboard, "urlopen", lambda *_args, **_kwargs: io.BytesIO(b'{"models":[]}'))
    with make_server(ROOT, runtime, 0) as value:
        thread = threading.Thread(target=value.serve_forever, daemon=True)
        thread.start()
        try:
            yield value
        finally:
            value.shutdown()
            thread.join(timeout=5)


def request(
    server: DashboardServer,
    path: str,
    data: Any = None,
    *,
    origin: bool = True,
    host: str | None = None,
) -> tuple[int, Any]:
    client = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    headers = {"Host": host or f"127.0.0.1:{server.server_port}"}
    if data is not None:
        headers["Content-Type"] = "application/json"
        if origin:
            headers["Origin"] = f"http://127.0.0.1:{server.server_port}"
    client.request(
        "GET" if data is None else "POST",
        path,
        body=None if data is None else json.dumps(data),
        headers=headers,
    )
    response = client.getresponse()
    raw = response.read()
    content = (
        json.loads(raw)
        if "application/json" in str(response.getheader("Content-Type"))
        else raw.decode()
    )
    status = response.status
    client.close()
    return status, content


def test_reading_dashboard_never_runs_a_model(
    server: DashboardServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        dashboard, "run_project_tasks", lambda *_args: pytest.fail("GET launched worker")
    )
    status, data = request(server, "/api/status")
    assert status == 200 and data["projects"][0]["total"] == 2
    assert not data["worker"]["active"] and data["models"] == []
    for path in ("/", "/dashboard.js", "/dashboard.css"):
        status, text = request(server, path)
        assert status == 200 and text
    assert request(server, "/unknown")[0] == 404
    assert request(server, "/api/status", host="evil.example")[0] == 403


def test_diagram_download_preserves_extension_with_encoded_filename(server: DashboardServer) -> None:
    from urllib.parse import quote, urlencode

    project = server.runtime / "projects/daily-project"
    name = 'schéma "réseau".drawio'
    file = project / "diagrams/design-choice" / name
    file.parent.mkdir(exist_ok=True)
    file.write_text("<mxfile/>")
    client = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    client.request(
        "GET",
        "/api/artifact?"
        + urlencode(
            {
                "project": project.name,
                "path": file.relative_to(project).as_posix(),
            }
        ),
    )
    response = client.getresponse()
    assert response.status == 200
    assert response.getheader("Content-Disposition") == "attachment; filename*=UTF-8''" + quote(
        name, safe=""
    )
    assert response.read() == b"<mxfile/>"
    client.close()


def test_pause_notes_and_search_are_usable_through_local_api(server: DashboardServer) -> None:
    project = server.runtime / "projects/daily-project"
    data = {"project_id": "daily-project"}
    assert request(server, "/api/pause", data, origin=False)[0] == 403
    assert request(server, "/api/pause", data)[0] == 202
    assert is_paused(server.runtime, project)
    status, report = request(
        server,
        "/api/remember",
        {**data, "title": "Mémoire", "text": "Vulkan reste notre choix quotidien."},
    )
    assert status == 200 and report["documents"] == 2
    status, hits = request(server, "/api/search?project=daily-project&q=Vulkan")
    assert status == 200 and hits[0]["kind"] == "decision"
    assert request(server, "/api/index", data)[0] == 200
    assert request(server, "/api/search?project=../escape&q=secret")[0] == 400
    assert request(server, "/api/index", {"project_id": "../escape"})[0] == 400
    assert request(server, "/api/index", {"project_id": "absent-project"})[0] == 400
    assert request(server, "/../pyproject.toml")[0] == 404
    assert request(server, "/api/unknown", data)[0] == 404
    assert request(server, "/api/remember", {**data, "title": "", "text": "bad"})[0] == 400


def test_dashboard_rejects_existing_project_symlink(server: DashboardServer, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "project.json").write_text("{}")
    (server.runtime / "projects/linked-project").symlink_to(outside, target_is_directory=True)
    assert request(server, "/api/search?project=linked-project&q=secret")[0] == 400
    assert request(server, "/api/index", {"project_id": "linked-project"})[0] == 400


def test_resume_requires_click_assigned_plan_and_daily_profile(
    server: DashboardServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    called = threading.Event()
    monkeypatch.setattr(dashboard, "run_project_tasks", lambda *_args, **_kwargs: called.set() or [])
    data = {"project_id": "daily-project"}
    assert request(server, "/api/resume", data)[0] == 202
    assert called.wait(timeout=2)
    (server.runtime / "state").mkdir(exist_ok=True)
    (server.runtime / "state/gaming-mode").touch()
    assert request(server, "/api/resume", data)[0] == 400
    monkeypatch.setattr(dashboard, "worker_active", lambda _runtime: True)
    assert request(server, "/api/resume", data)[0] == 400


def test_async_failure_is_visible_to_user(
    server: DashboardServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failed(*_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        raise ValueError("Modèle non provisionné")

    monkeypatch.setattr(dashboard, "run_project_tasks", failed)
    handler = object.__new__(dashboard.DashboardHandler)
    handler.server = server
    handler._run(server.runtime / "projects/daily-project")
    assert request(server, "/api/status")[1]["errors"]["daily-project"] == "Modèle non provisionné"
    monkeypatch.setattr(
        dashboard,
        "run_project_tasks",
        lambda *_args, **_kwargs: [{"status": "FAIL", "summary": "Réponse invalide"}],
    )
    handler._run(server.runtime / "projects/daily-project")
    assert server.errors["daily-project"] == "Réponse invalide"


def test_missing_ollama_is_reported_and_does_not_load_anything(
    planned: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, _project = planned

    def unavailable(*_args: Any, **_kwargs: Any) -> Any:
        raise OSError("service arrêté")

    monkeypatch.setattr(dashboard, "urlopen", unavailable)
    value = snapshot(ROOT, runtime)
    assert value["ollama_available"] is False and value["models"] == []
    monkeypatch.setattr(dashboard, "urlopen", lambda *_args, **_kwargs: io.BytesIO(b"x" * 64001))
    assert snapshot(ROOT, runtime)["ollama_available"] is False


def test_workshop_shows_cloud_state_pause_models_and_budget(
    server: DashboardServer, planned: tuple[Path, Path]
) -> None:
    from clawfedora import project_cloud
    from clawfedora.cloud_state import write_activation

    runtime, project = planned
    (runtime / "state").mkdir(exist_ok=True)
    _, data = request(server, "/api/status")
    assert data["cloud"] == {"ready": False, "reason": "cloud non activé"}
    assert data["projects"][0]["cloud"]["state"] == "none"
    write_activation(runtime, {"privacy_filter": "x", "budget_guard": "x"})
    project_cloud.grant(ROOT, runtime, project, acknowledged=True)
    project_cloud.write_pause(runtime, project, "budget_refused", "plafond atteint", "design-choice")
    _, data = request(server, "/api/status")
    assert data["cloud"]["ready"] and data["cloud"]["budget"]["cap_eur"] == 25
    brief = data["projects"][0]["cloud"]
    assert brief["state"] == "granted" and brief["pause"]["code"] == "budget_refused"
    status, detail = request(server, "/api/cloud?project=daily-project")
    assert status == 200 and detail["pause"]["message"] == "plafond atteint"
    assert "ne repasse jamais en local" in detail["consent_text"]


def test_cloud_approval_through_the_api_needs_both_explicit_flags_and_a_local_origin(
    server: DashboardServer, planned: tuple[Path, Path]
) -> None:
    from clawfedora import project_cloud
    from clawfedora.cloud_state import write_activation

    runtime, project = planned
    (runtime / "state").mkdir(exist_ok=True)
    body = {"project_id": "daily-project", "human_approved": True, "acknowledged": True}
    assert request(server, "/api/cloud-approve", body, origin=False)[0] == 403
    for partial in ({"human_approved": True}, {"acknowledged": True}, {}):
        status, _ = request(server, "/api/cloud-approve", {"project_id": "daily-project", **partial})
        assert status == 400
    # The cloud is not activated: even a complete request is refused.
    status, answer = request(server, "/api/cloud-approve", body)
    assert status == 400 and "cloud indisponible" in answer["error"]
    write_activation(runtime, {"privacy_filter": "x", "budget_guard": "x"})
    assert request(server, "/api/cloud-approve", body)[0] == 202
    assert project_cloud.consent_state(ROOT, runtime, project)["state"] == "granted"
    assert request(server, "/api/cloud-revoke", {"project_id": "daily-project"})[0] == 202
    assert project_cloud.consent_state(ROOT, runtime, project)["state"] == "none"


def test_dashboard_page_has_the_cloud_panels(server: DashboardServer) -> None:
    _, page = request(server, "/")
    assert 'id="cloud-budget"' in page and 'id="cloud"' in page
    _, script = request(server, "/dashboard.js")
    assert "/api/cloud-approve" in script and "/api/cloud-revoke" in script
