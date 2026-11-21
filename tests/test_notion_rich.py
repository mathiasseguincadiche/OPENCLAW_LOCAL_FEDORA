"""Synthetic Notion API checks for segment-only rich-text updates."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from clawfedora import notion_rich as rich
from clawfedora import notion_write as nw
from clawfedora import source_connectors

PAGE = "a" * 32
BLOCK = "b" * 32
BOOL_KEYS = ("bold", "italic", "strikethrough", "underline", "code")


def _annotations(**flags: bool) -> dict[str, Any]:
    return {**{key: flags.get(key, False) for key in BOOL_KEYS}, "color": "default"}


def _segment(content: str, *, link: str | None = None, bold: bool = False) -> dict[str, Any]:
    return {
        "type": "text", "text": {"content": content, "link": {"url": link} if link else None},
        "annotations": _annotations(bold=bold),
    }


def _setup(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    parts = [
        _segment("Aide : "),
        _segment("préparer", bold=True),
        _segment(" documentation", link="https://example.org/wiki"),
    ]
    state: dict[str, Any] = {
        "parts": parts, "patches": [], "version": "2026-11-21T00:00:00Z",
        "icon": {"type": "emoji", "emoji": "💡"},
        "color": "blue_background", "children": False, "archived": False,
        "structure": False, "fail_patch": False, "kind": "callout",
    }

    def blocks(page_id: str) -> list[dict[str, Any]]:
        assert page_id == PAGE
        result = [{
            "id": BLOCK, "type": state["kind"], "has_children": state["children"],
            "archived": state["archived"],
        }]
        if state["structure"]:
            result.append({
                "id": "c" * 32, "type": "divider",
                "has_children": False, "archived": False,
            })
        return result

    def fake(
        method: str, path: str, *, write: bool = False,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if method == "GET" and path == f"/v1/pages/{PAGE}":
            return {"id": PAGE, "archived": False}
        if method == "GET" and path == f"/v1/blocks/{BLOCK}":
            result_parts = copy.deepcopy(state["parts"])
            for part in result_parts:
                part["plain_text"] = part["text"]["content"]
                url = part["text"].get("link")
                part["href"] = url["url"] if url is not None else None
            return {
                "id": BLOCK, "type": state["kind"],
                "parent": {"type": "page_id", "page_id": PAGE},
                "archived": state["archived"], "in_trash": False,
                "has_children": state["children"], "last_edited_time": state["version"],
                state["kind"]: {
                    "rich_text": result_parts, "icon": copy.deepcopy(state["icon"]),
                    "color": state["color"],
                },
            }
        if method == "PATCH" and path == f"/v1/blocks/{BLOCK}":
            assert write and body is not None
            state["patches"].append(copy.deepcopy(body))
            if state["fail_patch"]:
                raise nw.NotionWriteError("simulation d'une réponse ambiguë")
            assert set(body) == {state["kind"]}
            assert set(body[state["kind"]]) == {"rich_text"}
            state["parts"] = copy.deepcopy(body[state["kind"]]["rich_text"])
            state["version"] = "2026-11-21T00:03:00Z"
            return {"id": BLOCK}
        pytest.fail("unexpected request")

    monkeypatch.setattr(nw, "_request", fake)
    monkeypatch.setattr(source_connectors, "_notion_children", blocks)
    return state


def test_inspect_shows_styles_but_protects_linked_segment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup(monkeypatch)
    result = rich.inspect(PAGE, BLOCK)
    assert result["mode"] == "RICH_SEGMENTS_READ_ONLY"
    assert len(result["segments"]) == 3
    assert result["segments"][1]["annotations"]["bold"] is True
    assert result["segments"][2]["has_link"] is True
    assert result["segments"][2]["editable"] is False


def test_preview_and_approval_preserve_all_other_rich_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _setup(monkeypatch)
    initial = copy.deepcopy(state["parts"])
    plan_file = tmp_path / "segment.json"
    proposal = rich.preview(PAGE, BLOCK, 1, "préparer et vérifier", plan_file)
    assert proposal["mode"] == "RICH_SEGMENT_PREVIEW_ONLY"
    assert "+préparer et vérifier" in proposal["diff"]
    assert proposal["preserved_segments"] == 2
    assert not state["patches"]
    result = rich.apply(plan_file, PAGE, proposal["manifest_sha256"])
    assert result["mode"] == "RICH_SEGMENT_API_VERIFIED"
    assert len(state["patches"]) == 1
    assert state["parts"][1]["text"]["content"] == "préparer et vérifier"
    assert state["parts"][1]["annotations"]["bold"] is True
    assert state["parts"][0] == initial[0] and state["parts"][2] == initial[2]
    assert state["parts"][2]["text"]["link"]["url"] == "https://example.org/wiki"
    assert state["icon"]["emoji"] == "💡"
    assert state["color"] == "blue_background"
    with pytest.raises(nw.NotionWriteError, match="déjà tenté"):
        rich.apply(plan_file, PAGE, proposal["manifest_sha256"])
    assert len(state["patches"]) == 1


def test_never_edit_linked_or_unknown_rich_segment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _setup(monkeypatch)
    with pytest.raises(nw.NotionWriteError, match="lien"):
        rich.preview(PAGE, BLOCK, 2, "texte de lien modifié", tmp_path / "x.json")
    assert state["patches"] == []
    state["parts"][0]["type"] = "mention"
    with pytest.raises(nw.NotionWriteError, match="mention"):
        rich.inspect(PAGE, BLOCK)


def test_refuse_broken_annotations_without_losing_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _setup(monkeypatch)
    state["parts"][1]["annotations"].pop("italic")
    with pytest.raises(nw.NotionWriteError, match="annotations"):
        rich.inspect(PAGE, BLOCK)
    state["parts"][1]["annotations"]["italic"] = False
    state["parts"][1]["annotations"]["unknown"] = True
    with pytest.raises(nw.NotionWriteError, match="annotations"):
        rich.inspect(PAGE, BLOCK)


def test_reject_structure_drift_without_patch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _setup(monkeypatch)
    path = tmp_path / "plan.json"
    result = rich.preview(PAGE, BLOCK, 1, "Texte revu", path)
    state["structure"] = True
    with pytest.raises(nw.NotionWriteError, match="structure"):
        rich.apply(path, PAGE, result["manifest_sha256"])
    assert state["patches"] == []
    assert not (tmp_path / "plan.json.attempted.json").exists()


def test_refuse_edited_icon_color_or_segment_even_without_structure_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _setup(monkeypatch)
    path = tmp_path / "plan.json"
    result = rich.preview(PAGE, BLOCK, 1, "Version adaptée", path)
    state["icon"] = {"type": "emoji", "emoji": "📌"}
    with pytest.raises(nw.NotionWriteError, match="modifié"):
        rich.apply(path, PAGE, result["manifest_sha256"])
    assert state["patches"] == []
    state["icon"] = {"type": "emoji", "emoji": "💡"}
    state["parts"][0]["text"]["content"] = "Autre texte"
    with pytest.raises(nw.NotionWriteError, match="modifié"):
        rich.apply(path, PAGE, result["manifest_sha256"])
    assert state["patches"] == []


def test_tampering_and_wrong_manifest_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _setup(monkeypatch)
    path = tmp_path / "plan.json"
    proposal = rich.preview(PAGE, BLOCK, 1, "Version révisée", path)
    with pytest.raises(nw.NotionWriteError, match="approbation"):
        rich.apply(path, PAGE, "0" * 64)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["segment_index"] = 0
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(nw.NotionWriteError, match="approbation"):
        rich.apply(path, PAGE, proposal["manifest_sha256"])
    assert state["patches"] == []


def test_no_patch_on_child_or_archived_callout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _setup(monkeypatch)
    state["children"] = True
    with pytest.raises(nw.NotionWriteError, match="protégé"):
        rich.preview(PAGE, BLOCK, 1, "Nouvelle phrase", tmp_path / "plan.json")
    state["children"] = False
    state["archived"] = True
    with pytest.raises(nw.NotionWriteError, match="protégé"):
        rich.preview(PAGE, BLOCK, 1, "Nouvelle phrase", tmp_path / "plan.json")


def test_uncertain_patch_cannot_be_replayed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _setup(monkeypatch)
    path = tmp_path / "plan.json"
    proposal = rich.preview(PAGE, BLOCK, 1, "Version contrôlée", path)
    state["fail_patch"] = True
    with pytest.raises(nw.NotionWriteError, match="ambiguë"):
        rich.apply(path, PAGE, proposal["manifest_sha256"])
    assert (tmp_path / "plan.json.attempted.json").is_file()
    with pytest.raises(nw.NotionWriteError, match="déjà tenté"):
        rich.apply(path, PAGE, proposal["manifest_sha256"])
    assert len(state["patches"]) == 1


def test_wrong_index_cannot_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _setup(monkeypatch)
    with pytest.raises(nw.NotionWriteError, match="inexistant"):
        rich.preview(PAGE, BLOCK, True, "Texte", tmp_path / "plan.json")
    with pytest.raises(nw.NotionWriteError, match="inexistant"):
        rich.preview(PAGE, BLOCK, 40, "Texte", tmp_path / "plan.json")
    assert state["patches"] == []
