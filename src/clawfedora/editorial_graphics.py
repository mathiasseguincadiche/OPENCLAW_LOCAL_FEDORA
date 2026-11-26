"""Managed graphic pairs; native rendering remains a separate human check."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from defusedxml import ElementTree as SafeET

from clawfedora.diagram_review import inspect_page
from clawfedora.drawio import export_page_svg, inspect_diagram
from clawfedora.editorial_identity import from_json

CRITERIA = {
    "accuracy": "Composants, flux, libellés et intention conformes aux sources.",
    "composition": "Hiérarchie, composition et densité adaptées au visuel.",
    "legibility": "Libellés, géométrie, contrastes et espaces cohérents.",
    "purpose": "Visuel utile au lecteur, présentation distincte du détail technique.",
    "preservation": "Exigences, frontières et source éditable préservées.",
    "security": "Aucune donnée privée ni secret divulgué.",
    "evidence": "Illustration distincte d'une capture ou d'une preuve réelle.",
}


def profile(task: dict[str, Any]) -> str | None:
    outputs = task["expected_outputs"]
    if len(outputs) != 2:
        return None
    paths = [Path(item) for item in outputs]
    if paths[0].with_suffix("") != paths[1].with_suffix(""):
        return None
    extensions = {path.suffix for path in paths}
    if any(path.parts[0] not in {"diagrams", "work", "deliverables"} for path in paths):
        return None
    role = task["role"]
    if extensions == {".drawio", ".svg"} and role == "architecte-solutions":
        return "diagram"
    if extensions == {".json", ".svg"} and role in {
        "architecte-solutions", "redacteur-pedagogique",
    }:
        return "identity"
    return None


def source_path(task: dict[str, Any], kind: str) -> str:
    suffix = ".drawio" if kind == "diagram" else ".json"
    return next(
        path for path in task["expected_outputs"]
        if isinstance(path, str) and Path(path).suffix == suffix
    )


def verify_refs(task: dict[str, Any], kind: str, response: dict[str, Any]) -> None:
    source = source_path(task, kind)
    svg = str(Path(source).with_suffix(".svg"))
    files = response.get("files", {})
    left, right = files.get(source), files.get(svg)
    if not isinstance(left, str) or not isinstance(right, str):
        raise ValueError("revue graphique : paire de références manquante")
    if kind == "diagram":
        if not left.startswith("@tool-drawio:") or right != (
            "@tool-svg:" + left.removeprefix("@tool-drawio:")
        ):
            raise ValueError("revue graphique : Draw.io et SVG du même outil requis")
    else:
        parts = left.split(":")
        if len(parts) != 3 or parts[0] != "@tool-file" or parts[2] != "json" or right != (
            f"@tool-file:{parts[1]}:svg"
        ):
            raise ValueError("revue graphique : JSON et SVG du même outil requis")


def inspect_source(source: str, kind: str) -> tuple[str, list[str]]:
    if kind == "identity":
        normalized, svg = from_json(source)
        if source != normalized:
            raise ValueError("revue graphique : source JSON canonique requise")
        return svg, []
    inspect_diagram(source)
    document = SafeET.fromstring(source)
    pages = document.findall("diagram")
    if document.tag != "mxfile" or len(pages) != 1:
        raise ValueError("revue graphique : une seule vue Draw.io par paire")
    geometry = inspect_page(pages[0])
    issues = []
    for pair in geometry["node_overlaps"]:
        issues.append(f"Chevauchement de composants : {pair[0]} / {pair[1]}.")
    for item in geometry["edge_through_nodes"]:
        issues.append(f"Flux {item['edge']} traversant {item['node']}.")
    for edge in geometry["non_orthogonal_edges"]:
        issues.append(f"Segment non orthogonal à revoir : {edge}.")
    return export_page_svg(pages[0]), issues


def verify_pair(task: dict[str, Any], kind: str, files: dict[str, str]) -> dict[str, str]:
    source = source_path(task, kind)
    svg_path = str(Path(source).with_suffix(".svg"))
    expected, _ = inspect_source(files[source], kind)
    if expected != files[svg_path]:
        raise ValueError("revue graphique : SVG divergent de la source")
    return {
        path: hashlib.sha256(files[path].encode("utf-8")).hexdigest()
        for path in (source, svg_path)
    }
