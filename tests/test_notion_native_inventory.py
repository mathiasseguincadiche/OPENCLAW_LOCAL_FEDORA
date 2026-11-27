"""Native inventory is bounded, read-only and fails closed on incomplete traversal."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from clawfedora import notion_native_inventory as ni

ROOT = "a" * 32
PAGE = "b" * 32
DB = "c" * 32
SOURCE = "d" * 32
VIEW = "e" * 32
BLOCK = "f" * 32


def _parent(kind: str, ident: str) -> dict[str, str]:
    return {"type": kind, kind: ident}


def _block(ident: str, kind: str, parent: str, **payload: Any) -> dict[str, Any]:
    return {"id": ident, "object": "block", "type": kind, kind: payload,
            "parent": _parent("page_id", parent), "has_children": False}


def _list(*items: dict[str, Any], cursor: str | None = None) -> dict[str, Any]:
    return {"results": list(items), "has_more": cursor is not None, "next_cursor": cursor}


def _fake(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, str]]]:
    calls: list[tuple[str, dict[str, str]]] = []
    responses = {
        f"/v1/pages/{ROOT}": {"id": ROOT, "object": "page"},
        f"/v1/pages/{PAGE}": {"id": PAGE, "object": "page",
                             "parent": _parent("page_id", ROOT)},
        f"/v1/blocks/{PAGE}/children": _list(
            _block(BLOCK, "paragraph", PAGE, rich_text=[{"plain_text": "privé"}]),
        ),
        f"/v1/databases/{DB}": {"id": DB, "object": "database",
                               "parent": _parent("page_id", ROOT),
                               "data_sources": [{"id": SOURCE}]},
        f"/v1/data_sources/{SOURCE}": {
            "id": SOURCE, "object": "data_source", "parent": _parent("database_id", DB),
            "properties": {"Suivi": {"type": "rollup"}, "Module": {"type": "relation"}},
        },
        "/v1/views": _list({"id": VIEW}),
        f"/v1/views/{VIEW}": {"id": VIEW, "object": "view",
                             "parent": _parent("database_id", DB), "type": "gallery"},
    }

    def get(path: str, params: dict[str, str]) -> dict[str, Any]:
        calls.append((path, dict(params)))
        if path == f"/v1/blocks/{ROOT}/children":
            if "start_cursor" not in params:
                return _list(_block(PAGE, "child_page", ROOT), cursor="next")
            return _list(_block(DB, "child_database", ROOT))
        return responses[path]

    monkeypatch.setattr(ni, "_get", get)
    monkeypatch.setattr(ni.time, "sleep", lambda _: None)
    return calls


def test_recursive_pages_pagination_database_relations_and_views(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _fake(monkeypatch)
    report = ni.capture(ROOT)
    assert report["counts"] == {
        "page": 2, "block": 3, "database": 1, "data_source": 1, "view": 1,
    }
    assert report["remote_write"] is False and report["native_render_verified"] is False
    assert "privé" not in json.dumps(report, ensure_ascii=False)
    schema = next(r for r in report["objects"] if r["category"] == "data_source")
    assert schema["property_types"] == {"rollup": 1, "relation": 1}
    assert ("/v1/views", {"database_id": DB, "page_size": "100"}) in calls
    assert ni.capture(ROOT)["structure_sha256"] == report["structure_sha256"]


def test_scope_and_repeated_cursor_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake(monkeypatch)
    old = ni._get

    def foreign(path: str, params: dict[str, str]) -> dict[str, Any]:
        if path == f"/v1/pages/{PAGE}":
            return {"id": PAGE, "object": "page", "parent": _parent("page_id", DB)}
        return old(path, params)

    monkeypatch.setattr(ni, "_get", foreign)
    with pytest.raises(ValueError, match="hors du wiki"):
        ni.capture(ROOT)
    monkeypatch.setattr(ni, "_get", lambda *_: _list({"id": PAGE}, cursor="repeat"))
    with pytest.raises(ValueError, match="curseur"):
        ni.Inventory().list_items("/v1/views", {"database_id": DB})


def test_no_network_in_plan_and_private_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _fake(monkeypatch)
    tmp_path.chmod(0o700)
    out = tmp_path / "inventory.json"
    args = ["--page", ROOT, "--output", str(out)]
    assert ni.main(args) == 0 and calls == [] and not out.exists()
    assert ni.main([*args, "--capture"]) == 0
    assert out.stat().st_mode & 0o777 == 0o600
    assert json.loads(out.read_text())["root_page"] == ROOT
    before = len(calls)
    assert ni.main([*args, "--capture"]) == 2 and len(calls) == before


def test_transport_refuses_other_endpoints_before_reading_token() -> None:
    for path, params in [
        ("/v1/search", {}), ("/v1/views", {}),
        (f"/v1/pages/{ROOT}", {"start_cursor": "x"}),
        (f"/v1/blocks/{ROOT}/children", {"start_cursor": "x&evil=1"}),
    ]:
        with pytest.raises(ValueError, match="endpoint"):
            ni._get(path, params)


def test_hosted_urls_are_volatile_but_external_url_is_not() -> None:
    first = {"file": {"url": "https://private/one", "expiry_time": "now"},
             "external": {"url": "https://example.org"}}
    second = {"file": {"url": "https://private/two", "expiry_time": "later"},
              "external": {"url": "https://example.org"}}
    assert ni._stable(first) == ni._stable(second)
    second["external"]["url"] = "https://changed.example.org"
    assert ni._stable(first) != ni._stable(second)
