"""Loopback-only Notion dashboard: real preview/apply adapter, mocked remote API."""

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

from clawfedora import dashboard, notion_panel, notion_write, source_connectors
from clawfedora.dashboard import DashboardServer, make_server

ROOT = Path(__file__).resolve().parents[1]
PAGE = "a" * 32
FIRST = "b" * 32
SECOND = "c" * 32
PROTECTED = "d" * 32


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
    connection.request(
        "GET" if data is None else "POST", path,
        body=None if data is None else json.dumps(data), headers=headers,
    )
    response = connection.getresponse()
    body = response.read()
    content_type = str(response.getheader("Content-Type"))
    decoded = json.loads(body) if "application/json" in content_type else body.decode("utf-8")
    code = response.status
    connection.close()
    return code, decoded


def _mock_notion(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {
        "texts": {FIRST: "Présentation initiale", SECOND: "Instructions"},
        "version": {FIRST: "2026-11-21T01:00:00Z", SECOND: "2026-11-21T01:00:00Z"},
        "patches": [], "drift": False,
    }

    def blocks(_page: str) -> list[dict[str, Any]]:
        assert _page == PAGE
        result: list[dict[str, Any]] = []
        for block_id, kind in ((FIRST, "paragraph"), (SECOND, "heading_2")):
            actual = state["texts"][block_id]
            result.append({
                "id": block_id, "type": kind, "has_children": False,
                "archived": False,
                kind: {"rich_text": [{"type": "text", "plain_text": actual}]},
            })
        result.append({
            "id": PROTECTED, "type": "child_page", "has_children": True,
            "archived": False, "child_page": {"title": "Exercice privé"},
        })
        if state["drift"]:
            result.reverse()
        return result

    def api(
        method: str, resource: str, *, write: bool = False,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if method == "GET" and resource == f"/v1/pages/{PAGE}":
            return {"id": PAGE, "archived": False}
        if method == "GET" and resource.startswith("/v1/blocks/"):
            block_id = resource.rsplit("/", 1)[-1]
            assert block_id in state["texts"]
            actual = state["texts"][block_id]
            kind = "paragraph" if block_id == FIRST else "heading_2"
            return {
                "id": block_id, "type": kind, "has_children": False,
                "archived": False, "last_edited_time": state["version"][block_id],
                "parent": {"type": "page_id", "page_id": PAGE},
                kind: {"rich_text": [{
                    "type": "text", "plain_text": actual, "href": None,
                    "text": {"content": actual, "link": None},
                    "annotations": {"color": "default", "bold": False,
                                    "italic": False, "underline": False,
                                    "strikethrough": False, "code": False},
                }]},
            }
        if method == "PATCH" and resource.startswith("/v1/blocks/"):
            assert write is True and body is not None
            block_id = resource.rsplit("/", 1)[-1]
            state["patches"].append(block_id)
            state["texts"][block_id] = body[next(iter(body))]["rich_text"][0]["text"]["content"]
            state["version"][block_id] = "2026-11-21T01:03:00Z"
            return {"id": block_id}
        pytest.fail("unexpected request: " + method + " " + resource)

    monkeypatch.setattr(notion_write, "_request", api)
    monkeypatch.setattr(source_connectors, "_notion_children", blocks)
    return state


def test_local_pages_and_navigation_are_static(
    server: DashboardServer, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        notion_panel, "inspect", lambda *_args: pytest.fail("GET performed Notion read"),
    )
    for page in ("/notion.html", "/notion.js", "/notion.css"):
        status, text = request(server, page)
        assert status == 200 and text
    assert "Préparer une révision Notion" in request(server, "/notion.html")[1]
    assert "Notion : wiki et révisions" in request(server, "/")[1]


def test_inspect_and_preview_are_read_only(
    server: DashboardServer, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _mock_notion(monkeypatch)
    code, result = request(server, "/api/notion/inspect", {"page": PAGE})
    assert code == 200
    assert result["mode"] == "NOTION_STRUCTURE_READ_ONLY"
    assert result["protected_count"] == 1
    assert result["editable_count"] == 2
    assert result["blocks"][0]["excerpt"] == "Présentation initiale"
    assert state["patches"] == []
    code, plan = request(server, "/api/notion/plan", {
        "page": PAGE, "edits": [
            {"block_id": FIRST, "text": "Présentation revue"},
            {"block_id": SECOND, "text": "Procédure vérifiée"},
        ],
    })
    assert code == 200
    assert plan["mode"] == "BATCH_PREVIEW_ONLY"
    assert len(plan["plan_id"]) == 32
    assert len(plan["manifest_sha256"]) == 64
    assert "plan_file" not in plan
    assert "Présentation initiale" in plan["edits"][0]["diff"]
    assert state["patches"] == []


def test_writes_require_same_origin_and_exact_human_approval(
    server: DashboardServer, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _mock_notion(monkeypatch)
    status, plan = request(server, "/api/notion/plan", {
        "page": PAGE, "edits": [{"block_id": FIRST, "text": "Texte accepté"}],
    })
    assert status == 200
    proposed = {
        "plan_id": plan["plan_id"], "page": PAGE,
        "approve_page": PAGE,
        "approve_manifest": plan["manifest_sha256"],
        "human_approved": True,
    }
    assert request(server, "/api/notion/apply", proposed, origin=False)[0] == 403
    assert request(server, "/api/notion/apply", {
        **proposed, "human_approved": False,
    })[0] == 400
    assert request(server, "/api/notion/apply", {
        **proposed, "approve_manifest": "0" * 64,
    })[0] == 400
    assert request(server, "/api/notion/apply", {
        **proposed, "approve_page": SECOND,
    })[0] == 400
    assert state["patches"] == []
    status, result = request(server, "/api/notion/apply", proposed)
    assert status == 200 and result["mode"] == "BATCH_BLOCKS_API_VERIFIED"
    assert state["texts"][FIRST] == "Texte accepté"
    assert state["patches"] == [FIRST]
    assert request(server, "/api/notion/apply", proposed)[0] == 400
    assert state["patches"] == [FIRST]


def test_conflict_and_bad_selector_are_fail_closed(
    server: DashboardServer, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _mock_notion(monkeypatch)
    status, plan = request(server, "/api/notion/plan", {
        "page": PAGE, "edits": [{"block_id": FIRST, "text": "Brouillon relu"}],
    })
    assert status == 200
    state["drift"] = True
    approved = {
        "plan_id": plan["plan_id"], "page": PAGE,
        "approve_page": PAGE, "approve_manifest": plan["manifest_sha256"],
        "human_approved": True,
    }
    assert request(server, "/api/notion/apply", approved)[0] == 400
    assert state["patches"] == []
    assert request(server, "/api/notion/apply", {
        **approved, "plan_id": "../../secrets",
    })[0] == 400
    assert request(server, "/api/notion/unrecognized", {"page": PAGE})[0] == 400


def test_private_plan_without_secret_or_untrusted_path(
    server: DashboardServer, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_notion(monkeypatch)
    monkeypatch.setenv("NOTION_WRITE_TOKEN", "test-token-never-display")
    status, plan = request(server, "/api/notion/plan", {
        "page": PAGE, "edits": [{"block_id": FIRST, "text": "Texte privé"}],
    })
    assert status == 200
    assert "test-token-never-display" not in json.dumps(plan)
    folder = server.runtime / "state/notion-ui"
    assert folder.stat().st_mode & 0o077 == 0
    saved = folder / (plan["plan_id"] + ".plan.json")
    assert saved.stat().st_mode & 0o077 == 0
    assert "test-token-never-display" not in saved.read_text(encoding="utf-8")


def test_rich_segment_ui_is_static_and_token_free(
    server: DashboardServer, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        notion_panel, "rich_inspect",
        lambda *_args: pytest.fail("static file triggered a Notion request"),
    )
    code, js = request(server, "/notion-rich.js")
    assert code == 200 and "rich-apply" in js
    code, html = request(server, "/notion.html")
    assert code == 200
    assert "Réviser un segment de texte enrichi" in html
    assert "/notion-rich.js" in html


def test_rich_segment_api_requires_exact_user_approval(
    server: DashboardServer, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _mock_notion(monkeypatch)
    code, details = request(server, "/api/notion/rich-segments", {
        "page": PAGE, "block_id": FIRST,
    })
    assert code == 200 and details["mode"] == "RICH_SEGMENTS_READ_ONLY"
    assert details["segments"][0]["editable"] is True
    code, proposal = request(server, "/api/notion/rich-plan", {
        "page": PAGE, "block_id": FIRST, "segment_index": 0,
        "text": "Présentation contrôlée",
    })
    assert code == 200
    assert proposal["mode"] == "RICH_SEGMENT_PREVIEW_ONLY"
    assert len(proposal["plan_id"]) == 32
    assert state["patches"] == []
    approval = {
        "plan_id": proposal["plan_id"], "page": PAGE, "approve_page": PAGE,
        "approve_manifest": proposal["manifest_sha256"], "human_approved": True,
    }
    assert request(server, "/api/notion/rich-apply", approval, origin=False)[0] == 403
    assert request(server, "/api/notion/rich-apply", {
        **approval, "human_approved": False,
    })[0] == 400
    assert request(server, "/api/notion/rich-apply", {
        **approval, "approve_manifest": "0" * 64,
    })[0] == 400
    assert request(server, "/api/notion/rich-apply", {
        **approval, "approve_page": SECOND,
    })[0] == 400
    assert state["patches"] == []
    code, result = request(server, "/api/notion/rich-apply", approval)
    assert code == 200 and result["mode"] == "RICH_SEGMENT_API_VERIFIED"
    assert state["texts"][FIRST] == "Présentation contrôlée"
    assert state["patches"] == [FIRST]
    assert request(server, "/api/notion/rich-apply", approval)[0] == 400
    assert state["patches"] == [FIRST]


def test_rich_segment_api_rejects_invalid_index_and_no_secret_exposure(
    server: DashboardServer, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _mock_notion(monkeypatch)
    monkeypatch.setenv("NOTION_WRITE_TOKEN", "hidden-test-token")
    bad = {
        "page": PAGE, "block_id": FIRST,
        "segment_index": True, "text": "Impossible",
    }
    assert request(server, "/api/notion/rich-plan", bad)[0] == 400
    good = {**bad, "segment_index": 0, "text": "Édition sûre"}
    code, proposal = request(server, "/api/notion/rich-plan", good)
    assert code == 200
    assert "hidden-test-token" not in json.dumps(proposal)
    assert "plan_file" not in proposal
    assert state["patches"] == []
    assert request(server, "/api/notion/rich-remove", {
        "page": PAGE,
    })[0] == 400
