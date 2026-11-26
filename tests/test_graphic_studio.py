"""Advanced graphics preserve editable sources and report geometry, not a visual PASS."""
from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from defusedxml.ElementTree import fromstring

from clawfedora.agent_tools import diagram
from clawfedora.editorial_compositions import COMPOSITIONS
from clawfedora.editorial_identity import VARIANTS, render

ROOT = Path(__file__).resolve().parents[1]
SPEC = {
    "project": "Atlas & Ops", "tagline": "Concevoir et expliquer",
    "variant": "hero", "motif": "automation", "palette": "indigo",
    "section": "Architecture & sécurité",
}


@pytest.mark.parametrize("composition", COMPOSITIONS)
@pytest.mark.parametrize("variant", sorted(VARIANTS))
def test_composition_valid_and_reproducible(composition, variant):
    normalized, svg = render(dict(SPEC, composition=composition, variant=variant))
    assert render(normalized) == (normalized, svg)
    assert fromstring(svg).tag.endswith("svg")
    assert "Architecture &amp; sécurité" in svg
    assert "<script" not in svg and "href=" not in svg
    if variant == "cover":
        assert "<text" not in svg


def test_hero_compositions_are_distinct_and_legacy_still_works():
    assert len({render(dict(SPEC, composition=c))[1] for c in COMPOSITIONS}) == 4
    assert render(SPEC) == render(dict(SPEC, composition="split"))
    with pytest.raises(ValueError, match="composition"):
        render(dict(SPEC, composition="raw-svg"))


@pytest.mark.parametrize("layout", ["timeline", "hub"])
def test_new_layouts_keep_editable_edges_and_separate_nodes(layout):
    result = diagram({
        "nodes": ["Orchestrateur", "Recherche", "Audit", "Livraison"],
        "edges": [[0, 1], [0, 2], [0, 3]], "layout": layout,
    })
    assert result["compositions"] == [layout]
    page = ET.fromstring(result["drawio"]).find("diagram")
    assert page is not None
    root = page.find("mxGraphModel/root")
    assert root is not None
    assert len(root.findall("mxCell[@edge='1']")) == 3
    report = result["geometry_review"][0]
    assert not report["node_overlaps"]
    assert report["native_visual_review"] == "NOT_EVALUATED"
    assert fromstring(result["svg"]).tag.endswith("svg")


def test_skipped_node_on_timeline_reports_obstruction():
    result = diagram({
        "nodes": ["Source", "Intermédiaire", "Cible"],
        "edges": [[0, 2]], "layout": "timeline",
    })
    assert {"edge": "e0", "node": "n1"} in result["geometry_review"][0]["edge_through_nodes"]


def test_advanced_examples_match_generator():
    gallery = ROOT / "docs/editorial-demo/advanced"
    sources = sorted(gallery.glob("*.json"))
    assert len(sources) == 3
    for path in sources:
        _, svg = render(json.loads(path.read_text(encoding="utf-8")))
        assert path.with_suffix(".svg").read_text(encoding="utf-8") == svg
