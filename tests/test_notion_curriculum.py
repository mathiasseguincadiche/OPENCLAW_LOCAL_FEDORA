"""Contract tests for the relational curriculum; no live Notion calls."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from clawfedora import notion_curriculum as nc
from clawfedora import notion_studio as ns
from clawfedora import notion_studio_preview as sp
from clawfedora import notion_write as nw

HOME = "1" * 32
PAGE = "2" * 32
COVER = "3" * 32
ROOT = Path(__file__).resolve().parents[1]


def sample() -> dict[str, Any]:
    return {"modules": [
        {"title": "Comprendre", "objective": "Expliquer le service", "page": "Cours",
         "cover_file": "cover.png",
         "activities": [
             {"title": "Flux HTTP", "objective": "Tracer une requête"},
             {"title": "Base de données", "objective": "Expliquer une transaction"},
         ]},
    ]}


class FakeCurriculum:
    def __init__(self) -> None:
        self.counter = 10
        self.db: dict[str, dict[str, Any]] = {}
        self.sources: dict[str, dict[str, Any]] = {}
        self.pages: dict[str, dict[str, Any]] = {}
        self.views: dict[str, dict[str, Any]] = {}
        self.writes: list[tuple[str, str]] = []
        self.wrong_rollup = False
        self.wrong_relation = False
        self.wrong_filter = False

    def ident(self) -> str:
        self.counter += 1
        return f"{self.counter:032x}"

    def __call__(self, method, resource, *, body=None):
        if method != "GET":
            self.writes.append((method, resource))
        if method == "POST" and resource == "/v1/databases":
            ident, source = self.ident(), self.ident()
            self.db[ident] = {"id": ident, **body, "data_sources": [{"id": source}]}
            properties = body["initial_data_source"]["properties"]
            self.sources[source] = {"id": source, "properties": {
                key: {"type": next(iter(value)), **value} for key, value in properties.items()
            }}
            if self.wrong_relation and "Activités" in properties:
                self.sources[source]["properties"]["Activités"] = {
                    "type": "relation",
                    "relation": {"type": "single_property", "data_source_id": "f" * 32},
                }
            return {"id": ident}
        if method == "PATCH" and resource.startswith("/v1/data_sources/"):
            source = resource.rsplit("/", 1)[1]
            for key, value in body["properties"].items():
                self.sources[source]["properties"][key] = {
                    "type": next(iter(value)), **value,
                }
            return self.sources[source]
        if method == "POST" and resource == "/v1/pages":
            ident = self.ident()
            data = {"id": ident, **body}
            if "cover" in data:
                data["cover"] = {"type": "file", "file": {"url": "https://example.invalid"}}
            if "Module" in data["properties"]:
                data["properties"]["Progression"] = {"rollup": {
                    "type": "number", "number": 0 if not self.wrong_rollup else 1,
                }}
            self.pages[ident] = data
            return {"id": ident}
        if method == "POST" and resource == "/v1/views":
            ident = self.ident()
            self.views[ident] = {"id": ident, **body, "parent": {
                "type": "database_id", "database_id": body["database_id"],
            }}
            if self.wrong_filter and "filter" in body:
                self.views[ident]["filter"] = {}
            return {"id": ident}
        assert method == "GET"
        ident = resource.rsplit("/", 1)[1]
        if resource.startswith("/v1/databases/"):
            return self.db[ident]
        if resource.startswith("/v1/data_sources/"):
            return self.sources[ident]
        if resource.startswith("/v1/pages/"):
            return self.pages[ident]
        if resource.startswith("/v1/views/"):
            return self.views[ident]
        if resource.startswith("/v1/blocks/"):
            return {"results": self.pages[resource.split("/")[3]]["children"],
                    "has_more": False}
        raise AssertionError(resource)


def test_curriculum_creates_only_new_related_data():
    api = FakeCurriculum()
    result = nc.create(api, HOME, sample(), {"Cours": PAGE}, {"cover.png": COVER})
    assert len(api.db) == 2
    assert len(api.views) == 2
    module = result["modules"][0]
    assert module["initial_progress"] == 0
    assert len(module["activities"]) == 2
    for ident in module["activities"]:
        assert api.pages[ident]["properties"]["Validé"]["checkbox"] is False
    assert api.pages[module["page_id"]]["children"][0]["link_to_page"]["page_id"] == PAGE
    assert api.views[result["gallery_view"]]["configuration"]["cover"]["type"] == "page_cover"
    assert api.views[result["pending_view"]]["filter"]["checkbox"] == {"equals": False}
    assert [(m, r) for m, r in api.writes if m == "PATCH"] == [
        ("PATCH", f'/v1/data_sources/{result["module_source"]}'),
    ]


@pytest.mark.parametrize("failure", ["wrong_relation", "wrong_rollup", "wrong_filter"])
def test_inconsistent_api_response_fails_closed(failure):
    api = FakeCurriculum()
    setattr(api, failure, True)
    with pytest.raises(nw.NotionWriteError):
        nc.create(api, HOME, sample(), {"Cours": PAGE}, {"cover.png": COVER})


def test_spec_rejects_duplicate_or_external_page():
    spec = sample()
    assert nc.validate(spec, {"Cours"}) == ["cover.png"]
    spec["modules"][0]["page"] = "f" * 32
    with pytest.raises(nw.NotionWriteError):
        nc.validate(spec, {"Cours"})
    spec = sample()
    spec["modules"][0]["activities"].append(spec["modules"][0]["activities"][0])
    with pytest.raises(nw.NotionWriteError, match="dupliquée"):
        nc.validate(spec, {"Cours"})


def test_preview_and_single_tracker():
    spec = json.loads((ROOT / "docs/editorial-demo/curriculum-spec.json").read_text())
    assert ns._spec(spec, HOME) == []
    rendered = sp.render(spec, [], {})
    assert "Parcours relationnel" in rendered
    assert "activités validées" in rendered
    assert "Ouvrir le module" in rendered
    spec["tracker"] = {"title": "Suivi", "activities": ["A"], "views": []}
    with pytest.raises(nw.NotionWriteError, match="un seul suivi"):
        ns._spec(spec, HOME)


def test_patch_only_data_source():
    for endpoint in [f"/v1/pages/{HOME}", f"/v1/blocks/{HOME}"]:
        with pytest.raises(nw.NotionWriteError, match="endpoint"):
            ns._request("PATCH", endpoint, body={"properties": {}})
