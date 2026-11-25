"""V26-inspired compositions must remain editable, bounded and honest."""
from __future__ import annotations

from xml.etree import ElementTree as ET

import pytest

from clawfedora.agent_tools import diagram
from clawfedora.drawio import inspect_diagram


def test_flow_is_a_real_grid_with_typed_connectors_and_reflowed_svg() -> None:
    result = diagram({
        "layout": "flow",
        "nodes": ["Git", "CI", "Application", "PostgreSQL"],
        "edges": [[0, 1], [1, 2], [2, 3]],
        "node_types": ["component", "pipeline", "service", "database"],
        "edge_types": ["administration", "administration", "application"],
        "edge_labels": ["commit", "image OCI", "SQL"],
    })
    root = ET.fromstring(result["drawio"]).find("diagram/mxGraphModel/root")
    assert root is not None
    positions = [(int((node.find("mxGeometry")).get("x", "0")),
                  int((node.find("mxGeometry")).get("y", "0")))
                 for node in root.findall("mxCell[@vertex='1']")]
    assert positions[0][1] == positions[1][1] == positions[2][1]
    assert positions[3][1] > positions[2][1]
    assert root.find("mxCell[@id='n3']").get("clawfedoraKind") == "database"
    assert root.find("mxCell[@id='e0']").get("clawfedoraFlow") == "administration"
    assert inspect_diagram(result["drawio"])["links"] == 3
    assert result["compositions"] == ["flow"]
    svg = ET.fromstring(result["svg"])
    assert svg.find("{http://www.w3.org/2000/svg}title") is not None
    assert int(svg.attrib["viewBox"].split()[2]) > 720
    assert "image OCI" in result["svg"]
    assert "<ellipse" in result["svg"]


def test_zones_are_real_drawio_groups_in_separate_columns() -> None:
    result = diagram({
        "layout": "zones",
        "nodes": ["Fedora", "Proxy", "Base", "Supervision"],
        "edges": [[0, 1], [1, 2], [2, 3]],
        "boundaries": ["Hôte", "Application", "Données", "Observabilité"],
        "node_types": ["host", "service", "database", "monitoring"],
    })
    root = ET.fromstring(result["drawio"]).find("diagram/mxGraphModel/root")
    assert root is not None
    frames = [c for c in root.findall("mxCell[@vertex='1']")
              if c.get("id", "").startswith("group")]
    assert len(frames) == 4
    assert len({c.find("mxGeometry").get("x") for c in frames}) == 3
    assert all(root.find(f"mxCell[@id='n{i}']").get("parent") != "1"
               for i in range(4))
    assert inspect_diagram(result["drawio"])["pages"] == 1
    assert result["compositions"] == ["zones"]


@pytest.mark.parametrize("bad", [
    {"layout": "spiral"},
    {"layout": "flow", "boundaries": ["A", "B"]},
    {"layout": "zones", "boundaries": ["A", "A"]},
    {"layout": "flow", "node_types": ["supervisor"]},
    {"edge_types": ["destructive"]},
    {"layout": ["flow"]},
])
def test_invalid_compositions_are_rejected_without_fallback(bad: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        diagram({"nodes": ["A", "B"], "edges": [[0, 1]], **bad})


def test_different_views_keep_their_independent_compositions() -> None:
    result = diagram({
        "nodes": ["But", "Infra"], "edges": [[0, 1]], "layout": "flow",
        "views": [{
            "title": "Technique",
            "nodes": ["Hôte", "Service", "DB"],
            "boundaries": ["Infra", "Runtime", "Stockage"],
            "edges": [[0, 1], [1, 2]], "layout": "zones",
        }],
    })
    assert result["compositions"] == ["flow", "zones"]
    assert result["views_generated"] == 2
    assert inspect_diagram(result["drawio"])["shapes"] >= 5


def test_zone_rows_clear_tall_frames() -> None:
    result = diagram({
        "layout": "zones",
        "nodes": ["Hôte", "Proxy", "API", "DB", "Logs", "CI", "VPN", "Backup"],
        "boundaries": ["A", "A", "A", "A", "A", "B", "C", "D"],
    })
    root = ET.fromstring(result["drawio"]).find("diagram/mxGraphModel/root")
    assert root is not None
    first = root.find("mxCell[@id='group0']/mxGeometry")
    last = root.find("mxCell[@id='group3']/mxGeometry")
    assert first is not None and last is not None
    assert int(last.attrib["y"]) > int(first.attrib["y"]) + int(first.attrib["height"])


def test_svg_respects_editable_ports_and_has_visible_title() -> None:
    result = diagram({
        "title": "Flux d'exploitation",
        "nodes": ["Git", "CI"], "edges": [[0, 1]],
        "edge_types": ["administration"],
    })
    svg = ET.fromstring(result["svg"])
    # Column route leaves the left-hand side at the center of each card.
    route = svg.find("{*}path[@marker-end='url(#arrow)']")
    assert route is not None
    assert route.attrib["d"].startswith("M 170 44 L ")
    assert route.attrib["d"].endswith("L 170 114")
    assert any(node.text == "Flux d'exploitation" for node in svg.findall("{*}text"))
    flow = diagram({"layout": "flow", "nodes": ["Git", "CI"], "edges": [[0, 1]]})
    edge = ET.fromstring(flow["drawio"]).find("diagram/mxGraphModel/root/mxCell[@id='e0']")
    assert edge is not None
    assert "exitX=1;" in edge.attrib["style"] and "entryX=0;" in edge.attrib["style"]
    route = ET.fromstring(flow["svg"]).find("{*}path[@marker-end='url(#arrow)']")
    assert route is not None
    assert route.attrib["d"].startswith("M 253 71 L ")
    assert route.attrib["d"].endswith("L 296 71")
