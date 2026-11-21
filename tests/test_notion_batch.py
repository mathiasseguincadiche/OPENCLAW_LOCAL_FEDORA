"""Offline security and lifecycle tests for a scoped, multi-block Notion patch."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from clawfedora import notion_batch as batch
from clawfedora import notion_write as nw

PAGE = "a" * 32
FIRST = "b" * 32
SECOND = "c" * 32
PROTECTED = "d" * 32


def _setup(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "texts": {FIRST: "Ligne initiale A", SECOND: "Ligne initiale B"},
        "version": {FIRST: "2026-11-21T12:00:00Z", SECOND: "2026-11-21T12:00:00Z"},
        "calls": [], "structure_extra": False, "fail_second": False,
    }

    def inventory(_page: str) -> list[dict[str, Any]]:
        assert _page == PAGE
        blocks = [
            {"id": FIRST, "type": "paragraph", "archived": False,
             "has_children": False},
            {"id": SECOND, "type": "heading_2", "archived": False,
             "has_children": False},
            {"id": PROTECTED, "type": "child_page", "archived": False,
             "has_children": True},
        ]
        if state["structure_extra"]:
            blocks.append({
                "id": "e" * 32, "type": "paragraph",
                "archived": False, "has_children": False,
            })
        return blocks

    def api(
        method: str, resource: str, *, write: bool = False,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if method == "GET" and resource == f"/v1/pages/{PAGE}":
            return {"id": PAGE, "archived": False}
        if method == "GET" and resource.startswith("/v1/blocks/"):
            block_id = resource.rsplit("/", 1)[-1]
            kind = "heading_2" if block_id == SECOND else "paragraph"
            value = state["texts"][block_id]
            return {
                "id": block_id, "type": kind, "archived": False,
                "has_children": False, "last_edited_time": state["version"][block_id],
                "parent": {"type": "page_id", "page_id": PAGE},
                kind: {"rich_text": [{
                    "type": "text", "plain_text": value, "href": None,
                    "text": {"content": value, "link": None},
                    "annotations": {"color": "default", "bold": False,
                                    "italic": False, "underline": False,
                                    "code": False, "strikethrough": False},
                }]},
            }
        if method == "PATCH":
            assert write and body is not None
            block_id = resource.rsplit("/", 1)[-1]
            if state["fail_second"] and block_id == SECOND:
                raise nw.NotionWriteError("simulation HTTP 503")
            value = body[next(iter(body))]["rich_text"][0]["text"]["content"]
            state["calls"].append(block_id)
            state["texts"][block_id] = value
            state["version"][block_id] = "2026-11-21T12:05:00Z"
            return {"id": block_id}
        pytest.fail("unexpected request")

    monkeypatch.setattr(nw, "_request", api)
    monkeypatch.setattr(batch.source_connectors, "_notion_children", inventory)
    return state


def _edits(path: Path, edits: list[dict[str, str]]) -> None:
    path.write_text(json.dumps({"edits": edits}, ensure_ascii=False), encoding="utf-8")


def _valid(tmp_path: Path) -> Path:
    source = tmp_path / "edits.json"
    _edits(source, [
        {"block_id": FIRST, "text": "Ligne relue A"},
        {"block_id": SECOND, "text": "Ligne relue B"},
    ])
    return source


def test_preview_only_and_apply_two_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _setup(monkeypatch)
    path = tmp_path / "plan.json"
    result = batch.preview(PAGE, _valid(tmp_path), path)
    assert result["mode"] == "BATCH_PREVIEW_ONLY"
    assert result["protected_blocks_untouched"] == 1
    assert len(result["edits"]) == 2
    assert state["calls"] == []
    assert path.stat().st_mode & 0o077 == 0
    applied = batch.apply(path, PAGE, result["manifest_sha256"])
    assert applied["mode"] == "BATCH_BLOCKS_API_VERIFIED"
    assert applied["verified_blocks"] == [FIRST, SECOND]
    assert state["texts"][FIRST] == "Ligne relue A"
    assert state["texts"][SECOND] == "Ligne relue B"
    assert state["calls"] == [FIRST, SECOND]
    assert (tmp_path / "plan.json.step-01.verified.json").is_file()
    assert (tmp_path / "plan.json.step-02.verified.json").is_file()
    with pytest.raises(nw.NotionWriteError, match="déjà tenté"):
        batch.apply(path, PAGE, result["manifest_sha256"])
    assert state["calls"] == [FIRST, SECOND]


def test_inventoried_child_page_never_edited(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup(monkeypatch)
    edits = tmp_path / "edits.json"
    _edits(edits, [{"block_id": PROTECTED, "text": "Texte interdit"}])
    with pytest.raises(nw.NotionWriteError, match="enfants"):
        batch.preview(PAGE, edits, tmp_path / "plan.json")


def test_structure_drift_refuses_before_attempt_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _setup(monkeypatch)
    path = tmp_path / "plan.json"
    result = batch.preview(PAGE, _valid(tmp_path), path)
    state["structure_extra"] = True
    with pytest.raises(nw.NotionWriteError, match="structure"):
        batch.apply(path, PAGE, result["manifest_sha256"])
    assert state["calls"] == []
    assert not (tmp_path / "plan.json.attempted.json").exists()


def test_text_drift_refuses_before_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _setup(monkeypatch)
    path = tmp_path / "plan.json"
    result = batch.preview(PAGE, _valid(tmp_path), path)
    state["version"][SECOND] = "2026-11-21T12:01:00Z"
    with pytest.raises(nw.NotionWriteError, match="modifié"):
        batch.apply(path, PAGE, result["manifest_sha256"])
    assert state["calls"] == []


def test_partial_remote_failure_stops_and_requires_manual_reconciliation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _setup(monkeypatch)
    path = tmp_path / "plan.json"
    result = batch.preview(PAGE, _valid(tmp_path), path)
    state["fail_second"] = True
    with pytest.raises(nw.NotionWriteError, match="503"):
        batch.apply(path, PAGE, result["manifest_sha256"])
    assert state["calls"] == [FIRST]
    assert (tmp_path / "plan.json.attempted.json").is_file()
    assert (tmp_path / "plan.json.step-01.verified.json").is_file()
    assert (tmp_path / "plan.json.step-02.attempted.json").is_file()
    assert not (tmp_path / "plan.json.step-02.verified.json").exists()
    with pytest.raises(nw.NotionWriteError, match="déjà tenté"):
        batch.apply(path, PAGE, result["manifest_sha256"])


def test_approval_and_integrity_never_trigger_network_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _setup(monkeypatch)
    path = tmp_path / "plan.json"
    result = batch.preview(PAGE, _valid(tmp_path), path)
    with pytest.raises(nw.NotionWriteError, match="intégrité"):
        batch.apply(path, PAGE, "0" * 64)
    plan = json.loads(path.read_text(encoding="utf-8"))
    plan["edits"][0]["new_text"] = "Texte injecté"
    path.write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(nw.NotionWriteError, match="intégrité"):
        batch.apply(path, PAGE, result["manifest_sha256"])
    assert state["calls"] == []


def test_duplicate_and_too_many_edits_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup(monkeypatch)
    path = tmp_path / "edits.json"
    _edits(path, [{"block_id": FIRST, "text": "A"}, {"block_id": FIRST, "text": "B"}])
    with pytest.raises(nw.NotionWriteError, match="répété"):
        batch.preview(PAGE, path, tmp_path / "plan.json")
    _edits(path, [{"block_id": FIRST, "text": "Nouveau"}] * 6)
    with pytest.raises(nw.NotionWriteError, match="1 et 5"):
        batch.preview(PAGE, path, tmp_path / "plan.json")


def test_no_implicit_apply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(nw, "_request", lambda *_args, **_kw: pytest.fail("network"))
    assert batch.main([
        "apply", "--plan", str(tmp_path / "plan.json"),
        "--approve-page", PAGE, "--approve-manifest", "f" * 64,
    ]) == 2
    assert "REFUSED_OR_INCOMPLETE" in capsys.readouterr().out


def test_plan_never_contains_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup(monkeypatch)
    monkeypatch.setenv("NOTION_WRITE_TOKEN", "token-secret-test")
    path = tmp_path / "plan.json"
    preview = batch.preview(PAGE, _valid(tmp_path), path)
    assert "token-secret-test" not in json.dumps(preview)
    assert "token-secret-test" not in path.read_text(encoding="utf-8")
