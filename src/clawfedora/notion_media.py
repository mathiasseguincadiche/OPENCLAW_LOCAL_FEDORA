"""Approved edits to existing image captions and a single Notion table cell.

No media upload, URL replacement, table resizing, row insertions/deletions or
database writes. All plans are single-use and bound to remote fingerprints.
"""

from __future__ import annotations

import difflib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from clawfedora import notion_batch as batch
from clawfedora import notion_rich as rich
from clawfedora import notion_write as nw
from clawfedora import source_connectors

MAX_TABLE_ROWS = 60
MAX_TABLE_WIDTH = 12
MAX_CELL_CHARS = 1900
PLAN_FIELDS = frozenset({
    "schema", "action", "page_id", "block_id", "row_id", "cell_index",
    "segment_index", "new_text", "inventory_sha256", "table_sha256",
    "children_sha256", "target_sha256", "created_at", "manifest_sha256",
})


def _default_part(text: str) -> dict[str, Any]:
    return {
        "type": "text", "text": {"content": text, "link": None},
        "annotations": {
            "bold": False, "italic": False, "strikethrough": False,
            "underline": False, "code": False, "color": "default",
        },
    }


def _normalize(parts: object) -> list[dict[str, Any]]:
    """Reuse the strict rich-text schema, with optional empty cells/captions."""
    if parts == []:
        return []
    if not isinstance(parts, list):
        raise nw.NotionWriteError("structure de texte Notion inconnue")
    return rich._segments({"cell": {"rich_text": parts}}, "cell")


def _replace(parts: list[dict[str, Any]], index: int, text: str) -> list[dict[str, Any]]:
    if type(index) is not int or index < 0:
        raise nw.NotionWriteError("segment invalide")
    proposed = nw._text(text)
    if len(proposed) > MAX_CELL_CHARS:
        raise nw.NotionWriteError("texte trop long")
    if not parts:
        if index != 0:
            raise nw.NotionWriteError("seul le segment 0 peut être créé")
        return [_default_part(proposed)]
    return rich._replace(parts, index, proposed)


def _page_structure(page_id: str, target_id: str, kind: str) -> str:
    items, fingerprint = batch._inventory(page_id)
    if not any(
        item["id"] == target_id and item["type"] == kind
        and not item["archived"] and bool(item["has_children"]) == (kind == "table")
        for item in items
    ):
        raise nw.NotionWriteError("image/tableau absent ou structure incompatible")
    return fingerprint


def _target(page_id: str, block_id: str, kind: str) -> dict[str, Any]:
    block = nw._request("GET", f"/v1/blocks/{block_id}")
    parent = block.get("parent")
    if (
        nw._id(str(block.get("id", ""))) != block_id
        or block.get("type") != kind
        or block.get("archived") is not False
        or block.get("in_trash") is True
        or not isinstance(parent, dict)
        or parent.get("type") != "page_id"
        or nw._id(str(parent.get("page_id", ""))) != page_id
        or block.get("has_children") is not (kind == "table")
    ):
        raise nw.NotionWriteError("bloc externe ou incompatible")
    return block


def _image_parts(block: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    data = block.get("image")
    if not isinstance(data, dict) or data.get("type") not in {"file", "external"}:
        raise nw.NotionWriteError("image Notion non prise en charge")
    resource = data.get(data["type"])
    if not isinstance(resource, dict):
        raise nw.NotionWriteError("fichier de l'image absent")
    if data["type"] == "external":
        url = resource.get("url")
        if not isinstance(url, str) or not url.startswith("https://"):
            raise nw.NotionWriteError("ressource externe de l'image invalide")
        asset = nw._digest({"type": "external", "url": url})
    else:
        # Notion refreshes signed file.url and expiry_time between reads.
        # Do not reveal signed URLs, and do not hash their rotating credentials.
        if not isinstance(resource.get("url"), str):
            raise nw.NotionWriteError("ressource Notion absente")
        asset = nw._digest({"type": "file"})
    return _normalize(data.get("caption", [])), asset


def _image_state(block: dict[str, Any]) -> str:
    parts, asset = _image_parts(block)
    return nw._digest({
        "id": block["id"], "type": "image",
        "edited": block.get("last_edited_time"),
        "caption": parts, "asset": asset,
    })


def _table_state(block: dict[str, Any]) -> tuple[int, str]:
    data = block.get("table")
    if not isinstance(data, dict):
        raise nw.NotionWriteError("métadonnées du tableau absentes")
    width = data.get("table_width")
    if type(width) is not int or not 1 <= width <= MAX_TABLE_WIDTH:
        raise nw.NotionWriteError("largeur de tableau non prise en charge")
    if any(type(data.get(key)) is not bool for key in ("has_column_header", "has_row_header")):
        raise nw.NotionWriteError("en-têtes du tableau non vérifiables")
    return width, nw._digest({
        "id": block["id"], "edited": block.get("last_edited_time"),
        "width": width, "headers": {
            "column": data["has_column_header"], "row": data["has_row_header"],
        },
    })


def _rows(table_id: str) -> tuple[list[dict[str, Any]], str]:
    try:
        result = source_connectors._notion_children(table_id)
    except source_connectors.SourceImportError as exc:
        raise nw.NotionWriteError("lignes du tableau indisponibles") from exc
    if not result or len(result) > MAX_TABLE_ROWS:
        raise nw.NotionWriteError("tableau vide ou trop grand")
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in result:
        if not isinstance(row, dict):
            raise nw.NotionWriteError("ligne Notion invalide")
        identifier = nw._id(str(row.get("id", "")))
        if (
            row.get("type") != "table_row" or row.get("has_children") is not False
            or row.get("archived") is not False or identifier in seen
        ):
            raise nw.NotionWriteError("enfant du tableau inattendu")
        seen.add(identifier)
        output.append({
            "id": identifier, "type": "table_row",
            "last_edited_time": row.get("last_edited_time"),
        })
    return output, nw._digest(output)


def _row(table_id: str, row_id: str, width: int) -> tuple[dict[str, Any], list[list[dict[str, Any]]]]:
    row = nw._request("GET", f"/v1/blocks/{row_id}")
    parent = row.get("parent")
    if (
        nw._id(str(row.get("id", ""))) != row_id
        or row.get("type") != "table_row"
        or row.get("archived") is not False or row.get("in_trash") is True
        or row.get("has_children") is not False
        or not isinstance(parent, dict)
        or parent.get("type") != "block_id"
        or nw._id(str(parent.get("block_id", ""))) != table_id
    ):
        raise nw.NotionWriteError("ligne étrangère ou archivée")
    fields = row.get("table_row")
    if not isinstance(fields, dict) or set(fields) != {"cells"}:
        raise nw.NotionWriteError("ligne du tableau avec propriétés inconnues")
    cells = fields.get("cells")
    if not isinstance(cells, list) or len(cells) != width:
        raise nw.NotionWriteError("cellules du tableau incohérentes")
    normalized = [_normalize(cell) for cell in cells]
    return row, normalized


def _row_state(row: dict[str, Any], cells: list[list[dict[str, Any]]]) -> str:
    return nw._digest({
        "id": row["id"], "edited": row.get("last_edited_time"),
        "cells": cells, "parent": row.get("parent"),
    })


def inspect(page: str, block: str) -> dict[str, Any]:
    page_id, block_id = nw._id(page), nw._id(block)
    _page_structure(page_id, block_id, "image" if _kind(page_id, block_id) == "image" else "table")
    target_kind = _kind(page_id, block_id)
    obj = _target(page_id, block_id, target_kind)
    if target_kind == "image":
        parts, _ = _image_parts(obj)
        return {
            "mode": "IMAGE_CAPTION_READ_ONLY", "page_id": page_id,
            "block_id": block_id, "kind": "image",
            "segments": _display(parts), "remote_writes": False,
        }
    width, _ = _table_state(obj)
    rows, _ = _rows(block_id)
    details: list[dict[str, Any]] = []
    for child in rows:
        _, cells = _row(block_id, child["id"], width)
        details.append({
            "row_id": child["id"], "cells": [_display(cell) for cell in cells],
        })
    return {
        "mode": "TABLE_CELLS_READ_ONLY", "page_id": page_id,
        "block_id": block_id, "kind": "table",
        "width": width, "rows": details, "remote_writes": False,
    }


def _kind(page_id: str, block_id: str) -> str:
    page = nw._request("GET", f"/v1/pages/{page_id}")
    block = nw._request("GET", f"/v1/blocks/{block_id}")
    if nw._id(str(page.get("id", ""))) != page_id or page.get("archived") is True:
        raise nw.NotionWriteError("page absente ou archivée")
    if block.get("type") not in {"image", "table"}:
        raise nw.NotionWriteError("seuls une image ou un tableau existants sont pris en charge")
    return str(block["type"])


def _display(parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not parts:
        return [{"index": 0, "text": "", "editable": True, "empty": True}]
    return [
        {
            "index": index, "text": part["text"]["content"],
            "editable": part["text"]["link"] is None, "empty": False,
        }
        for index, part in enumerate(parts)
    ]


def preview(
    page: str, block: str, row: str | None, cell: int | None,
    segment: int, text: str, output: Path,
) -> dict[str, Any]:
    page_id, block_id = nw._id(page), nw._id(block)
    kind = _kind(page_id, block_id)
    inventory_sha = _page_structure(page_id, block_id, kind)
    target = _target(page_id, block_id, kind)
    new_text = nw._text(text)
    row_id: str | None = None
    cell_index: int | None = None
    table_sha: str | None = None
    children_sha: str | None = None
    if kind == "image":
        if row is not None or cell is not None:
            raise nw.NotionWriteError("les légendes d'image n'ont pas de ligne ni colonne")
        old_parts, _ = _image_parts(target)
        _replace(old_parts, segment, new_text)
        previous = old_parts[segment]["text"]["content"] if old_parts else ""
        target_sha = _image_state(target)
        mode = "IMAGE_CAPTION_PREVIEW_ONLY"
    else:
        width, table_sha = _table_state(target)
        if row is None or type(cell) is not int or not 0 <= cell < width:
            raise nw.NotionWriteError("ligne et colonne du tableau requises")
        row_id, cell_index = nw._id(row), cell
        children, children_sha = _rows(block_id)
        if row_id not in {entry["id"] for entry in children}:
            raise nw.NotionWriteError("ligne absente du tableau")
        current_row, cells = _row(block_id, row_id, width)
        _replace(cells[cell_index], segment, new_text)
        old_parts = cells[cell_index]
        previous = old_parts[segment]["text"]["content"] if old_parts else ""
        target_sha = _row_state(current_row, cells)
        mode = "TABLE_CELL_PREVIEW_ONLY"
    plan: dict[str, Any] = {
        "schema": 1, "action": "replace_image_caption" if kind == "image" else "replace_table_cell",
        "page_id": page_id, "block_id": block_id,
        "row_id": row_id, "cell_index": cell_index, "segment_index": segment,
        "new_text": new_text, "inventory_sha256": inventory_sha,
        "table_sha256": table_sha, "children_sha256": children_sha,
        "target_sha256": target_sha, "created_at": datetime.now(UTC).isoformat(),
    }
    plan["manifest_sha256"] = nw._digest(plan)
    nw._private_new(output, plan)
    return {
        "mode": mode, "page_id": page_id, "block_id": block_id,
        "plan_file": str(output), "manifest_sha256": plan["manifest_sha256"],
        "diff": "\n".join(difflib.unified_diff(
            previous.splitlines(), new_text.splitlines(), fromfile="Notion actuel",
            tofile="Texte proposé", lineterm="",
        )), "remote_writes": False,
    }


def apply(path: Path, page: str, manifest: str) -> dict[str, Any]:
    plan = nw._load(path)
    if set(plan) != PLAN_FIELDS or plan.get("schema") != 1 or plan.get("action") not in {
        "replace_image_caption", "replace_table_cell",
    }:
        raise nw.NotionWriteError("schéma de plan image/table inconnu")
    digest = plan["manifest_sha256"]
    if (
        not isinstance(digest, str) or not nw.SHA256.fullmatch(digest)
        or digest != manifest
        or digest != nw._digest({key: val for key, val in plan.items() if key != "manifest_sha256"})
        or nw._id(page) != plan["page_id"]
    ):
        raise nw.NotionWriteError("approbation du plan image/table invalide")
    try:
        created = datetime.fromisoformat(plan["created_at"])
    except (ValueError, TypeError) as exc:
        raise nw.NotionWriteError("horodatage du plan invalide") from exc
    if created.utcoffset() is None or not (
        timedelta(0) <= datetime.now(UTC) - created <= timedelta(hours=24)
    ):
        raise nw.NotionWriteError("plan expiré")
    for key in ("inventory_sha256", "target_sha256"):
        if not isinstance(plan[key], str) or not nw.SHA256.fullmatch(plan[key]):
            raise nw.NotionWriteError("empreinte de plan invalide")
    page_id, block_id = nw._id(plan["page_id"]), nw._id(plan["block_id"])
    kind = "image" if plan["action"] == "replace_image_caption" else "table"
    marker = path.with_name(path.name + ".attempted.json")
    if marker.exists() or marker.is_symlink():
        raise nw.NotionWriteError("plan image/table déjà tenté")
    if _kind(page_id, block_id) != kind or (
        _page_structure(page_id, block_id, kind) != plan["inventory_sha256"]
    ):
        raise nw.NotionWriteError("structure de page modifiée")
    target = _target(page_id, block_id, kind)
    index = plan["segment_index"]
    if kind == "image":
        if any(
            plan[key] is not None
            for key in ("row_id", "cell_index", "table_sha256", "children_sha256")
        ):
            raise nw.NotionWriteError("plan image invalide")
        current, _ = _image_parts(target)
        if _image_state(target) != plan["target_sha256"]:
            raise nw.NotionWriteError("image modifiée depuis l'aperçu")
        proposed = _replace(current, index, plan["new_text"])
        target_id, body = block_id, {"image": {"caption": proposed}}
    else:
        if (
            not isinstance(plan["table_sha256"], str)
            or not nw.SHA256.fullmatch(plan["table_sha256"])
            or not isinstance(plan["children_sha256"], str)
            or not nw.SHA256.fullmatch(plan["children_sha256"])
        ):
            raise nw.NotionWriteError("empreintes de tableau invalides")
        width, table_sha = _table_state(target)
        if table_sha != plan["table_sha256"]:
            raise nw.NotionWriteError("métadonnées du tableau modifiées")
        _, children_sha = _rows(block_id)
        if children_sha != plan["children_sha256"]:
            raise nw.NotionWriteError("lignes du tableau modifiées")
        row_id = nw._id(plan["row_id"])
        column = plan["cell_index"]
        if type(column) is not int or not 0 <= column < width:
            raise nw.NotionWriteError("colonne du tableau invalide")
        current_row, cells = _row(block_id, row_id, width)
        if _row_state(current_row, cells) != plan["target_sha256"]:
            raise nw.NotionWriteError("ligne modifiée depuis l'aperçu")
        updated = [list(parts) for parts in cells]
        updated[column] = _replace(cells[column], index, plan["new_text"])
        target_id, body = row_id, {"table_row": {"cells": updated}}
    nw._private_new(marker, {
        "state": "ATTEMPTED", "page_id": page_id, "block_id": block_id,
        "manifest_sha256": digest, "target": target_id,
        "marked_at": datetime.now(UTC).isoformat(),
    })
    result = nw._request("PATCH", f"/v1/blocks/{target_id}", write=True, body=body)
    if nw._id(str(result.get("id", ""))) != target_id:
        raise nw.NotionWriteError("réponse Notion inattendue : inspecter les blocs")
    if kind == "image":
        after = _target(page_id, block_id, kind)
        checked, current_asset = _image_parts(after)
        # The asset may rotate a signed URL but its stable identity must persist.
        _, original_asset = _image_parts(target)
        if checked != proposed or current_asset != original_asset:
            raise nw.NotionWriteError("légende ou image non vérifiée : contrôler Notion")
    else:
        after_row, after_cells = _row(block_id, target_id, width)
        if after_cells != updated or after_row.get("type") != "table_row":
            raise nw.NotionWriteError("cellule non vérifiée : contrôler Notion")
    return {
        "mode": "IMAGE_CAPTION_API_VERIFIED" if kind == "image"
        else "TABLE_CELL_API_VERIFIED",
        "page_id": page_id, "block_id": block_id, "target_id": target_id,
        "limitations": "Concordance API seulement, pas de preuve graphique ni CAS atomique",
    }
