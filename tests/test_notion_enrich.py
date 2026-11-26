"""Append-only enrichments preserve the original direct inventory."""
from __future__ import annotations

import copy
import json

import pytest

from clawfedora import notion_enrich as en
from clawfedora import notion_studio as ns
from clawfedora import notion_write as nw

PAGE = "1" * 32
STAMP = "2026-11-25T20:00:00Z"


class FakeAPI:
    def __init__(self):
        self.page = {
            "id": PAGE, "parent": {"type": "workspace", "workspace": True},
            "last_edited_time": STAMP, "archived": False, "in_trash": False,
            "properties": {"title": {"title": []}}, "cover": None, "icon": None,
        }
        self.blocks = [
            self.block("2" * 32, "heading_2", {
                "rich_text": [{"plain_text": "Installation des outils"}],
            }),
            self.block("3" * 32, "child_page", {"title": "Pratiquer"}, children=True),
            self.block("4" * 32, "child_database", {"title": "Progression"}, children=True),
            self.block("5" * 32, "image", {
                "type": "file", "file": {"url": "https://example.invalid/old",
                                         "expiry_time": STAMP}, "caption": [],
            }),
        ]
        self.writes = []
        self.partial = False
        self.mutate = False
        self.has_more = False

    @staticmethod
    def block(ident, kind, payload, *, children=False):
        return {"object": "block", "id": ident, "type": kind, kind: payload,
                "last_edited_time": STAMP, "has_children": children, "archived": False}

    def __call__(self, method, resource, *, body=None):
        if method == "GET" and resource == f"/v1/pages/{PAGE}":
            return copy.deepcopy(self.page)
        if method == "GET" and resource == f"/v1/blocks/{PAGE}/children?page_size=100":
            return {"results": copy.deepcopy(self.blocks), "has_more": self.has_more}
        assert method == "PATCH" and resource == f"/v1/blocks/{PAGE}/children"
        self.writes.append(copy.deepcopy(body))
        added = []
        for index, block in enumerate(body["children"], 6):
            kind = block["type"]
            added.append(self.block(str(index) * 32, kind, block[kind]))
        self.blocks.extend(added[:1] if self.partial else added)
        if self.mutate:
            self.blocks[0]["last_edited_time"] = "2026-11-25T20:01:00Z"
        self.page["last_edited_time"] = "2026-11-25T20:02:00Z"
        return {"results": copy.deepcopy(added)}


@pytest.fixture
def setup(tmp_path, monkeypatch):
    api = FakeAPI()
    monkeypatch.setattr(ns, "_request", api)
    source = tmp_path / "section.json"
    source.write_text(json.dumps({"blocks": [
        {"type": "heading_2", "text": "Diagnostic"},
        {"type": "paragraph", "text": "Comparer le résultat observé et attendu."},
    ]}))
    return api, source, tmp_path / "plan.json"


def test_approved_append_preserves_existing_direct_blocks(setup):
    api, source, path = setup
    preview = en.preview(PAGE, source, path)
    assert api.writes == [] and preview["existing_count"] == 4
    assert "Diagnostic" in path.with_name(path.name + ".preview.html").read_text()
    # Expiring hosted URL may rotate between preview and application.
    api.blocks[3]["image"]["file"]["url"] = "https://example.invalid/new"
    original = copy.deepcopy(api.blocks)
    receipt = en.apply(path, PAGE, preview["manifest_sha256"])
    assert len(api.writes) == 1
    assert api.blocks[:4] == original
    assert receipt["preserved_direct_count"] == 4
    assert len(receipt["added_ids"]) == 2
    assert path.with_name(path.name + ".verified.json").is_file()
    with pytest.raises(nw.NotionWriteError, match="déjà tenté"):
        en.apply(path, PAGE, preview["manifest_sha256"])


def test_refuse_stale_inventory_and_wrong_approval(setup):
    api, source, path = setup
    preview = en.preview(PAGE, source, path)
    with pytest.raises(nw.NotionWriteError, match="approbation"):
        en.apply(path, PAGE, "a" * 64)
    api.blocks[0]["heading_2"]["rich_text"][0]["plain_text"] = "Autre titre"
    with pytest.raises(nw.NotionWriteError, match="modifiée"):
        en.apply(path, PAGE, preview["manifest_sha256"])
    assert api.writes == []


@pytest.mark.parametrize("fault", ["partial", "mutate"])
def test_ambiguous_append_stops_without_retry(setup, fault):
    api, source, path = setup
    preview = en.preview(PAGE, source, path)
    setattr(api, fault, True)
    with pytest.raises(nw.NotionWriteError, match="non confirmé"):
        en.apply(path, PAGE, preview["manifest_sha256"])
    assert len(api.writes) == 1
    assert path.with_name(path.name + ".attempted.json").is_file()
    assert not path.with_name(path.name + ".verified.json").exists()
    with pytest.raises(nw.NotionWriteError, match="déjà tenté"):
        en.apply(path, PAGE, preview["manifest_sha256"])


def test_duplicate_and_incomplete_inventory_refused(setup):
    api, source, path = setup
    source.write_text(json.dumps({"blocks": [
        {"type": "heading_2", "text": "installation DES outils"},
        {"type": "paragraph", "text": "Un doublon"},
    ]}))
    with pytest.raises(nw.NotionWriteError, match="déjà présent"):
        en.preview(PAGE, source, path)
    api.has_more = True
    with pytest.raises(nw.NotionWriteError, match="incomplet"):
        en.preview(PAGE, source, path)
    assert api.writes == []


@pytest.mark.parametrize("blocks", [
    [{"type": "heading_1", "text": "Titre"}, {"type": "paragraph", "text": "Texte"}],
    [{"type": "heading_2", "text": "Titre"}, {"type": "heading_2", "text": "Autre"}],
    [{"type": "heading_2", "text": "Titre"}, {"type": "divider"}],
    [{"type": "heading_2", "text": "Titre"}, {"type": "synced_block", "children": []}],
])
def test_refuse_unsupported_section(blocks):
    with pytest.raises(nw.NotionWriteError):
        en._section({"blocks": blocks})


def test_transport_refuses_mutations_other_than_bounded_append():
    for body in ({}, {"children": [], "after": "x"}, {"children": [{}] * 9}):
        with pytest.raises(nw.NotionWriteError, match="endpoint"):
            ns._request("PATCH", f"/v1/blocks/{PAGE}/children", body=body)
