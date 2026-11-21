"""Conservative Notion multi-block text change sets, scoped to one existing page.

The operator, not the model, selects a page and exactly which simple blocks to edit.
This is not a full Notion page editor: rich blocks, inserts, deletes and reordering
are intentionally refused. Notion has no atomic multi-block transaction.
"""

from __future__ import annotations

import argparse
import difflib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from clawfedora import notion_write as nw
from clawfedora import source_connectors

MAX_EDITS = 5
MAX_TOTAL_TEXT = 7000
MAX_CHILDREN = 500
PLAN_KEYS = frozenset({
    "schema", "action", "page_id", "created_at", "inventory_sha256", "edits",
    "manifest_sha256",
})
EDIT_KEYS = frozenset({"block_id", "type", "old_sha256", "new_text"})


def _inventory(page_id: str) -> tuple[list[dict[str, Any]], str]:
    """Read every direct child, never silently accept partial or reordered contents."""
    page = nw._request("GET", f"/v1/pages/{page_id}")
    if nw._id(str(page.get("id", ""))) != page_id or page.get("archived") is True:
        raise nw.NotionWriteError("page absente ou archivée")
    try:
        blocks = source_connectors._notion_children(page_id)
    except source_connectors.SourceImportError as exc:
        raise nw.NotionWriteError("inventaire Notion impossible ou incomplet") from exc
    if len(blocks) > MAX_CHILDREN:
        raise nw.NotionWriteError("page trop volumineuse pour un lot sûr")
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for block in blocks:
        if not isinstance(block, dict):
            raise nw.NotionWriteError("inventaire de blocs invalide")
        block_id = nw._id(str(block.get("id", "")))
        kind = block.get("type")
        if (
            block_id in seen or not isinstance(kind, str) or not kind
            or type(block.get("has_children")) is not bool
            or type(block.get("archived")) is not bool
        ):
            raise nw.NotionWriteError("inventaire de blocs incomplet ou dupliqué")
        seen.add(block_id)
        output.append({
            "id": block_id, "type": kind, "has_children": block["has_children"],
            "archived": block["archived"],
        })
    if not output:
        raise nw.NotionWriteError("page vide : aucun bloc éditable")
    return output, nw._digest(output)


def _read_edits(path: Path) -> list[dict[str, str]]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 14_000:
        raise nw.NotionWriteError("fichier de propositions absent ou non sûr")
    try:
        contents: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise nw.NotionWriteError("fichier de propositions JSON invalide") from exc
    if not isinstance(contents, dict) or set(contents) != {"edits"}:
        raise nw.NotionWriteError("format attendu : objet JSON avec edits uniquement")
    entries = contents["edits"]
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_EDITS:
        raise nw.NotionWriteError("entre 1 et 5 modifications textuelles requises")
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    total = 0
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"block_id", "text"}:
            raise nw.NotionWriteError("chaque modification requiert block_id et text")
        block_id = nw._id(str(entry["block_id"]))
        proposed = nw._text(entry["text"])
        if block_id in seen:
            raise nw.NotionWriteError("bloc répété dans un même lot")
        total += len(proposed)
        if total > MAX_TOTAL_TEXT:
            raise nw.NotionWriteError("lot trop volumineux")
        seen.add(block_id)
        result.append({"block_id": block_id, "text": proposed})
    return result


def preview(page: str, edits_file: Path, output: Path) -> dict[str, Any]:
    page_id = nw._id(page)
    entries = _read_edits(edits_file)
    inventory, inventory_hash = _inventory(page_id)
    allowed = {
        value["id"]: value for value in inventory
        if not value["archived"] and not value["has_children"]
    }
    revisions: list[dict[str, str]] = []
    diffs: list[dict[str, str]] = []
    for entry in entries:
        block_id, new_text = entry["block_id"], entry["text"]
        if block_id not in allowed:
            raise nw.NotionWriteError("bloc absent, archivé ou possédant des enfants")
        block, kind, old_text = nw._block(page_id, block_id)
        if allowed[block_id]["type"] != kind:
            raise nw.NotionWriteError("type du bloc différent de l'inventaire")
        if new_text == old_text:
            raise nw.NotionWriteError("modification identique au texte existant")
        revisions.append({
            "block_id": block_id, "type": kind, "old_sha256": nw._fingerprint(block, kind),
            "new_text": new_text,
        })
        diffs.append({
            "block_id": block_id, "diff": "\n".join(difflib.unified_diff(
                old_text.splitlines(), new_text.splitlines(), fromfile="Texte actuel",
                tofile="Texte proposé", lineterm="",
            )),
        })
    plan: dict[str, Any] = {
        "schema": 1, "action": "replace_plain_text_batch", "page_id": page_id,
        "created_at": datetime.now(UTC).isoformat(),
        "inventory_sha256": inventory_hash, "edits": revisions,
    }
    plan["manifest_sha256"] = nw._digest(plan)
    nw._private_new(output, plan)
    return {
        "mode": "BATCH_PREVIEW_ONLY", "page_id": page_id,
        "plan_file": str(output), "manifest_sha256": plan["manifest_sha256"],
        "edits": diffs,
        "protected_blocks_untouched": len(inventory) - len(entries),
        "remote_writes": False,
    }


def _validated_plan(plan_file: Path, page: str, manifest: str) -> dict[str, Any]:
    plan = nw._load(plan_file)
    if set(plan) != PLAN_KEYS or plan.get("schema") != 1 or plan.get(
        "action",
    ) != "replace_plain_text_batch":
        raise nw.NotionWriteError("schéma de plan non autorisé")
    digest = plan["manifest_sha256"]
    if (
        not isinstance(digest, str) or digest != manifest
        or not nw.SHA256.fullmatch(digest)
        or nw._digest({k: v for k, v in plan.items() if k != "manifest_sha256"}) != digest
        or nw._id(page) != plan["page_id"]
    ):
        raise nw.NotionWriteError("empreinte, page ou intégrité du plan invalide")
    try:
        created_at = datetime.fromisoformat(plan["created_at"])
    except (TypeError, ValueError) as exc:
        raise nw.NotionWriteError("horodatage du plan invalide") from exc
    age = datetime.now(UTC) - created_at
    if created_at.utcoffset() is None or not timedelta(0) <= age <= timedelta(hours=24):
        raise nw.NotionWriteError("plan expiré")
    if not isinstance(plan["inventory_sha256"], str) or not nw.SHA256.fullmatch(
        plan["inventory_sha256"],
    ):
        raise nw.NotionWriteError("inventaire invalide")
    edits = plan["edits"]
    if not isinstance(edits, list) or not 1 <= len(edits) <= MAX_EDITS:
        raise nw.NotionWriteError("nombre de modifications interdit")
    total = 0
    seen: set[str] = set()
    for edit in edits:
        if not isinstance(edit, dict) or set(edit) != EDIT_KEYS:
            raise nw.NotionWriteError("entrée de plan invalide")
        block_id = nw._id(edit["block_id"])
        if (
            block_id in seen or edit["type"] not in nw.EDIT_TYPES
            or not isinstance(edit["old_sha256"], str)
            or not nw.SHA256.fullmatch(edit["old_sha256"])
        ):
            raise nw.NotionWriteError("bloc, type ou empreinte invalide")
        total += len(nw._text(edit["new_text"]))
        if total > MAX_TOTAL_TEXT:
            raise nw.NotionWriteError("taille du plan dépassée")
        seen.add(block_id)
    return plan


def apply(plan_file: Path, page: str, manifest: str) -> dict[str, Any]:
    plan = _validated_plan(plan_file, page, manifest)
    page_id = nw._id(plan["page_id"])
    marker = plan_file.with_name(plan_file.name + ".attempted.json")
    if marker.exists() or marker.is_symlink():
        raise nw.NotionWriteError("lot déjà tenté : inspecter Notion avant de recommencer")
    inventory, fingerprint = _inventory(page_id)
    if fingerprint != plan["inventory_sha256"]:
        raise nw.NotionWriteError("structure Notion modifiée : préparer un nouveau lot")
    allowed = {item["id"]: item for item in inventory}
    edits = cast(list[dict[str, str]], plan["edits"])
    for edit in edits:
        block_id = edit["block_id"]
        entry = allowed.get(block_id)
        if (
            entry is None or entry["archived"] or entry["has_children"]
            or entry["type"] != edit["type"]
        ):
            raise nw.NotionWriteError("bloc de destination modifié")
        block, kind, old = nw._block(page_id, block_id)
        if (
            kind != edit["type"] or nw._fingerprint(block, kind) != edit["old_sha256"]
            or old == edit["new_text"]
        ):
            raise nw.NotionWriteError("contenu modifié depuis l'aperçu")
    nw._private_new(marker, {
        "state": "ATTEMPTED", "page_id": page_id,
        "manifest_sha256": manifest, "count": len(edits),
        "timestamp": datetime.now(UTC).isoformat(),
    })
    verified: list[str] = []
    for index, edit in enumerate(edits, 1):
        block_id = edit["block_id"]
        # If another actor moves/creates/deletes a sibling, do not continue.
        _, current_structure = _inventory(page_id)
        if current_structure != fingerprint:
            raise nw.NotionWriteError(
                "lot partiellement appliqué possible : structure modifiée, inspecter Notion",
            )
        current, kind, original = nw._block(page_id, block_id)
        if (
            kind != edit["type"] or nw._fingerprint(current, kind) != edit["old_sha256"]
            or original == edit["new_text"]
        ):
            raise nw.NotionWriteError(
                "lot partiellement appliqué possible : bloc modifié, inspecter Notion",
            )
        attempt = plan_file.with_name(plan_file.name + f".step-{index:02d}.attempted.json")
        nw._private_new(attempt, {
            "state": "PATCH_ATTEMPTED", "block_id": block_id,
            "timestamp": datetime.now(UTC).isoformat(),
        })
        result = nw._request("PATCH", f"/v1/blocks/{block_id}", write=True, body={
            kind: {"rich_text": [{"type": "text", "text": {"content": edit["new_text"]}}]},
        })
        if nw._id(str(result.get("id", ""))) != block_id:
            raise nw.NotionWriteError("réponse Notion ambiguë : inspecter tous les blocs du lot")
        _, new_kind, new_text = nw._block(page_id, block_id)
        if new_kind != kind or new_text != edit["new_text"]:
            raise nw.NotionWriteError(
                "résultat Notion non vérifié : inspecter tous les blocs du lot",
            )
        verified.append(block_id)
        receipt = plan_file.with_name(plan_file.name + f".step-{index:02d}.verified.json")
        nw._private_new(receipt, {
            "state": "PATCH_API_VERIFIED", "block_id": block_id,
            "timestamp": datetime.now(UTC).isoformat(),
        })
    return {
        "mode": "BATCH_BLOCKS_API_VERIFIED", "page_id": page_id,
        "manifest_sha256": manifest, "verified_blocks": verified,
        "limitations": "Aucune transaction atomique ni validation visuelle",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clawfedora-notion-batch")
    commands = parser.add_subparsers(dest="action", required=True)
    plan = commands.add_parser("plan", help="diff multi-blocs en lecture seule")
    plan.add_argument("--page", required=True)
    plan.add_argument("--edits-file", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)
    approval = commands.add_parser("apply", help="modifier les blocs précis approuvés")
    approval.add_argument("--plan", type=Path, required=True)
    approval.add_argument("--approve-page", required=True)
    approval.add_argument("--approve-manifest", required=True)
    approval.add_argument("--apply", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.action == "plan":
            result = preview(args.page, args.edits_file, args.output)
        else:
            if not args.apply:
                raise nw.NotionWriteError("--apply explicite requis")
            result = apply(args.plan, args.approve_page, args.approve_manifest)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (
        nw.NotionWriteError, OSError, UnicodeError, TypeError, KeyError,
    ) as exc:
        print(json.dumps({
            "mode": "REFUSED_OR_INCOMPLETE", "reason": str(exc),
            "next_step": "Contrôler Notion et les reçus locaux ; aucun retry implicite.",
        }, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
