"""Verify the native navigation contract through the studio with a simulated API."""
from __future__ import annotations

import copy
import json

import pytest
from test_notion_studio import CHILD, HOME, PARENT, FakeAPI, _setup

from clawfedora import editorial_notion as en
from clawfedora import notion_navigation as nn
from clawfedora import notion_studio as ns
from clawfedora import notion_write as nw


class NavigationAPI(FakeAPI):
    def __init__(self):
        super().__init__()
        self.counter = 100
        self.bad_pointer = False
        self.bad_prefix = False

    def __call__(self, method, resource, *, body=None, binary=None, content_type=None):
        if method != "PATCH":
            return copy.deepcopy(super().__call__(
                method, resource, body=body, binary=binary, content_type=content_type,
            ))
        page = resource.split("/")[3]
        assert page in {HOME, CHILD}
        self.writes.append(resource)
        block = copy.deepcopy(body["children"][0])
        self.counter += 1
        ident = f"{self.counter:032x}"
        block["id"] = ident
        original = block["synced_block"]["synced_from"] is None
        nested = block["synced_block"].pop("children", [])
        block["has_children"] = True
        if original:
            self.children[ident] = []
            for child in nested:
                self.counter += 1
                self.children[ident].append({
                    **child, "id": f"{self.counter:032x}", "has_children": False,
                })
        elif self.bad_pointer:
            block["synced_block"]["synced_from"]["block_id"] = "f" * 32
        if self.bad_prefix:
            self.children[page][0]["id"] = "e" * 32
        self.children[page].append(block)
        return {"results": [block]}


def prepared(tmp_path, monkeypatch):
    spec, media, plan = _setup(tmp_path)
    value = json.loads(spec.read_text())
    # The legacy fake assigns the same id to every original block.
    value["pages"][0].pop("images")
    value["navigation"] = {"title": "Explorer le wiki"}
    spec.write_text(json.dumps(value, ensure_ascii=False))
    api = NavigationAPI()
    monkeypatch.setattr(ns, "_request", api)
    return spec, media, plan, api


def test_synced_navigation_is_opt_in_and_verified(tmp_path, monkeypatch):
    spec, media, plan, api = prepared(tmp_path, monkeypatch)
    result = ns.preview(PARENT, spec, media, plan)
    assert not api.writes
    html = plan.with_name(plan.name + ".preview.html").read_text()
    assert html.count("Navigation synchronisée prévue") == 2
    receipt = ns.apply(plan, PARENT, result["manifest_sha256"])
    nav = receipt["navigation"]
    assert nav["verified_links"] == 2
    assert nav["copies"][0]["page_id"] == CHILD
    source = api.children[nav["original_block_id"]]
    assert [b["bulleted_list_item"]["rich_text"][0]["text"]["link"]["url"]
            for b in source[1:]] == [f"https://www.notion.so/{HOME}",
                                     f"https://www.notion.so/{CHILD}"]
    assert api.children[CHILD][-1]["synced_block"]["synced_from"]["block_id"] == (
        nav["original_block_id"]
    )
    assert len([p for p in api.writes if p.endswith("/children")]) == 2


def test_wrong_pointer_refuses_receipt_and_replay(tmp_path, monkeypatch):
    spec, media, plan, api = prepared(tmp_path, monkeypatch)
    result = ns.preview(PARENT, spec, media, plan)
    api.bad_pointer = True
    with pytest.raises(nw.NotionWriteError, match="mauvais original"):
        ns.apply(plan, PARENT, result["manifest_sha256"])
    assert not plan.with_name(plan.name + ".verified.json").exists()
    count = len(api.writes)
    with pytest.raises(nw.NotionWriteError, match="déjà tenté"):
        ns.apply(plan, PARENT, result["manifest_sha256"])
    assert len(api.writes) == count


@pytest.mark.parametrize("value", [{"title": "Navigation", "block_id": "a" * 32}, {}, []])
def test_no_external_reference(value):
    with pytest.raises(nw.NotionWriteError):
        nn.validate(value)


def test_review_detects_navigation_removal(tmp_path, monkeypatch):
    spec, _, _, _ = prepared(tmp_path, monkeypatch)
    value = json.loads(spec.read_text())
    del value["navigation"]
    assert "Conserver la navigation synchronisée initiale." in en.inspect(
        json.dumps(value), preserve_navigation=True,
    )


def test_changed_prefix_refuses_navigation(tmp_path, monkeypatch):
    spec, media, plan, api = prepared(tmp_path, monkeypatch)
    result = ns.preview(PARENT, spec, media, plan)
    api.bad_prefix = True
    with pytest.raises(nw.NotionWriteError, match="ajout non confirmé"):
        ns.apply(plan, PARENT, result["manifest_sha256"])
    assert not plan.with_name(plan.name + ".verified.json").exists()
    assert len([p for p in api.writes if p.endswith("/children")]) == 1
