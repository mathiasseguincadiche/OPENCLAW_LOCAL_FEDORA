"""Synthetic provider tests for safe image captions and Notion table cells."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from clawfedora import notion_media as media
from clawfedora import notion_write as nw
from clawfedora import source_connectors

PAGE = "a" * 32
IMAGE = "b" * 32
TABLE = "c" * 32
ROW1 = "d" * 32
ROW2 = "e" * 32


def _part(text: str, *, bold: bool = False, url: str | None = None) -> dict[str, Any]:
    return {
        "type": "text",
        "text": {"content": text, "link": {"url": url} if url else None},
        "annotations": {
            "bold": bold, "italic": False, "strikethrough": False,
            "underline": False, "code": False, "color": "default",
        },
    }


def _setup(monkeypatch: pytest.MonkeyPatch, *, signed: bool = False) -> dict[str, Any]:
    state: dict[str, Any] = {
        "image": [_part("Schéma de présentation", bold=True)],
        "asset": {
            "type": "file",
            "file": {
                "url": "https://cdn.notion.test/temp-a",
                "expiry_time": "2026-11-22T00:00:00Z",
            },
        } if signed else {
            "type": "external", "external": {"url": "https://example.org/arch.svg"},
        },
        "cells": {
            ROW1: [[_part("Outil")], [_part("Objectif", bold=True)]],
            ROW2: [[_part("Ansible")], [_part("Automatiser"), _part(" documentation", url="https://example.org")]],
        },
        "patches": [], "edited": "2026-11-21T19:00:00Z",
        "structure_changed": False, "row_changed": False, "fail_patch": False,
    }
    # Use two columns; row2 has two rich-text spans in its second cell.
    def rows(block_id: str) -> list[dict[str, Any]]:
        if block_id == PAGE:
            result = [
                {"id": IMAGE, "type": "image", "has_children": False, "archived": False},
                {"id": TABLE, "type": "table", "has_children": True, "archived": False},
            ]
            if state["structure_changed"]:
                result.append({
                    "id": "f" * 32, "type": "paragraph", "has_children": False, "archived": False,
                })
            return result
        if block_id == TABLE:
            result = [
                {"id": ROW1, "type": "table_row", "has_children": False,
                 "archived": False, "last_edited_time": state["edited"]},
                {"id": ROW2, "type": "table_row", "has_children": False,
                 "archived": False, "last_edited_time": state["edited"]},
            ]
            if state["row_changed"]:
                result.reverse()
            return result
        pytest.fail("unexpected child inventory")

    def provider(
        method: str, resource: str, *, write: bool = False,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if method == "GET" and resource == f"/v1/pages/{PAGE}":
            return {"id": PAGE, "archived": False}
        block_id = resource.rsplit("/", 1)[-1]
        if method == "GET" and block_id == IMAGE:
            caption = []
            for item in state["image"]:
                part = copy.deepcopy(item)
                part["plain_text"] = part["text"]["content"]
                part["href"] = part["text"]["link"]["url"] if part["text"]["link"] else None
                caption.append(part)
            asset = copy.deepcopy(state["asset"])
            return {
                "id": IMAGE, "type": "image", "has_children": False, "archived": False,
                "parent": {"type": "page_id", "page_id": PAGE},
                "last_edited_time": state["edited"],
                "image": {**asset, "caption": caption},
            }
        if method == "GET" and block_id == TABLE:
            return {
                "id": TABLE, "type": "table", "has_children": True, "archived": False,
                "parent": {"type": "page_id", "page_id": PAGE},
                "last_edited_time": "2026-11-21T18:00:00Z",
                "table": {
                    "table_width": 2,
                    "has_column_header": True, "has_row_header": False,
                },
            }
        if method == "GET" and block_id in {ROW1, ROW2}:
            data = copy.deepcopy(state["cells"][block_id])
            for cell in data:
                for part in cell:
                    part["plain_text"] = part["text"]["content"]
                    part["href"] = part["text"]["link"]["url"] if part["text"]["link"] else None
            return {
                "id": block_id, "type": "table_row", "archived": False,
                "has_children": False, "parent": {"type": "block_id", "block_id": TABLE},
                "last_edited_time": state["edited"], "table_row": {"cells": data},
            }
        if method == "PATCH":
            assert write is True and body is not None
            if state["fail_patch"]:
                raise nw.NotionWriteError("simulation de réponse ambiguë")
            state["patches"].append((block_id, copy.deepcopy(body)))
            if block_id == IMAGE:
                assert set(body) == {"image"}
                assert set(body["image"]) == {"caption"}
                state["image"] = copy.deepcopy(body["image"]["caption"])
                if state["asset"]["type"] == "file":
                    state["asset"]["file"]["url"] = "https://cdn.notion.test/temp-b"
            else:
                assert block_id in {ROW1, ROW2}
                assert set(body) == {"table_row"}
                assert set(body["table_row"]) == {"cells"}
                state["cells"][block_id] = copy.deepcopy(body["table_row"]["cells"])
            state["edited"] = "2026-11-21T19:02:00Z"
            return {"id": block_id}
        pytest.fail(f"unexpected Notion operation {method} {resource}")

    monkeypatch.setattr(nw, "_request", provider)
    monkeypatch.setattr(source_connectors, "_notion_children", rows)
    return state


def test_image_caption_approval_preserves_external_asset_and_bold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _setup(monkeypatch)
    original_asset = copy.deepcopy(state["asset"])
    page = media.inspect(PAGE, IMAGE)
    assert page["kind"] == "image"
    assert page["segments"][0]["text"] == "Schéma de présentation"
    assert "url" not in json.dumps(page)
    path = tmp_path / "image-plan.json"
    preview = media.preview(PAGE, IMAGE, None, None, 0, "Schéma technique", path)
    assert preview["mode"] == "IMAGE_CAPTION_PREVIEW_ONLY"
    assert state["patches"] == []
    approved = media.apply(path, PAGE, preview["manifest_sha256"])
    assert approved["mode"] == "IMAGE_CAPTION_API_VERIFIED"
    assert state["image"][0]["text"]["content"] == "Schéma technique"
    assert state["image"][0]["annotations"]["bold"] is True
    assert state["asset"] == original_asset
    assert state["patches"][0][1] == {"image": {"caption": state["image"]}}
    with pytest.raises(nw.NotionWriteError, match="déjà tenté"):
        media.apply(path, PAGE, preview["manifest_sha256"])


def test_signed_image_url_rotation_not_a_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _setup(monkeypatch, signed=True)
    path = tmp_path / "plan.json"
    preview = media.preview(PAGE, IMAGE, None, None, 0, "Légende validée", path)
    state["asset"]["file"]["url"] = "https://cdn.notion.test/temp-new"
    result = media.apply(path, PAGE, preview["manifest_sha256"])
    assert result["mode"] == "IMAGE_CAPTION_API_VERIFIED"
    assert len(state["patches"]) == 1


def test_table_cell_one_segment_preserves_other_cells_and_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _setup(monkeypatch)
    original = copy.deepcopy(state["cells"])
    page = media.inspect(PAGE, TABLE)
    assert page["kind"] == "table"
    assert page["width"] == 2 and len(page["rows"]) == 2
    path = tmp_path / "table.json"
    proposal = media.preview(PAGE, TABLE, ROW2, 1, 0, "Orchestrer les opérations", path)
    assert proposal["mode"] == "TABLE_CELL_PREVIEW_ONLY"
    assert state["patches"] == []
    result = media.apply(path, PAGE, proposal["manifest_sha256"])
    assert result["mode"] == "TABLE_CELL_API_VERIFIED"
    assert state["cells"][ROW2][1][0]["text"]["content"] == "Orchestrer les opérations"
    assert state["cells"][ROW2][1][1] == original[ROW2][1][1]
    assert state["cells"][ROW2][0] == original[ROW2][0]
    assert state["cells"][ROW1] == original[ROW1]
    assert len(state["patches"]) == 1


def test_linked_segment_and_invalid_table_cell_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _setup(monkeypatch)
    with pytest.raises(nw.NotionWriteError, match="lien"):
        media.preview(PAGE, TABLE, ROW2, 1, 1, "Ne pas écraser", tmp_path / "x.json")
    with pytest.raises(nw.NotionWriteError, match="colonne"):
        media.preview(PAGE, TABLE, ROW2, 12, 0, "Interdit", tmp_path / "y.json")
    assert state["patches"] == []


def test_image_inconsistent_or_injected_asset_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _setup(monkeypatch)
    state["asset"]["external"]["url"] = "file:///etc/shadow"
    with pytest.raises(nw.NotionWriteError, match="ressource"):
        media.inspect(PAGE, IMAGE)


def test_drift_in_table_children_and_page_blocks_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _setup(monkeypatch)
    path = tmp_path / "plan.json"
    proposal = media.preview(PAGE, TABLE, ROW2, 1, 0, "Nouveau", path)
    state["row_changed"] = True
    with pytest.raises(nw.NotionWriteError, match="lignes"):
        media.apply(path, PAGE, proposal["manifest_sha256"])
    assert state["patches"] == []
    state["row_changed"] = False
    state["structure_changed"] = True
    with pytest.raises(nw.NotionWriteError, match="structure"):
        media.apply(path, PAGE, proposal["manifest_sha256"])
    assert state["patches"] == []


def test_image_target_drift_refuses_before_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _setup(monkeypatch)
    path = tmp_path / "image-plan.json"
    proposal = media.preview(PAGE, IMAGE, None, None, 0, "Texte approuvé", path)
    state["image"][0]["annotations"]["bold"] = False
    with pytest.raises(nw.NotionWriteError, match="modifiée"):
        media.apply(path, PAGE, proposal["manifest_sha256"])
    assert state["patches"] == []
    assert not (tmp_path / "image-plan.json.attempted.json").exists()


def test_tampering_and_wrong_approval_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _setup(monkeypatch)
    path = tmp_path / "image-plan.json"
    proposal = media.preview(PAGE, IMAGE, None, None, 0, "Texte approuvé", path)
    with pytest.raises(nw.NotionWriteError, match="approbation"):
        media.apply(path, PAGE, "0" * 64)
    plan = json.loads(path.read_text(encoding="utf-8"))
    plan["new_text"] = "Autre modification"
    path.write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(nw.NotionWriteError, match="approbation"):
        media.apply(path, PAGE, proposal["manifest_sha256"])
    assert state["patches"] == []


def test_unknown_mention_in_other_cell_refuses_whole_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _setup(monkeypatch)
    state["cells"][ROW2][0][0]["type"] = "mention"
    with pytest.raises(nw.NotionWriteError, match="mention"):
        media.preview(PAGE, TABLE, ROW2, 1, 0, "Interdit", tmp_path / "no.json")
    assert state["patches"] == []


def test_uncertain_patch_cannot_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _setup(monkeypatch)
    path = tmp_path / "image-plan.json"
    proposal = media.preview(PAGE, IMAGE, None, None, 0, "Vérifié", path)
    state["fail_patch"] = True
    with pytest.raises(nw.NotionWriteError, match="ambiguë"):
        media.apply(path, PAGE, proposal["manifest_sha256"])
    assert (tmp_path / "image-plan.json.attempted.json").is_file()
    with pytest.raises(nw.NotionWriteError, match="déjà tenté"):
        media.apply(path, PAGE, proposal["manifest_sha256"])


def test_child_inventory_malformed_entry_is_not_silently_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        source_connectors, "_notion",
        lambda *_args: {
            "results": [{"id": TABLE, "type": "table"}, "invalid-block"],
            "has_more": False,
        },
    )
    with pytest.raises(source_connectors.SourceImportError, match="incomplet"):
        source_connectors._notion_children(PAGE)
