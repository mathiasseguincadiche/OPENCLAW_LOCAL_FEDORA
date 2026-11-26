"""Geometry signals for generated Draw.io pages; not a visual acceptance verdict."""
from __future__ import annotations

from itertools import combinations
from typing import Any
from xml.etree import ElementTree as ET

from clawfedora.diagram_layouts import _absolute, _geom

Box = tuple[int, int, int, int]
Point = tuple[int, int]


def _intersects(a: Point, b: Point, box: Box) -> bool:
    x, y, w, h = box
    # Report orthogonal line segments entering the interior, not boundary touches.
    if a[0] == b[0]:
        return x < a[0] < x + w and max(min(a[1], b[1]), y) < min(max(a[1], b[1]), y + h)
    if a[1] == b[1]:
        return y < a[1] < y + h and max(min(a[0], b[0]), x) < min(max(a[0], b[0]), x + w)
    return False


def _port(edge: ET.Element, box: Box, prefix: str) -> Point:
    fields = dict(item.split("=", 1) for item in edge.get("style", "").split(";") if "=" in item)
    x, y, w, h = box
    return (x + round(w * float(fields.get(prefix + "X", ".5"))),
            y + round(h * float(fields.get(prefix + "Y", ".5"))))


def inspect_page(page: ET.Element) -> dict[str, Any]:
    root = page.find("mxGraphModel/root")
    if root is None:
        raise ValueError("Draw.io: page incomplète")
    by_id = {cell.attrib["id"]: cell for cell in root.findall("mxCell[@vertex='1']")}
    boxes = {key: _absolute(cell, by_id) for key, cell in by_id.items()
             if not key.startswith("group")}
    overlaps = []
    for (first, a), (second, b) in combinations(boxes.items(), 2):
        if max(a[0], b[0]) < min(a[0] + a[2], b[0] + b[2]) and (
            max(a[1], b[1]) < min(a[1] + a[3], b[1] + b[3])
        ):
            overlaps.append([first, second])
    obstacles = []
    non_orthogonal = []
    for edge in root.findall("mxCell[@edge='1']"):
        src, dst = edge.attrib["source"], edge.attrib["target"]
        points = [_port(edge, boxes[src], "exit")]
        points.extend((int(p.attrib["x"]), int(p.attrib["y"]))
                      for p in _geom(edge).findall("Array/mxPoint"))
        points.append(_port(edge, boxes[dst], "entry"))
        segments = list(zip(points, points[1:], strict=False))
        if any(a[0] != b[0] and a[1] != b[1] for a, b in segments):
            non_orthogonal.append(edge.attrib["id"])
        for key, box in boxes.items():
            if key not in (src, dst) and any(_intersects(a, b, box) for a, b in segments):
                obstacles.append({"edge": edge.attrib["id"], "node": key})
    return {
        "title": page.get("name"), "node_overlaps": overlaps,
        "edge_through_nodes": obstacles, "non_orthogonal_edges": non_orthogonal,
        "assessment": "GEOMETRY_SIGNALS_ONLY",
        "native_visual_review": "NOT_EVALUATED",
    }
