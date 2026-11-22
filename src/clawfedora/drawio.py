"""Native editable diagrams and bounded structural checks; no editor or network."""

from __future__ import annotations

import base64
import binascii
import math
import zlib
from textwrap import wrap
from typing import Any
from urllib.parse import unquote
from xml.etree import ElementTree as ET

from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException


def _document(content: str) -> ET.Element:
    if not content.strip() or len(content.encode()) > 60000:
        raise ValueError("Draw.io: XML limité à 60000 octets")
    try:
        return SafeET.fromstring(content, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except DefusedXmlException as exc:
        raise ValueError("Draw.io: DTD, entités et références externes interdites") from exc
    except ET.ParseError as exc:
        raise ValueError("Draw.io: XML invalide") from exc


def normalize_diagram(content: str) -> str:
    """Import the editor's usual compressed save, with a strict inflation budget."""
    document = _document(content)
    changed = False
    if document.tag == "mxfile":
        pages = document.findall("diagram")
        if not 1 <= len(pages) <= 8:
            raise ValueError("Draw.io: 1 à 8 pages requises")
        for page in pages:
            if page.find("mxGraphModel") is not None or not (page.text or "").strip():
                continue
            try:
                encoded = base64.b64decode((page.text or "").strip().encode("ascii"), validate=True)
                decoder = zlib.decompressobj(wbits=-15)
                # URI encoding may triple the UTF-8 size; no unrestricted flush/inflate.
                inflated = decoder.decompress(encoded, 180001)
                if len(inflated) > 180000 or not decoder.eof or decoder.unused_data:
                    raise ValueError("Draw.io: contenu décompressé trop volumineux ou invalide")
                model = _document(unquote(inflated.decode("utf-8"), errors="strict"))
                if model.tag != "mxGraphModel":
                    raise ValueError("Draw.io: graphe compressé invalide")
                page.text = None
                page.append(model)
                changed = True
            except (binascii.Error, zlib.error, UnicodeError) as exc:
                raise ValueError("Draw.io: sauvegarde compressée invalide") from exc
    if changed:
        document.set("compressed", "false")
        content = ET.tostring(document, encoding="unicode")
    inspect_diagram(content)
    return content


def native_diagram(labels: list[str], edges: list[list[int]]) -> str:
    document = ET.Element("mxfile", {"host": "clawfedora", "compressed": "false"})
    page = ET.SubElement(document, "diagram", {"id": "infrastructure", "name": "Infrastructure"})
    model = ET.SubElement(page, "mxGraphModel", {"grid": "1", "gridSize": "10"})
    root = ET.SubElement(model, "root")
    ET.SubElement(root, "mxCell", {"id": "0"})
    ET.SubElement(root, "mxCell", {"id": "1", "parent": "0"})
    for index, label in enumerate(labels):
        cell = ET.SubElement(
            root,
            "mxCell",
            {
                "id": f"n{index}",
                "value": label,
                "vertex": "1",
                "parent": "1",
                "style": "rounded=1;whiteSpace=wrap;html=0;fillColor=#173a56;"
                "fontColor=#ffffff;fontSize=13;strokeColor=none;",
            },
        )
        ET.SubElement(
            cell,
            "mxGeometry",
            {
                "x": "170",
                "y": str(index * 70 + 20),
                "width": "330",
                "height": "48",
                "as": "geometry",
            },
        )
    for index, (source, target) in enumerate(edges):
        cell = ET.SubElement(
            root,
            "mxCell",
            {
                "id": f"e{index}",
                "edge": "1",
                "parent": "1",
                "source": f"n{source}",
                "target": f"n{target}",
                "style": "edgeStyle=segmentEdgeStyle;html=0;endArrow=block;endFill=1;"
                "strokeColor=#367a93;strokeWidth=2;exitX=0;exitY=0.5;entryX=0;entryY=0.5;",
            },
        )
        geometry = ET.SubElement(cell, "mxGeometry", {"relative": "1", "as": "geometry"})
        points = ET.SubElement(geometry, "Array", {"as": "points"})
        for node in (source, target):
            ET.SubElement(points, "mxPoint", {"x": str(80 + index * 5), "y": str(node * 70 + 44)})
    result = ET.tostring(document, encoding="unicode")
    inspect_diagram(result)
    return result


def multi_view_diagram(
    labels: list[str], edges: list[list[int]], views: list[dict[str, Any]],
) -> str:
    """One editable Draw.io file with independent bounded views (no flattening).

    Each page is a self-contained graph with its own export.
    """
    if len(views) > 7:
        raise ValueError("Draw.io: 8 vues maximum, vue principale comprise")
    document = ET.fromstring(native_diagram(labels, edges))
    first = document.find("diagram")
    if first is None:
        raise ValueError("Draw.io: vue principale manquante")
    first.set("id", "view-1")
    for index, view in enumerate(views, 2):
        title = view.get("title")
        nodes, links = view.get("nodes"), view.get("edges", [])
        if (
            not isinstance(title, str) or not 1 <= len(title.strip()) <= 60
            or any(c in title for c in "\r\n\x00")
            or not isinstance(nodes, list) or not 1 <= len(nodes) <= 8
            or any(not isinstance(label, str) or not label.strip()
                   or len(label) > 60 for label in nodes)
            or not isinstance(links, list) or len(links) > 12
            or any(not isinstance(link, list) or len(link) != 2
                   or any(type(n) is not int or not 0 <= n < len(nodes) for n in link)
                   for link in links)
        ):
            raise ValueError("Draw.io: titre ou graphe d'une vue invalide")
        other = ET.fromstring(native_diagram(nodes, links))
        page = other.find("diagram")
        if page is None:
            raise ValueError("Draw.io: vue non générée")
        page.set("id", f"view-{index}")
        page.set("name", title.strip())
        document.append(page)
    xml = ET.tostring(document, encoding="unicode")
    inspect_diagram(xml)
    return xml


def inspect_diagram(content: str) -> dict[str, Any]:
    """Check plain XML and editable graph structure, never infrastructure correctness."""
    document = _document(content)
    models = (
        [document]
        if document.tag == "mxGraphModel"
        else document.findall("diagram/mxGraphModel")
        if document.tag == "mxfile"
        else []
    )
    if (
        not 1 <= len(models) <= 8
        or document.tag == "mxfile"
        and len(document.findall("diagram")) != len(models)
    ):
        raise ValueError("Draw.io: enregistrer 1 à 8 pages en XML non compressé")
    shapes = links = 0
    for model in models:
        root = model.find("root")
        if root is None:
            raise ValueError("Draw.io: racine du graphe absente")
        cells = list(root.iter("mxCell"))
        identities = [
            cell.get("id") or parent.get("id")
            for parent in root
            for cell in ([parent] if parent.tag == "mxCell" else parent.findall("mxCell"))
        ]
        if not 2 <= len(cells) <= 256 or len(set(identities)) != len(cells):
            raise ValueError("Draw.io: cellules trop nombreuses ou identifiants invalides")
        if not all(identities) or "0" not in identities or "1" not in identities:
            raise ValueError("Draw.io: cellules structurelles 0 et 1 requises")
        vertices = {
            identity
            for cell, identity in zip(cells, identities, strict=True)
            if cell.get("vertex") == "1"
        }
        if root.find("mxCell[@id='0']") is None or root.find("mxCell[@id='1'][@parent='0']") is None:
            raise ValueError("Draw.io: racine et couche par défaut requises")
        for cell in cells:
            vertex, edge = cell.get("vertex") == "1", cell.get("edge") == "1"
            if vertex and edge or cell.get("parent") not in {None, *identities}:
                raise ValueError("Draw.io: type ou parent de cellule invalide")
            if not (vertex or edge):
                continue
            geometry = cell.find("mxGeometry")
            if geometry is None:
                raise ValueError("Draw.io: géométrie de cellule absente")
            if edge and any(cell.get(key) not in vertices for key in ("source", "target")):
                raise ValueError("Draw.io: connexion sans extrémités connues")
            for key in ("x", "y", "width", "height"):
                try:
                    number = float(geometry.get(key, "0"))
                except ValueError as exc:
                    raise ValueError("Draw.io: coordonnées invalides") from exc
                if not math.isfinite(number) or abs(number) > 100000:
                    raise ValueError("Draw.io: coordonnées hors limites")
                if vertex and key in {"width", "height"} and number <= 0:
                    raise ValueError("Draw.io: dimensions positives requises")
            shapes += vertex
            links += edge
    return {
        "status": "PASS",
        "pages": len(models),
        "shapes": shapes,
        "links": links,
        "runtime_tested": False,
        "scope": "structure XML; infrastructure non vérifiée",
    }


def decorate_page(page: ET.Element, data: dict[str, Any]) -> None:
    """Place nodes inside editable trust boundaries and attach labels to actual edges."""
    root = page.find("mxGraphModel/root")
    assert root is not None
    nodes = root.findall("mxCell[@vertex='1']")
    links = root.findall("mxCell[@edge='1']")

    def labels(key: str, size: int) -> list[str]:
        values = data.get(key, [""] * size)
        if (not isinstance(values, list) or len(values) != size or any(
                not isinstance(v, str) or len(v) > 60 or not v.isprintable() and v
                for v in values)):
            raise ValueError(f"{key}: un libellé court par élément requis")
        return values

    groups = labels("boundaries", len(nodes))
    link_labels = labels("edge_labels", len(links))
    tops: dict[str, int] = {}
    cursor = 20
    order = list(dict.fromkeys(groups))
    for i, name in enumerate(order):
        members = [node for node, group in zip(nodes, groups, strict=True) if group == name]
        if name:
            group_id = f"group{i}"
            height = len(members) * 70 + 48
            frame = ET.Element("mxCell", id=group_id, value=name, vertex="1", parent="1",
                               style="rounded=1;html=0;verticalAlign=top;fillColor=#ecf4f8;")
            ET.SubElement(frame, "mxGeometry", {"x": "145", "y": str(cursor), "width": "550",
                          "height": str(height), "as": "geometry"})
            root.insert(2, frame)
        for j, node in enumerate(members):
            geom = node.find("mxGeometry")
            assert geom is not None
            top = j * 70 + (38 if name else 0)
            geom.set("x", "25" if name else "170")
            geom.set("width", "500")
            geom.set("y", str(top if name else cursor + top))
            if name:
                node.set("parent", group_id)
            tops[node.attrib["id"]] = cursor + top + 24
        cursor += len(members) * 70 + (70 if name else 0)
    for i, (edge, text) in enumerate(zip(links, link_labels, strict=True)):
        edge.set("value", text)
        for point, end in zip(edge.findall("mxGeometry/Array/mxPoint"),
                              ("source", "target"), strict=True):
            point.set("y", str(tops[edge.attrib[end]]))
            point.set("x", str(14 + i * 12))


def export_page_svg(page: ET.Element) -> str:
    """Inert SVG preview of Draw.io cells, typed flows and bounded compositions.

    Structural export only: browser legibility and infrastructure truth need
    independent review on the real target. All labels remain XML-escaped.
    """
    root = page.find("mxGraphModel/root")
    assert root is not None
    boxes: dict[str, tuple[int, int, int, int]] = {}
    svg = ET.Element("svg", xmlns="http://www.w3.org/2000/svg", role="img")
    ET.SubElement(svg, "title").text = page.get("name")
    ET.SubElement(svg, "desc").text = (
        "Schéma de principe : composants, frontières et flux, sans preuve de déploiement."
    )
    ET.SubElement(svg, "rect", width="100%", height="100%", fill="#ffffff")
    marker = ET.SubElement(ET.SubElement(svg, "defs"), "marker", id="arrow",
                           markerWidth="8", markerHeight="8", refX="8", refY="4",
                           orient="auto")
    ET.SubElement(marker, "path", d="M0 0 L8 4 L0 8 Z", fill="#33445D")

    def style(cell: ET.Element, key: str, fallback: str) -> str:
        for field in cell.get("style", "").split(";"):
            name, sep, value = field.partition("=")
            if sep and name == key and value:
                return value
        return fallback

    for cell in root.findall("mxCell[@vertex='1']"):
        g = cell.find("mxGeometry")
        assert g is not None
        x, y, w, h = (int(g.attrib[k]) for k in ("x", "y", "width", "height"))
        px, py, _, _ = boxes.get(cell.attrib["parent"], (0, 0, 0, 0))
        x, y = x + px, y + py
        ident = cell.attrib["id"]
        boxes[ident] = x, y, w, h
        frame = ident.startswith("group")
        fill = "#ecf4f8" if frame else style(cell, "fillColor", "#173a56")
        stroke = "#367a93" if frame else style(cell, "strokeColor", "#367a93")
        font = "#173a56" if frame else style(cell, "fontColor", "#ffffff")
        if cell.get("clawfedoraKind") == "database":
            # Recognizable storage shape even in the SVG preview.
            ET.SubElement(svg, "rect", x=str(x), y=str(y + 8), width=str(w),
                          height=str(max(1, h - 16)), fill=fill, stroke=stroke)
            for top in (y + 8, y + h - 8):
                ET.SubElement(svg, "ellipse", cx=str(x + w // 2), cy=str(top),
                              rx=str(w // 2), ry="8", fill=fill, stroke=stroke)
        else:
            ET.SubElement(svg, "rect", x=str(x), y=str(y), width=str(w),
                          height=str(h), rx="8", fill=fill, stroke=stroke)
        value = cell.get("value", "")
        # SVG has no automatic wrapping. Keep labels inside the actual card.
        max_chars = max(12, (w - 22) // 7)
        lines = wrap(value, max_chars, break_long_words=True) or [""]
        if len(lines) > max(1, (h - 8) // 16):
            raise ValueError("Draw.io: libellé illisible pour la taille de la forme")
        top = y + 18 if frame else y + (h - 16 * len(lines)) // 2 + 13
        label = ET.SubElement(svg, "text", {"x": str(x + w // 2),
                              "fill": font, "text-anchor": "middle",
                              "font-family": "sans-serif", "font-size": "13"})
        for index, line in enumerate(lines):
            ET.SubElement(label, "tspan", {"x": str(x + w // 2),
                          "y": str(top + index * 16)}).text = line

    names = {cell.attrib["id"]: cell.get("value", "")
             for cell in root.findall("mxCell[@vertex='1']")}
    max_x = max(x + w for x, _, w, _ in boxes.values()) + 28
    legend_y = max(y + h for _, y, _, h in boxes.values()) + 24
    markers: list[tuple[str, str, str]] = []
    for index, cell in enumerate(root.findall("mxCell[@edge='1']"), 1):
        sx, sy, sw, sh = boxes[cell.attrib["source"]]
        tx, ty, tw, th = boxes[cell.attrib["target"]]
        src_cx, src_cy = sx + sw // 2, sy + sh // 2
        dst_cx, dst_cy = tx + tw // 2, ty + th // 2
        if abs(dst_cx - src_cx) > abs(dst_cy - src_cy):
            start = (sx + sw if dst_cx >= src_cx else sx, src_cy)
            end = (tx if dst_cx >= src_cx else tx + tw, dst_cy)
        else:
            start = (src_cx, sy + sh if dst_cy >= src_cy else sy)
            end = (dst_cx, ty if dst_cy >= src_cy else ty + th)
        points = cell.findall("mxGeometry/Array/mxPoint")
        via = " ".join(f"L {p.attrib['x']} {p.attrib['y']}" for p in points)
        stroke = style(cell, "strokeColor", "#367a93")
        ET.SubElement(svg, "path", {"d": f"M {start[0]} {start[1]} {via} "
                          f"L {end[0]} {end[1]}", "fill": "none", "stroke": stroke,
                          "stroke-width": "2", "marker-end": "url(#arrow)"})
        if text := cell.get("value"):
            position = points[0].attrib if points else {"x": str(start[0]), "y": str(start[1])}
            markers.append((position["x"], position["y"], str(index)))
            source, target = (names[cell.attrib[key]] for key in ("source", "target"))
            lines = [*wrap(f"{index}. {source} → {target}", 75), *wrap(text, 75)]
            for line_number, line in enumerate(lines):
                legend_y += 19
                ET.SubElement(svg, "text", {"x": "26" if line_number == 0 else "42",
                              "y": str(legend_y), "fill": stroke,
                              "font-family": "sans-serif", "font-size": "14"}).text = line
            legend_y += 8
    for lane_x, mid, number in markers:
        ET.SubElement(svg, "circle", cx=lane_x, cy=mid, r="9", fill="#173a56")
        ET.SubElement(svg, "text", {"x": lane_x, "y": str(int(mid) + 4),
                      "fill": "#ffffff", "text-anchor": "middle",
                      "font-family": "sans-serif", "font-size": "10"}).text = number
    svg.set("viewBox", f"0 0 {max(720, max_x)} {legend_y + (12 if markers else 0)}")
    return ET.tostring(svg, encoding="unicode")
