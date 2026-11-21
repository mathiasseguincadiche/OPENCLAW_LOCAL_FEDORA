"""Reviewed updates of one rich-text segment without replacing other formatting.

Supported: direct, childless paragraphs, headings, lists, quotations, callouts.
A PATCH writes the full rich_text array *with its existing writable annotations*.
No creation, deletion, block conversion, image, database, or mention editing.
Notion offers no atomic compare-and-swap: an operator must avoid parallel edits.
"""

from __future__ import annotations

import difflib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from clawfedora import notion_batch as batch
from clawfedora import notion_write as nw

RICH_KINDS = frozenset({
    "paragraph", "heading_1", "heading_2", "heading_3",
    "quote", "callout", "bulleted_list_item", "numbered_list_item",
})
FORMATS = frozenset({"bold", "italic", "strikethrough", "underline", "code", "color"})
COLORS = frozenset({"default"} | {
    suffix + variant
    for suffix in ("gray", "brown", "orange", "yellow", "green", "blue",
                   "purple", "pink", "red")
    for variant in ("", "_background")
})
MAX_PARTS = 16
MAX_LENGTH = 9000
PLAN_KEYS = frozenset({
    "schema", "action", "page_id", "block_id", "block_type", "segment_index",
    "old_sha256", "inventory_sha256", "new_text", "created_at", "manifest_sha256",
})


def _segments(block: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    """Normalize Notion's rich-text GET response to the writable subset.

    Reject unknown types, keys, malformed links or annotations rather than
    dropping data from a richer object during a PATCH.
    """
    data = block.get(kind)
    if not isinstance(data, dict):
        raise nw.NotionWriteError("données du bloc enrichi absentes")
    source = data.get("rich_text")
    if not isinstance(source, list) or not 1 <= len(source) <= MAX_PARTS:
        raise nw.NotionWriteError("nombre de segments enrichis non pris en charge")
    result: list[dict[str, Any]] = []
    length = 0
    for part in source:
        if not isinstance(part, dict) or set(part) - {
            "type", "text", "annotations", "plain_text", "href",
        } or part.get("type") != "text":
            raise nw.NotionWriteError("mention, équation ou segment enrichi inconnu")
        data_text = part.get("text")
        if not isinstance(data_text, dict) or set(data_text) - {"content", "link"}:
            raise nw.NotionWriteError("objet texte enrichi inconnu")
        raw = data_text.get("content")
        if not isinstance(raw, str) or len(raw) > 2000 or "\x00" in raw:
            raise nw.NotionWriteError("segment de texte enrichi invalide")
        if part.get("plain_text") != raw:
            raise nw.NotionWriteError("texte Notion non concordant")
        link = data_text.get("link")
        if link is not None:
            if (
                not isinstance(link, dict) or set(link) != {"url"}
                or not isinstance(link.get("url"), str)
                or not link["url"].startswith(("https://", "http://", "mailto:"))
                or len(link["url"]) > 1800
                or part.get("href") != link["url"]
            ):
                raise nw.NotionWriteError("lien enrichi non conservable sans perte")
        elif part.get("href") is not None:
            raise nw.NotionWriteError("lien Notion incohérent")
        annotations = part.get("annotations")
        if not isinstance(annotations, dict) or set(annotations) != FORMATS:
            raise nw.NotionWriteError("annotations Notion inconnues ou incomplètes")
        if not all(type(annotations[key]) is bool for key in FORMATS - {"color"}):
            raise nw.NotionWriteError("annotations Notion non booléennes")
        if annotations["color"] not in COLORS:
            raise nw.NotionWriteError("couleur enrichie inconnue")
        length += len(raw)
        result.append({
            "type": "text",
            "text": {"content": raw, "link": link},
            "annotations": dict(annotations),
        })
    if length > MAX_LENGTH:
        raise nw.NotionWriteError("bloc enrichi trop long pour une édition sûre")
    return result


def _read(page_id: str, block_id: str) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
    page = nw._request("GET", f"/v1/pages/{page_id}")
    block = nw._request("GET", f"/v1/blocks/{block_id}")
    if nw._id(str(page.get("id", ""))) != page_id or page.get("archived") is True:
        raise nw.NotionWriteError("page Notion archivée ou absente")
    parent = block.get("parent")
    if (
        nw._id(str(block.get("id", ""))) != block_id
        or not isinstance(parent, dict)
        or parent.get("type") != "page_id"
        or nw._id(str(parent.get("page_id", ""))) != page_id
        or block.get("archived") is not False
        or block.get("has_children") is not False
        or block.get("in_trash") is True
    ):
        raise nw.NotionWriteError("bloc non direct ou portant des enfants")
    kind = block.get("type")
    if kind not in RICH_KINDS:
        raise nw.NotionWriteError("type de bloc enrichi non supporté")
    return block, str(kind), _segments(block, str(kind))


def _fingerprint(block: dict[str, Any], kind: str) -> str:
    data = cast(dict[str, Any], block[kind])
    return nw._digest({
        "base": nw._fingerprint(block, kind),
        "icon": data.get("icon"), "color": data.get("color"),
        "has_children": block.get("has_children"),
        "parent": block.get("parent"), "in_trash": block.get("in_trash"),
    })


def _replace(parts: list[dict[str, Any]], index: int, new_text: str) -> list[dict[str, Any]]:
    if type(index) is not int or not 0 <= index < len(parts):
        raise nw.NotionWriteError("segment enrichi inexistant")
    proposed = nw._text(new_text)
    if parts[index]["text"]["link"] is not None:
        raise nw.NotionWriteError("texte portant un lien : segment protégé")
    if parts[index]["text"]["content"] == proposed:
        raise nw.NotionWriteError("segment inchangé")
    updated = [
        {"type": "text", "text": dict(part["text"]), "annotations": dict(part["annotations"])}
        for part in parts
    ]
    updated[index]["text"]["content"] = proposed
    if sum(len(part["text"]["content"]) for part in updated) > MAX_LENGTH:
        raise nw.NotionWriteError("taille enrichie maximale dépassée")
    return updated


def inspect(page: str, block: str) -> dict[str, Any]:
    page_id, block_id = nw._id(page), nw._id(block)
    _block, kind, parts = _read(page_id, block_id)
    return {
        "mode": "RICH_SEGMENTS_READ_ONLY", "page_id": page_id,
        "block_id": block_id, "block_type": kind, "segments": [
            {
                "index": i, "text": part["text"]["content"],
                "annotations": part["annotations"],
                "has_link": part["text"]["link"] is not None,
                "editable": part["text"]["link"] is None,
            }
            for i, part in enumerate(parts)
        ], "remote_writes": False,
    }


def preview(
    page: str, block: str, index: int, new_text: str, output: Path,
) -> dict[str, Any]:
    page_id, block_id = nw._id(page), nw._id(block)
    inventory, inventory_sha = batch._inventory(page_id)
    if block_id not in {item["id"] for item in inventory if (
        item["has_children"] is False and item["archived"] is False
    )}:
        raise nw.NotionWriteError("bloc enrichi absent ou protégé")
    current, kind, parts = _read(page_id, block_id)
    _replace(parts, index, new_text)  # Validate format and exact target.
    original = parts[index]["text"]["content"]
    plan: dict[str, Any] = {
        "schema": 1, "action": "replace_rich_segment",
        "page_id": page_id, "block_id": block_id, "block_type": kind,
        "segment_index": index, "new_text": new_text,
        "inventory_sha256": inventory_sha,
        "old_sha256": _fingerprint(current, kind),
        "created_at": datetime.now(UTC).isoformat(),
    }
    plan["manifest_sha256"] = nw._digest(plan)
    nw._private_new(output, plan)
    return {
        "mode": "RICH_SEGMENT_PREVIEW_ONLY", "page_id": page_id,
        "block_id": block_id, "segment_index": index,
        "plan_file": str(output), "manifest_sha256": plan["manifest_sha256"],
        "preserved_segments": len(parts) - 1,
        "diff": "\n".join(difflib.unified_diff(
            original.splitlines(), new_text.splitlines(),
            fromfile="Segment actuel", tofile="Segment proposé", lineterm="",
        )), "remote_writes": False,
    }


def apply(path: Path, page: str, manifest: str) -> dict[str, Any]:
    plan = nw._load(path)
    if set(plan) != PLAN_KEYS or plan.get("schema") != 1 or plan.get(
        "action",
    ) != "replace_rich_segment":
        raise nw.NotionWriteError("plan enrichi de schéma inconnu")
    digest = plan["manifest_sha256"]
    if (
        not isinstance(digest, str) or not nw.SHA256.fullmatch(digest)
        or digest != manifest or digest != nw._digest({
            k: v for k, v in plan.items() if k != "manifest_sha256"
        }) or nw._id(page) != plan["page_id"]
        or not isinstance(plan["old_sha256"], str)
        or not nw.SHA256.fullmatch(plan["old_sha256"])
        or not isinstance(plan["inventory_sha256"], str)
        or not nw.SHA256.fullmatch(plan["inventory_sha256"])
        or plan["block_type"] not in RICH_KINDS
    ):
        raise nw.NotionWriteError("plan enrichi ou approbation invalide")
    try:
        created = datetime.fromisoformat(plan["created_at"])
    except (TypeError, ValueError) as exc:
        raise nw.NotionWriteError("date du plan enrichi invalide") from exc
    if created.utcoffset() is None or not (
        timedelta(0) <= datetime.now(UTC) - created <= timedelta(hours=24)
    ):
        raise nw.NotionWriteError("plan enrichi expiré")
    page_id, block_id = nw._id(plan["page_id"]), nw._id(plan["block_id"])
    index = plan["segment_index"]
    marker = path.with_name(path.name + ".attempted.json")
    if marker.exists() or marker.is_symlink():
        raise nw.NotionWriteError("plan enrichi déjà tenté")
    inventory, structure_sha = batch._inventory(page_id)
    if structure_sha != plan["inventory_sha256"] or block_id not in {
        part["id"] for part in inventory if not part["has_children"] and not part["archived"]
    }:
        raise nw.NotionWriteError("structure de la page modifiée depuis le plan")
    current, kind, parts = _read(page_id, block_id)
    if kind != plan["block_type"] or _fingerprint(current, kind) != plan["old_sha256"]:
        raise nw.NotionWriteError("bloc enrichi modifié depuis le plan")
    updated = _replace(parts, index, plan["new_text"])
    old_meta = {
        field: cast(dict[str, Any], current[kind]).get(field)
        for field in ("icon", "color")
    }
    nw._private_new(marker, {
        "state": "ATTEMPTED", "page_id": page_id, "block_id": block_id,
        "manifest_sha256": digest, "marked_at": datetime.now(UTC).isoformat(),
    })
    result = nw._request(
        "PATCH", f"/v1/blocks/{block_id}", write=True,
        body={kind: {"rich_text": updated}},
    )
    if nw._id(str(result.get("id", ""))) != block_id:
        raise nw.NotionWriteError("réponse enrichie ambiguë : vérifier Notion")
    verified, after_kind, after_parts = _read(page_id, block_id)
    after_meta = {
        field: cast(dict[str, Any], verified[after_kind]).get(field)
        for field in ("icon", "color")
    }
    if after_kind != kind or after_parts != updated or after_meta != old_meta:
        raise nw.NotionWriteError("rich text / style non vérifié : inspecter Notion")
    return {
        "mode": "RICH_SEGMENT_API_VERIFIED", "page_id": page_id,
        "block_id": block_id, "manifest_sha256": digest,
        "preserved_segments": len(parts) - 1,
        "limitations": "Aucune garantie de rendu graphique ou d'atomicité Notion",
    }
