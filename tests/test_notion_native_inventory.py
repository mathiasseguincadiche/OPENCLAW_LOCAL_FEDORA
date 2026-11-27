"""Native inventory is bounded, read-only and fails closed on incomplete traversal."""
from __future__ import annotations

import json
import os
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from clawfedora import notion_inventory_diff as nd
from clawfedora import notion_native_inventory as ni
from clawfedora import notion_write as nw

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


def _row(report: dict[str, Any], category: str, ident: str) -> dict[str, Any]:
    return next(r for r in report["objects"] if (r["category"], r["id"]) == (category, ident))


def _seal(report: dict[str, Any]) -> None:
    report["counts"] = dict(Counter(r["category"] for r in report["objects"]))
    report["structure_sha256"] = nw._digest(report["objects"])
    if report["schema"] == ni.SCHEMA:
        report.pop("inventory_sha256", None)
        report["inventory_sha256"] = nw._digest(report)


def test_diff_detects_move_and_effective_content_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake(monkeypatch)
    get = ni._get
    before = ni.capture(ROOT)

    def revised(path: str, params: dict[str, str]) -> dict[str, Any]:
        if path == f"/v1/blocks/{PAGE}/children":
            return _list()
        if path == f"/v1/blocks/{ROOT}/children" and "start_cursor" in params:
            return _list(
                _block(DB, "child_database", ROOT),
                _block(BLOCK, "paragraph", ROOT, rich_text=[{"plain_text": "nouveau texte privé"}]),
            )
        if path == f"/v1/data_sources/{SOURCE}":
            data = deepcopy(get(path, params))
            data["properties"]["Nouveau nom"] = data["properties"].pop("Module")
            return data
        if path == f"/v1/views/{VIEW}":
            return {**get(path, params), "filter": {"test": "secret"}}
        return get(path, params)

    monkeypatch.setattr(ni, "_get", revised)
    after = ni.capture(ROOT)
    report = nd.compare(before, after, root_page=ROOT)
    modified = {(r["category"], r["id"]): r for r in report["modified"]}
    block = modified["block", BLOCK]
    assert block["structure"]["parent_id"] == {"before": PAGE, "after": ROOT}
    assert "observable_sha256" in block["fingerprints"] and "text_sha256" in block["fingerprints"]
    source = modified["data_source", SOURCE]
    assert "properties_sha256" in source["fingerprints"] and not source["metadata_changed"]
    assert "observable_sha256" in modified["view", VIEW]["fingerprints"]
    assert report["added"] == report["absent"] == report["reordered"] == []
    assert "nouveau texte privé" not in json.dumps(report, ensure_ascii=False)
    assert "Nouveau nom" not in json.dumps(report, ensure_ascii=False)
    assert "secret" not in json.dumps(report)
    assert report == nd.compare(before, after, root_page=ROOT)
    assert report["report_sha256"] == nw._digest(
        {k: v for k, v in report.items() if k != "report_sha256"}
    )


def test_diff_detects_reorder_and_absent_objects(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake(monkeypatch)
    before = ni.capture(ROOT)
    after = deepcopy(before)
    _row(after, "block", PAGE)["position"] = 1
    _row(after, "block", DB)["position"] = 0
    after["objects"].remove(_row(after, "view", VIEW))
    added_id = "1" * 32
    after["objects"].append({**_row(after, "block", BLOCK), "id": added_id, "position": 1})
    _seal(after)
    report = nd.compare(before, after, root_page=ROOT)
    assert [(x["category"], x["id"]) for x in report["added"]] == [("block", added_id)]
    assert [(x["category"], x["id"]) for x in report["absent"]] == [("view", VIEW)]
    assert report["reordered"] == [{
        "category": "block", "parent_id": ROOT, "before": [PAGE, DB], "after": [DB, PAGE],
    }]
    assert all(not row["fingerprints"] for row in report["modified"])


def test_diff_distinguishes_ordinal_shift_from_reorder(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake(monkeypatch)
    before = ni.capture(ROOT)
    after = deepcopy(before)
    _row(after, "block", PAGE)["position"] = 1
    _row(after, "block", DB)["position"] = 2
    after["objects"].append({
        **_row(before, "block", BLOCK), "id": "1" * 32, "parent_id": ROOT, "position": 0,
    })
    _seal(after)
    assert nd.compare(before, after, root_page=ROOT)["reordered"] == []


def test_diff_keeps_legacy_and_new_fingerprints_separate(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake(monkeypatch)
    report = ni.capture(ROOT)
    legacy = deepcopy(report)
    legacy["schema"] = 1
    del legacy["inventory_sha256"]
    for row in legacy["objects"]:
        del row["observable_sha256"]
        row.pop("properties_sha256", None)
    _seal(legacy)
    assert nd.compare(legacy, legacy, root_page=ROOT)["modified"] == []
    with pytest.raises(ValueError, match="schémas.*différents"):
        nd.compare(legacy, report, root_page=ROOT)


@pytest.mark.parametrize(("field", "value"), [
    ("root_page", PAGE), ("assessment", "partial"), ("api_version", "2025-09-03"),
    ("schema", True), ("limitations", []), ("requests", 1), ("remote_write", True),
    ("counts", {"page": True}), ("inventory_sha256", "0" * 64),
])
def test_diff_refuses_incompatible_inventory(
    monkeypatch: pytest.MonkeyPatch, field: str, value: Any,
) -> None:
    _fake(monkeypatch)
    report = ni.capture(ROOT)
    with pytest.raises(ValueError):
        nd.compare(report, {**report, field: value}, root_page=ROOT)


@pytest.mark.parametrize("damage", ["altered", "cycle", "gap", "child_missing", "foreign", "dupe"])
def test_diff_refuses_inconsistent_tree(monkeypatch: pytest.MonkeyPatch, damage: str) -> None:
    _fake(monkeypatch)
    report = ni.capture(ROOT)
    other = deepcopy(report)
    if damage == "altered":
        _row(other, "view", VIEW)["sha256"] = "0" * 64
    elif damage == "cycle":
        _row(other, "page", PAGE)["parent_id"] = PAGE
        child = _row(other, "block", PAGE)
        child.update(parent_id=PAGE, position=1)
        _row(other, "block", DB)["position"] = 0
    elif damage == "gap":
        _row(other, "block", DB)["position"] = 2
    elif damage == "child_missing":
        other["objects"].remove(_row(other, "page", PAGE))
    elif damage == "foreign":
        _row(other, "view", VIEW)["parent_id"] = PAGE
    else:
        other["objects"].append(_row(other, "block", DB))
    if damage != "altered":
        _seal(other)
    with pytest.raises(ValueError):
        nd.compare(report, other, root_page=ROOT)


def test_diff_ignores_transport_metadata_in_observable_fingerprint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake(monkeypatch)
    get = ni._get
    before = ni.capture(ROOT)

    def revised(path: str, params: dict[str, str]) -> dict[str, Any]:
        data = get(path, params)
        if path == f"/v1/pages/{ROOT}":
            return {**data, "last_edited_time": "2026-11-27T12:00:00Z"}
        return data

    monkeypatch.setattr(ni, "_get", revised)
    after = ni.capture(ROOT)
    changes = nd.compare(before, after, root_page=ROOT)["modified"]
    assert len(changes) == 1
    assert set(changes[0]["fingerprints"]) == {"sha256"}


@pytest.mark.skipif(os.name != "posix", reason="private POSIX files")
def test_diff_cli_privacy_and_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    calls = _fake(monkeypatch)
    snapshot = ni.capture(ROOT)
    count = len(calls)
    tmp_path.chmod(0o700)
    source, output = tmp_path / "inventory.json", tmp_path / "report.json"
    source.write_text(json.dumps(snapshot), encoding="utf-8")
    source.chmod(0o600)
    args = ["--page", ROOT, "--before", str(source), "--after", str(source),
            "--output", str(output)]
    assert nd.main(args) == 0
    assert output.stat().st_mode & 0o777 == 0o600
    assert json.loads(output.read_text())["modified"] == []
    assert ROOT not in capsys.readouterr().out
    assert nd.main(args) == 2
    output.unlink()

    source.chmod(0o644)
    assert nd.main(args) == 2 and not output.exists()
    source.chmod(0o600)
    (tmp_path / ".git").touch()
    assert nd.main(args) == 2 and not output.exists()
    (tmp_path / ".git").unlink()
    linked = tmp_path / "linked.json"
    linked.symlink_to(source)
    assert nd.main([*args, "--after", str(linked)]) == 2 and not output.exists()
    source.write_text('{"schema": 2, "schema": 2}', encoding="utf-8")
    assert nd.main(args) == 2 and not output.exists()
    assert len(calls) == count
