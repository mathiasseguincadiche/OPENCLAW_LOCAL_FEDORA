"""Native editable diagrams and bounded structural checks; no editor or network."""

from __future__ import annotations

import base64
import binascii
import math
import zlib
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
