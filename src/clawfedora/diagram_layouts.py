"""Opt-in diagram compositions for the existing editable Draw.io/SVG tool.

Never infer technical truth from geometry. Defaults are unchanged for older agents.
"""
from __future__ import annotations

from typing import Any
from xml.etree import ElementTree as ET

LAYOUTS = ("column", "flow", "zones")
NODE_TYPES = {
    "component": ("#ffffff", "#33445D"),
    "person": ("#E9EEF6", "#33445D"),
    "host": ("#E9EEF6", "#33445D"),
    "service": ("#E7F5F9", "#0E6E86"),
    "database": ("#E7F5F9", "#0E6E86"),
    "security": ("#FEF1EF", "#B42318"),
    "monitoring": ("#FDEFF4", "#B4245B"),
    "backup": ("#FFF4EC", "#A85A22"),
    "pipeline": ("#E7F5F9", "#0E6E86"),
}
EDGE_TYPES = {
    "application": "#33445D",
    "administration": "#0E6E86",
    "monitoring": "#B4245B",
    "backup": "#A85A22",
}


def _typed_list(data: dict[str, Any], key: str, count: int,
                known: dict[str, Any], fallback: str) -> list[str]:
    values = data.get(key, [fallback] * count)
    if (
        not isinstance(values, list) or len(values) != count
        or any(not isinstance(item, str) or item not in known for item in values)
    ):
        raise ValueError(f"Draw.io: {key} exige {count} types autorisés")
    return values


def _geom(node: ET.Element) -> ET.Element:
    geometry = node.find("mxGeometry")
    if geometry is None:
        raise ValueError("Draw.io: géométrie absente")
    return geometry


def _place(node: ET.Element, x: int, y: int, width: int, height: int) -> None:
    _geom(node).attrib.update({
        "x": str(x), "y": str(y), "width": str(width), "height": str(height),
    })


def _absolute(node: ET.Element, by_id: dict[str, ET.Element]) -> tuple[int, int, int, int]:
    geometry = _geom(node)
    x, y = int(geometry.get("x", "0")), int(geometry.get("y", "0"))
    width, height = int(geometry.get("width", "0")), int(geometry.get("height", "0"))
    parent = node.get("parent", "1")
    if parent != "1":
        outer = by_id[parent]
        container = _geom(outer)
        x += int(container.get("x", "0"))
        y += int(container.get("y", "0"))
    return x, y, width, height


def _route(root: ET.Element, nodes: list[ET.Element], edges: list[ET.Element]) -> None:
    by_id = {node.get("id", ""): node for node in root.findall("mxCell[@vertex='1']")}
    boxes = {node.attrib["id"]: _absolute(node, by_id) for node in nodes}
    for edge in edges:
        sx, sy, sw, sh = boxes[edge.attrib["source"]]
        tx, ty, tw, th = boxes[edge.attrib["target"]]
        src_cx, src_cy = sx + sw // 2, sy + sh // 2
        dst_cx, dst_cy = tx + tw // 2, ty + th // 2
        exit_port: tuple[float, float]
        entry_port: tuple[float, float]
        if abs(dst_cx - src_cx) > abs(dst_cy - src_cy):
            start_x = sx + sw if dst_cx >= src_cx else sx
            end_x = tx if dst_cx >= src_cx else tx + tw
            center = (start_x + end_x) // 2
            points = ((center, src_cy), (center, dst_cy))
            exit_port = (1, 0.5) if dst_cx >= src_cx else (0, 0.5)
            entry_port = (0, 0.5) if dst_cx >= src_cx else (1, 0.5)
        else:
            start_y = sy + sh if dst_cy >= src_cy else sy
            end_y = ty if dst_cy >= src_cy else ty + th
            center = (start_y + end_y) // 2
            points = ((src_cx, center), (dst_cx, center))
            exit_port = (0.5, 1) if dst_cy >= src_cy else (0.5, 0)
            entry_port = (0.5, 0) if dst_cy >= src_cy else (0.5, 1)
        # Keep the editable ports and the generated SVG on the same route.
        fields = [
            field for field in edge.get("style", "").split(";")
            if field and field.partition("=")[0] not in {"exitX", "exitY", "entryX", "entryY"}
        ]
        fields.extend((
            f"exitX={exit_port[0]}", f"exitY={exit_port[1]}",
            f"entryX={entry_port[0]}", f"entryY={entry_port[1]}",
        ))
        edge.set("style", ";".join(fields) + ";")
        geometry = _geom(edge)
        old = geometry.find("Array[@as='points']")
        if old is not None:
            geometry.remove(old)
        arr = ET.SubElement(geometry, "Array", {"as": "points"})
        for x, y in points:
            ET.SubElement(arr, "mxPoint", {"x": str(x), "y": str(y)})


def style_and_arrange(page: ET.Element, data: dict[str, Any]) -> str:
    """Apply an explicitly chosen composition, with bounded visual semantics."""
    root = page.find("mxGraphModel/root")
    if root is None:
        raise ValueError("Draw.io: page incomplète")
    nodes = [node for node in root.findall("mxCell[@vertex='1']")
             if not node.attrib.get("id", "").startswith("group")]
    edges = root.findall("mxCell[@edge='1']")
    layout = data.get("layout", "column")
    if not isinstance(layout, str) or layout not in LAYOUTS:
        raise ValueError("Draw.io: composition non reconnue")
    kinds = _typed_list(data, "node_types", len(nodes), NODE_TYPES, "component")
    flows = _typed_list(data, "edge_types", len(edges), EDGE_TYPES, "application")
    if "node_types" in data:
        for node, kind in zip(nodes, kinds, strict=True):
            fill, stroke = NODE_TYPES[kind]
            shape = "shape=cylinder;" if kind == "database" else "rounded=1;"
            node.set("style", (
                f"{shape}whiteSpace=wrap;html=0;fillColor={fill};"
                f"fontColor=#1D293B;fontSize=13;strokeColor={stroke};strokeWidth=1.5;"
            ))
            node.set("clawfedoraKind", kind)
    if "edge_types" in data:
        for edge, kind in zip(edges, flows, strict=True):
            edge.set("style", (
                "edgeStyle=segmentEdgeStyle;html=0;endArrow=block;endFill=1;"
                f"strokeColor={EDGE_TYPES[kind]};strokeWidth=2;"
                "exitX=0;exitY=0.5;entryX=0;entryY=0.5;"
            ))
            edge.set("clawfedoraFlow", kind)
    if layout == "column":
        return layout
    if layout == "flow":
        if any(node.get("parent") != "1" for node in nodes):
            raise ValueError(
                "Draw.io: flux en grille incompatible avec les frontières; utiliser zones"
            )
        for index, node in enumerate(nodes):
            _place(node, 28 + (index % 3) * 268, 35 + (index // 3) * 115, 225, 72)
    else:
        # Actual trust boundaries become independent columns; no artificial cloud zones.
        groups: dict[str, list[ET.Element]] = {}
        for node in nodes:
            groups.setdefault(node.get("parent", "1"), []).append(node)
        if len(groups) < 2 or all(key == "1" for key in groups):
            raise ValueError("Draw.io: la vue zones demande au moins deux groupes réels")
        by_id = {node.get("id", ""): node for node in root.findall("mxCell[@vertex='1']")}
        # The next row must clear the tallest frame, including a breathing gap.
        stride = max(410, max(58 + len(members) * 82 for members in groups.values()) + 36)
        for index, (parent, members) in enumerate(groups.items()):
            column, row = index % 3, index // 3
            x, y = 26 + column * 310, 26 + row * stride
            if parent == "1":
                for position, node in enumerate(members):
                    _place(node, x + 14, y + position * 82 + 20, 250, 62)
            else:
                outer = by_id[parent]
                _place(outer, x, y, 280, 58 + len(members) * 82)
                for position, node in enumerate(members):
                    _place(node, 15, 42 + position * 82, 250, 62)
    _route(root, nodes, edges)
    return layout
