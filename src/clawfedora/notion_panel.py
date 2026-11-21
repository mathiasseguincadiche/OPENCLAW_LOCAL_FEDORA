"""Same-origin dashboard adapter for selected Notion text blocks.

No API tokens or user-provided filesystem paths are accepted from the browser.
The local operator owns proposals and explicit approvals; agents cannot invoke
this adapter. The underlying Notion writer remains the sole mutation engine.
"""

from __future__ import annotations

import re
import secrets
import stat
from pathlib import Path
from typing import Any

from clawfedora import notion_batch, notion_media, notion_rich, notion_write, source_connectors

PLAN_ID = re.compile(r"[0-9a-f]{32}\Z")
MAX_VISIBLE_BLOCKS = 120


def _store(runtime: Path) -> Path:
    root = runtime / "state"
    if root.is_symlink():
        raise notion_write.NotionWriteError("dossier d'état lié interdit")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    folder = root / "notion-ui"
    if folder.is_symlink():
        raise notion_write.NotionWriteError("dossier de plans lié interdit")
    folder.mkdir(mode=0o700, exist_ok=True)
    if (
        not folder.is_dir()
        or stat.S_IMODE(folder.stat().st_mode) & 0o077
    ):
        raise notion_write.NotionWriteError("dossier de plans non privé")
    return folder


def inspect(page: str) -> dict[str, Any]:
    """Read page structure and bounded previews, not write or import content."""
    page_id = notion_write._id(page)
    inventory, fingerprint = notion_batch._inventory(page_id)
    if len(inventory) > MAX_VISIBLE_BLOCKS:
        raise notion_write.NotionWriteError(
            "page trop grande pour le panneau : utiliser la CLI sur une page plus courte",
        )
    children = source_connectors._notion_children(page_id)
    comparison = [
        {
            "id": notion_write._id(str(block.get("id", ""))),
            "type": block.get("type"),
            "has_children": block.get("has_children"),
            "archived": block.get("archived"),
        }
        for block in children
    ]
    if notion_write._digest(comparison) != fingerprint:
        raise notion_write.NotionWriteError("inventaire Notion modifié pendant la lecture")
    rows: list[dict[str, Any]] = []
    for block in children:
        kind = str(block["type"])
        editable = (
            kind in notion_write.EDIT_TYPES
            and block.get("has_children") is False
            and block.get("archived") is False
        )
        media_candidate = kind in {"image", "table"}
        rich_candidate = (
            kind in notion_rich.RICH_KINDS
            and block.get("has_children") is False
            and block.get("archived") is False
        )
        label = ""
        if editable or rich_candidate:
            data = block.get(kind, {})
            pieces = data.get("rich_text", []) if isinstance(data, dict) else []
            if isinstance(pieces, list):
                label = "".join(
                    str(part.get("plain_text", ""))
                    for part in pieces if isinstance(part, dict)
                )[:180]
        rows.append({
            "block_id": notion_write._id(str(block["id"])),
            "type": kind,
            "eligible": editable,
            "rich_candidate": rich_candidate,
            "media_candidate": media_candidate,
            "excerpt": label,
        })
    return {
        "mode": "NOTION_STRUCTURE_READ_ONLY",
        "page_id": page_id, "inventory_sha256": fingerprint,
        "blocks": rows,
        "editable_count": sum(row["eligible"] for row in rows),
        "rich_candidate_count": sum(row["rich_candidate"] for row in rows),
        "media_candidate_count": sum(row["media_candidate"] for row in rows),
        "protected_count": sum(not row["eligible"] for row in rows),
        "remote_writes": False,
    }


def plan(runtime: Path, page: str, edits: object) -> dict[str, Any]:
    page_id = notion_write._id(page)
    if not isinstance(edits, list):
        raise notion_write.NotionWriteError("liste de modifications requise")
    folder = _store(runtime)
    name = secrets.token_hex(16)
    source = folder / (name + ".edits.json")
    output = folder / (name + ".plan.json")
    # Only the local runtime chooses the path; no browser path or filename is used.
    notion_write._private_new(source, {"edits": edits})
    try:
        preview = notion_batch.preview(page_id, source, output)
    finally:
        source.unlink(missing_ok=True)
    return {
        "mode": preview["mode"],
        "page_id": page_id,
        "plan_id": name,
        "manifest_sha256": preview["manifest_sha256"],
        "edits": preview["edits"],
        "protected_blocks_untouched": preview["protected_blocks_untouched"],
        "remote_writes": False,
    }


def apply(
    runtime: Path, plan_id: str, page: str,
    approve_page: str, approve_manifest: str, human_approved: object,
) -> dict[str, Any]:
    if human_approved is not True:
        raise notion_write.NotionWriteError("accord humain explicite requis")
    if PLAN_ID.fullmatch(plan_id) is None:
        raise notion_write.NotionWriteError("identifiant de plan invalide")
    page_id = notion_write._id(page)
    if notion_write._id(approve_page) != page_id:
        raise notion_write.NotionWriteError("page approuvée différente")
    if notion_write.SHA256.fullmatch(approve_manifest) is None:
        raise notion_write.NotionWriteError("empreinte de plan SHA-256 requise")
    path = _store(runtime) / (plan_id + ".plan.json")
    result = notion_batch.apply(path, page_id, approve_manifest)
    return {
        "mode": result["mode"],
        "page_id": page_id,
        "verified_blocks": result["verified_blocks"],
        "manifest_sha256": result["manifest_sha256"],
        "limitations": result["limitations"],
    }


def rich_inspect(page: str, block_id: str) -> dict[str, Any]:
    """Read one selected block; returned text stays inside the local browser."""
    return notion_rich.inspect(page, block_id)


def rich_plan(
    runtime: Path, page: str, block_id: str, segment_index: int, text: str,
) -> dict[str, Any]:
    page_id = notion_write._id(page)
    folder = _store(runtime)
    name = secrets.token_hex(16)
    output = folder / (name + ".plan.json")
    result = notion_rich.preview(page_id, block_id, segment_index, text, output)
    return {
        "mode": result["mode"], "page_id": page_id,
        "block_id": result["block_id"], "segment_index": result["segment_index"],
        "plan_id": name, "manifest_sha256": result["manifest_sha256"],
        "preserved_segments": result["preserved_segments"],
        "diff": result["diff"], "remote_writes": False,
    }


def rich_apply(
    runtime: Path, plan_id: str, page: str, approve_page: str,
    approve_manifest: str, human_approved: object,
) -> dict[str, Any]:
    if human_approved is not True:
        raise notion_write.NotionWriteError("accord humain explicite requis")
    if PLAN_ID.fullmatch(plan_id) is None:
        raise notion_write.NotionWriteError("identifiant de plan invalide")
    page_id = notion_write._id(page)
    if notion_write._id(approve_page) != page_id:
        raise notion_write.NotionWriteError("page approuvée différente")
    if notion_write.SHA256.fullmatch(approve_manifest) is None:
        raise notion_write.NotionWriteError("empreinte de plan SHA-256 requise")
    path = _store(runtime) / (plan_id + ".plan.json")
    result = notion_rich.apply(path, page_id, approve_manifest)
    return {
        "mode": result["mode"], "page_id": page_id,
        "block_id": result["block_id"],
        "preserved_segments": result["preserved_segments"],
        "limitations": result["limitations"],
    }


def media_inspect(page: str, block_id: str) -> dict[str, Any]:
    """Read an existing image caption or table without exposing image URLs."""
    return notion_media.inspect(page, block_id)


def media_plan(
    runtime: Path, page: str, block_id: str, row_id: str | None,
    cell_index: int | None, segment_index: int, new_text: str,
) -> dict[str, Any]:
    page_id = notion_write._id(page)
    folder = _store(runtime)
    name = secrets.token_hex(16)
    output = folder / (name + ".plan.json")
    result = notion_media.preview(
        page_id, block_id, row_id, cell_index, segment_index, new_text, output,
    )
    return {
        "mode": result["mode"], "page_id": page_id,
        "block_id": result["block_id"], "plan_id": name,
        "manifest_sha256": result["manifest_sha256"],
        "diff": result["diff"], "remote_writes": False,
    }


def media_apply(
    runtime: Path, plan_id: str, page: str,
    approve_page: str, approve_manifest: str, human_approved: object,
) -> dict[str, Any]:
    if human_approved is not True:
        raise notion_write.NotionWriteError("approbation humaine requise")
    if PLAN_ID.fullmatch(plan_id) is None:
        raise notion_write.NotionWriteError("identifiant de plan invalide")
    page_id = notion_write._id(page)
    if notion_write._id(approve_page) != page_id:
        raise notion_write.NotionWriteError("page approuvée différente")
    if notion_write.SHA256.fullmatch(approve_manifest) is None:
        raise notion_write.NotionWriteError("empreinte SHA-256 requise")
    path = _store(runtime) / (plan_id + ".plan.json")
    result = notion_media.apply(path, page_id, approve_manifest)
    return {
        "mode": result["mode"], "page_id": page_id,
        "block_id": result["block_id"], "target_id": result["target_id"],
        "limitations": result["limitations"],
    }
