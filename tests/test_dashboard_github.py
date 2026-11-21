"""Same-origin GitHub control panel: no unsafe implicit network writes."""

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
from clawfedora.dashboard import DashboardServer, make_server
from clawfedora.project_common import read_json, write_json

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def server(
    planned: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch,
) -> Iterator[DashboardServer]:
    runtime, _project = planned
    monkeypatch.setattr(
        dashboard, "urlopen", lambda *_a, **_kw: io.BytesIO(b'{"models":[]}')
    )
    with make_server(ROOT, runtime, 0) as srv:
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        try:
            yield srv
        finally:
            srv.shutdown()
            thread.join(timeout=5)


def request(
    server: DashboardServer, path: str, data: dict[str, Any] | None = None,
    *, origin: bool = True,
) -> tuple[int, Any]:
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=8)
    headers = {"Host": f"127.0.0.1:{server.server_port}"}
    if data is not None:
        headers["Content-Type"] = "application/json"
        if origin:
            headers["Origin"] = f"http://127.0.0.1:{server.server_port}"
    connection.request("GET" if data is None else "POST", path,
                       body=None if data is None else json.dumps(data),
                       headers=headers)
    response = connection.getresponse()
    body = response.read()
    data_result = json.loads(body) if "application/json" in str(
        response.getheader("Content-Type")
    ) else body.decode("utf-8")
    status = response.status
    connection.close()
    return status, data_result


def test_visual_workspace_is_local_static_and_does_not_trigger_writes(
    server: DashboardServer, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        dashboard.github_remote, "create_repository",
        lambda **_args: pytest.fail("GET created repository"),
    )
    for path in ("/github.html", "/github.js", "/github.css"):
        code, text = request(server, path)
        assert code == 200 and text
    assert "Créer un dépôt privé" in request(server, "/github.html")[1]
    assert "GitHub : dépôts et PR" in request(server, "/")[1]


def test_preview_and_read_only_routes_never_require_token(
    server: DashboardServer, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(
        dashboard.github_remote, "_request",
        lambda *_a, **_kw: pytest.fail("unexpected network"),
    )
    status, payload = request(server, "/api/github/create-plan", {
        "name": "BankFlow", "description": "Lab",
    })
    assert status == 200 and payload["mode"] == "OFFLINE_REPOSITORY_PLAN"
    assert payload["visibility"] == "private"
    status, payload = request(server, "/api/github/policy-plan", {
        "repo": "example/infraops", "branch": "main", "kind": "pr-ruleset",
    })
    assert status == 200 and payload["mode"] == "OFFLINE_POLICY_PLAN"


def test_remote_writes_require_same_origin_explicit_approval(
    server: DashboardServer, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        dashboard.github_remote, "create_repository",
        lambda *_args, **_kwargs: pytest.fail("unapproved write"),
    )
    assert request(server, "/api/github/create-apply", {
        "name": "BankFlow",
    }, origin=False)[0] == 403
    assert request(server, "/api/github/create-apply", {
        "name": "BankFlow",
    })[0] == 400
    assert request(server, "/api/github/policy-apply", {
        "repo": "example/infraops",
    })[0] == 400


def test_draft_preview_binds_title_body_and_manifest_before_publication(
    server: DashboardServer, monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = server.runtime / "projects/daily-project"
    manifest = read_json(project / "project.json")
    manifest["status"] = "COMPLETE"
    write_json(project / "project.json", manifest)
    stage = project / "deliverables/github-docs"
    stage.mkdir(parents=True)
    (stage / "README.md").write_text("# Verified draft content\n", encoding="utf-8")
    base = {
        "project_id": "daily-project", "stage": "deliverables/github-docs",
        "repo": "example/infraops", "base_sha": "a" * 40,
        "branch": "atelier/verified-docs", "title": "Proposition vérifiable",
        "body": "Description détaillée, aucune CI artificiellement verte.",
    }
    status, plan = request(server, "/api/github/draft-plan", base)
    assert status == 200 and plan["mode"] == "OFFLINE_DRY_RUN"
    assert len(plan["approval_sha256"]) == 64
    called: list[dict[str, Any]] = []

    def fake(**kwargs: Any) -> dict[str, Any]:
        called.append(kwargs)
        return {"mode": "DRAFT_PR_CREATED", "url": "https://github.com/example/infraops/pull/42"}

    monkeypatch.setattr(dashboard.github_pr, "publish_draft", fake)
    wrong = {
        **base, "title": "Title changed after approval",
        "approve_sha256": plan["approval_sha256"],
        "approve_repo": "example/infraops", "human_approved": True,
    }
    assert request(server, "/api/github/draft-apply", wrong)[0] == 400
    assert called == []
    good = {
        **base, "approve_sha256": plan["approval_sha256"],
        "approve_repo": "example/infraops", "human_approved": True,
    }
    status, response = request(server, "/api/github/draft-apply", good)
    assert status == 201
    assert response["mode"] == "DRAFT_PR_CREATED"
    assert called[0]["approve_manifest"] == plan["manifest_sha256"]


def test_no_publish_from_unfinished_project(server: DashboardServer) -> None:
    status, payload = request(server, "/api/github/draft-plan", {
        "project_id": "daily-project", "stage": "deliverables/nonexistent",
        "repo": "example/infraops", "base_sha": "a" * 40,
        "branch": "atelier/docs", "title": "Example title",
        "body": "Example description",
    })
    assert status == 400
    assert payload["error"]


def test_unknown_action_returns_bounded_error(server: DashboardServer) -> None:
    status, value = request(server, "/api/github/delete-repository", {"repo": "example/repo"})
    assert status == 400
    assert "inconnue" in value["error"]
