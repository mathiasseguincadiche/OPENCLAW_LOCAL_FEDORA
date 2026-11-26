"""Offline review of a new Notion studio specification, never a publication plan."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from clawfedora import notion_studio as ns
from clawfedora import notion_studio_preview as sp
from clawfedora.structured_response import parse_response

CRITERIA = {
    "accuracy": "Exactitude technique, versions, sources et limites.",
    "writing": "Rédaction naturelle, précise, transitions et absence de doublons inutiles.",
    "navigation": "Accueil, sous-pages, navigation et hiérarchie adaptées aux lecteurs.",
    "pedagogy": "Objectifs, mécanismes, exemples, installation, pratique et vérification.",
    "composition": "Couvertures et blocs natifs utiles, tableaux et colonnes sobres.",
    "preservation": "Respect du brief, contenus requis, exercices, liens et confidentialité.",
    "evidence": "Progression manuelle et preuves réelles distinctes de la maquette.",
}
MAX_BYTES = 8000
DUMMY_PARENT = "0" * 32


def requested(task: dict[str, Any]) -> bool:
    outputs = task["expected_outputs"]
    return (
        task["role"] in {"architecte-solutions", "redacteur-pedagogique"}
        and len(outputs) == 1
        and outputs[0].endswith(".notion.json")
        and Path(outputs[0]).parts[0] in {"work", "deliverables"}
    )


def parse(content: str) -> dict[str, Any]:
    if not isinstance(content, str) or not 0 < len(content.encode("utf-8")) <= MAX_BYTES:
        raise ValueError("revue Notion : spécification limitée à 8000 octets")
    spec = parse_response(content, {"type": "object"})
    try:
        names = ns._spec(spec, DUMMY_PARENT)
    except (KeyError, TypeError) as exc:
        raise ValueError("revue Notion : spécification invalide") from exc
    # Only names are reviewed here; actual bytes must be approved in studio plan.
    for name in names:
        if not ns.NAME.fullmatch(name) or ".." in name or Path(name).suffix.lower() not in ns.MIMES:
            raise ValueError("revue Notion : nom simple PNG/JPEG requis")
    return spec


def _blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for block in blocks:
        result.append(block)
        if block["type"] == "toggle":
            result.extend(_blocks(block["children"]))
        elif block["type"] == "columns":
            for column in block["columns"]:
                result.extend(_blocks(column))
    return result


def _text(block: dict[str, Any]) -> str:
    if "spans" in block:
        return "".join(span["text"] for span in block["spans"])
    return str(block.get("text", ""))


def has_installation(spec: dict[str, Any]) -> bool:
    for page in [spec["home"], *spec["pages"]]:
        for block in _blocks(page["blocks"]):
            if (
                (block["type"].startswith("heading_") or block["type"] == "toggle")
                and " ".join(_text(block).casefold().split()) == "installation des outils"
            ):
                return True
    return False


def inspect(content: str, *, preserve_installation: bool = False,
            preserve_curriculum: bool = False) -> list[str]:
    spec = parse(content)
    issues = []
    if (preserve_installation or "curriculum" in spec) and not has_installation(spec):
        issues.append("Conserver une section Installation des outils dans le wiki.")
    if preserve_curriculum and "curriculum" not in spec:
        issues.append("Conserver le parcours relationnel initial.")
    for index, page in enumerate([spec["home"], *spec["pages"]], 1):
        # Page titles are already rendered by Notion; headings start at level 1 or 2.
        levels = [int(b["type"][-1]) for b in page["blocks"]
                  if b["type"].startswith("heading_")]
        if levels and (levels[0] == 3 or any(
            right > left + 1 for left, right in zip(levels, levels[1:], strict=False)
        )):
            issues.append(f"Page {index} : reprendre les niveaux de titres.")
        if not any(b["type"] in {"paragraph", "callout", "quote", "code",
                                 "bulleted_list_item", "numbered_list_item"}
                   for b in _blocks(page["blocks"])):
            issues.append(f"Page {index} : ajouter une explication, pas seulement des titres.")
    return issues


def canonical(content: str) -> str:
    return json.dumps(parse(content), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def preview(content: str) -> str:
    # No credentials, remote requests, or local image reads in an agent review.
    return sp.render(parse(content), [], {}, media_placeholders=True)
