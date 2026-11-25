"""Bounded editorial page creation: mocked API, no live publication."""
import json
from pathlib import Path
from typing import Any

import pytest

from clawfedora import notion_editorial as ne
from clawfedora import notion_write as nw

PARENT = "1" * 32
PAGE = "2" * 32
ROOT = Path(__file__).resolve().parents[1]


def test_compile_demo_native_blocks():
    spec = json.loads((ROOT / "docs/editorial-demo/notion-spec.json").read_text())
    payload = ne.compile_spec(spec, PARENT)
    assert payload["parent"]["page_id"] == PARENT
    assert {block["type"] for block in payload["children"]} >= {
        "callout", "column_list", "table", "code", "toggle",
    }


@pytest.mark.parametrize("block", [
    {"type": "image", "url": "https://example.invalid"},
    {"type": "child_database", "title": "New"},
    {"type": "paragraph", "text": "hi", "delete": True},
    {"type": "columns", "columns": [[]]},
    {"type": "table", "rows": [["a", "b"], ["a"]]},
    {"type": "toggle", "text": "x", "children": [
        {"type": "toggle", "text": "x", "children": []},
    ]},
])
def test_rejects_unapproved_shapes(block):
    with pytest.raises(nw.NotionWriteError):
        ne.compile_spec({"title": "Test", "blocks": [block]}, PARENT)


def test_approval_single_use_and_readback(tmp_path, monkeypatch):
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({
        "title": "Test", "blocks": [{"type": "paragraph", "text": "Texte"}],
    }))
    plan = tmp_path / "plan.json"
    posts: list[dict[str, Any]] = []

    def read(method, resource):
        assert method == "GET"
        if resource.endswith(PARENT):
            return {"id": PARENT, "parent": {"type": "workspace", "workspace": True},
                    "last_edited_time": "2026-11-25T00:00:00Z", "archived": False}
        return {"id": PAGE, "parent": {"type": "page_id", "page_id": PARENT},
                "properties": posts[0]["properties"], "archived": False}

    def post(payload):
        posts.append(payload)
        return {"id": PAGE}

    def read_children(identifier):
        assert identifier == PAGE
        return [{**posts[0]["children"][0], "id": "3" * 32, "has_children": False}]

    monkeypatch.setattr(nw, "_request", read)
    monkeypatch.setattr(ne, "_post_page", post)
    monkeypatch.setattr(ne.source_connectors, "_notion_children", read_children)
    result = ne.preview(PARENT, spec, plan)
    assert not result["remote_writes"] and not posts
    with pytest.raises(nw.NotionWriteError):
        ne.apply(plan, PARENT, "0" * 64)
    assert not posts
    assert ne.apply(plan, PARENT, result["manifest_sha256"])["page_id"] == PAGE
    assert len(posts) == 1
    with pytest.raises(nw.NotionWriteError, match="déjà tenté"):
        ne.apply(plan, PARENT, result["manifest_sha256"])
    assert len(posts) == 1


def test_readback_checks_fields_and_nested_structure():
    assert ne._matches({"x": {"value": "a"}}, {"x": {"value": "a", "server": 1}})
    assert not ne._matches({"x": ["a"]}, {"x": ["b"]})
    assert not ne._matches({"x": ["a"]}, {"x": []})

PUBLIC = "https://raw.githubusercontent.com/example/demo/" + "a" * 40 + "/docs/cover.svg"


def test_premium_cover_and_rich_text_are_explicit():
    payload = ne.compile_spec({
        "title": "Test", "cover": PUBLIC, "icon": "🧭",
        "blocks": [
            {"type": "image", "url": PUBLIC, "caption": "Illustration"},
            {"type": "paragraph", "spans": [
                {"text": "Lire ", "bold": True},
                {"text": "la page", "url": "https://app.notion.com/p/" + "b" * 32},
            ]},
        ],
    }, PARENT)
    assert payload["cover"]["external"]["url"] == PUBLIC
    assert payload["icon"]["emoji"] == "🧭"
    assert payload["children"][0]["image"]["caption"][0]["text"]["content"] == "Illustration"
    rich = payload["children"][1]["paragraph"]["rich_text"]
    assert rich[0]["annotations"]["bold"] is True
    assert rich[1]["text"]["link"]["url"].endswith("b" * 32)


@pytest.mark.parametrize("url", [
    "http://localhost/cover.svg",
    "https://raw.githubusercontent.com/example/demo/main/cover.svg",
    PUBLIC + "?token=secret",
    PUBLIC.replace("/docs/", "/../"),
])
def test_media_refuses_mutable_or_unsafe_reference(url):
    with pytest.raises(nw.NotionWriteError):
        ne.compile_spec({"title": "Test", "cover": url,
                         "blocks": [{"type": "paragraph", "text": "Test"}]}, PARENT)
