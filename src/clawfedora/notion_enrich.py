"""Operator-approved append-only enrichment of a single existing Notion page."""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from clawfedora import notion_editorial as ne
from clawfedora import notion_studio as ns
from clawfedora import notion_studio_preview as sp
from clawfedora import notion_write as nw
from clawfedora.structured_response import parse_response

MAX_ADDITIONS = 8
PLAN_KEYS = {
    "schema", "action", "page_id", "page_sha256", "inventory_sha256",
    "existing_count", "section", "created_at", "manifest_sha256",
}


def _stable(value: Any) -> Any:
    """Hosted file URL/expiry rotate; retain all other fields including edit stamps."""
    if isinstance(value, list):
        return [_stable(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: _stable(item) for key, item in value.items()}
    if value.get("type") == "file" and isinstance(value.get("file"), dict):
        result["file"] = {
            key: _stable(item) for key, item in value["file"].items()
            if key not in {"url", "expiry_time"}
        }
    return result


def _page(page_id: str) -> tuple[str, str]:
    page = ns._request("GET", f"/v1/pages/{page_id}")
    if (
        nw._id(str(page.get("id", ""))) != page_id
        or page.get("archived") is True or page.get("in_trash") is True
        or not isinstance(page.get("last_edited_time"), str)
        or page.get("parent", {}).get("type") not in {"page_id", "workspace"}
    ):
        raise nw.NotionWriteError("page wiki non active ou ligne de base de données")
    # A page modification stamp may legitimately change after append.
    return nw._digest(_stable(page)), nw._digest(_stable({
        key: page.get(key) for key in ("id", "parent", "properties", "icon", "cover",
                                      "archived", "in_trash")
    }))


def _children(page_id: str) -> list[dict[str, Any]]:
    response = ns._request("GET", f"/v1/blocks/{page_id}/children?page_size=100")
    blocks = response.get("results")
    if response.get("has_more") is not False or not isinstance(blocks, list):
        raise nw.NotionWriteError("inventaire direct incomplet : 100 blocs maximum")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for block in blocks:
        if not isinstance(block, dict):
            raise nw.NotionWriteError("bloc non reconnu")
        ident = nw._id(str(block.get("id", "")))
        kind = block.get("type")
        if (
            ident in seen or not isinstance(kind, str) or not isinstance(block.get(kind), dict)
            or not isinstance(block.get("last_edited_time"), str)
            or type(block.get("has_children")) is not bool
            or block.get("archived") is True or block.get("in_trash") is True
        ):
            raise nw.NotionWriteError("inventaire direct non vérifiable")
        seen.add(ident)
        result.append(block)
    return result


def _inventory(blocks: list[dict[str, Any]]) -> str:
    return nw._digest(_stable(blocks))


def _section(value: object) -> tuple[str, list[dict[str, Any]]]:
    if not isinstance(value, dict) or set(value) != {"blocks"}:
        raise nw.NotionWriteError("section : objet blocks uniquement")
    blocks = value["blocks"]
    if not isinstance(blocks, list) or not 2 <= len(blocks) <= MAX_ADDITIONS:
        raise nw.NotionWriteError("section de deux à huit blocs directs")
    first = blocks[0]
    if not isinstance(first, dict) or set(first) != {"type", "text"} or (
        first["type"] != "heading_2"
    ):
        raise nw.NotionWriteError("premier bloc : titre heading_2 simple requis")
    title = nw._text(first["text"])
    if any(isinstance(block, dict) and block.get("type") in {"heading_1", "heading_2"}
           for block in blocks[1:]):
        raise nw.NotionWriteError("une seule section de niveau 2 par opération")
    compiled = [ne._compile(block) for block in blocks]
    if not any(block["type"] in {"paragraph", "callout", "quote", "code",
                                 "bulleted_list_item", "numbered_list_item"}
               for block in compiled[1:]):
        raise nw.NotionWriteError("explication de section requise")
    return title, compiled


def _unique(title: str, blocks: list[dict[str, Any]]) -> None:
    wanted = " ".join(title.casefold().split())
    for block in blocks:
        kind = block["type"]
        if kind in {"heading_1", "heading_2", "heading_3", "toggle"}:
            parts = block[kind].get("rich_text", [])
            if not isinstance(parts, list) or any(not isinstance(p, dict) for p in parts):
                raise nw.NotionWriteError("titre existant non vérifiable")
            old = "".join(str(p.get("plain_text", p.get("text", {}).get("content", "")))
                          for p in parts)
            if " ".join(old.casefold().split()) == wanted:
                raise nw.NotionWriteError("titre de section déjà présent : enrichir sans doublon")


def preview(page: str, source: Path, output: Path) -> dict[str, Any]:
    page_id = nw._id(page)
    ns._safe_path(source)
    ns._safe_path(output)
    if not source.is_file() or source.stat().st_size > 6000:
        raise nw.NotionWriteError("section JSON limitée à 6000 octets")
    section = parse_response(source.read_text(encoding="utf-8"), {"type": "object"})
    title, compiled = _section(section)
    before, _ = _page(page_id)
    existing = _children(page_id)
    if len(existing) + len(compiled) > 100:
        raise nw.NotionWriteError("page finale limitée à 100 blocs directs")
    _unique(title, existing)
    if _page(page_id)[0] != before:
        raise nw.NotionWriteError("page modifiée pendant l'inventaire")
    plan: dict[str, Any] = {
        "schema": 1, "action": "append_editorial_section", "page_id": page_id,
        "page_sha256": before, "inventory_sha256": _inventory(existing),
        "existing_count": len(existing), "section": section,
        "created_at": datetime.now(UTC).isoformat(),
    }
    plan["manifest_sha256"] = nw._digest(plan)
    if len(json.dumps(plan, ensure_ascii=False, indent=2).encode()) + 1 > 12000:
        raise nw.NotionWriteError("plan trop volumineux")
    html = sp.render({
        "home": {"title": "Section à ajouter", "blocks": section["blocks"]},
        "pages": [], "tracker": None,
    }, [], {})
    preview_file = output.with_name(output.name + ".preview.html")
    ns._safe_path(preview_file)
    if preview_file.exists():
        raise nw.NotionWriteError("aperçu déjà présent")
    nw._private_new(output, plan)
    sp.write(preview_file, html)
    return {"mode": "SECTION_PREVIEW_ONLY", "page_id": page_id,
            "manifest_sha256": plan["manifest_sha256"], "existing_count": len(existing),
            "added_count": len(compiled), "plan_file": str(output),
            "preview_file": str(preview_file), "remote_writes": False}


def _plan(path: Path, page: str, digest: str) -> dict[str, Any]:
    ns._safe_path(path)
    plan = nw._load(path)
    if (
        set(plan) != PLAN_KEYS or plan.get("schema") != 1
        or plan.get("action") != "append_editorial_section"
        or plan.get("page_id") != nw._id(page)
        or not nw.SHA256.fullmatch(digest) or plan["manifest_sha256"] != digest
        or nw._digest({k: v for k, v in plan.items() if k != "manifest_sha256"}) != digest
    ):
        raise nw.NotionWriteError("plan ou approbation invalide")
    created = datetime.fromisoformat(plan["created_at"])
    if created.utcoffset() is None or not (
        timedelta(0) <= datetime.now(UTC) - created <= timedelta(hours=24)
    ):
        raise nw.NotionWriteError("plan expiré")
    return plan


def apply(path: Path, page: str, digest: str) -> dict[str, Any]:
    plan = _plan(path, page, digest)
    page_id = nw._id(page)
    title, compiled = _section(plan["section"])
    marker = path.with_name(path.name + ".attempted.json")
    if marker.exists() or marker.is_symlink():
        raise nw.NotionWriteError("plan déjà tenté : inspecter la page, aucune relance")
    before, metadata = _page(page_id)
    existing = _children(page_id)
    if (
        before != plan["page_sha256"] or _inventory(existing) != plan["inventory_sha256"]
        or len(existing) != plan["existing_count"] or len(existing) + len(compiled) > 100
        or _page(page_id)[0] != before
    ):
        raise nw.NotionWriteError("page modifiée depuis l'aperçu")
    _unique(title, existing)
    nw._private_new(marker, {"mode": "APPEND_ATTEMPTED", "page_id": page_id,
                             "manifest_sha256": digest, "count": len(compiled)})
    result = ns._request("PATCH", f"/v1/blocks/{page_id}/children",
                         body={"children": compiled})
    rows = result.get("results")
    if not isinstance(rows, list) or len(rows) != len(compiled):
        raise nw.NotionWriteError("ajout ambigu : vérifier la page avant toute reprise")
    added = [nw._id(str(item.get("id", ""))) for item in rows]
    actual = _children(page_id)
    prefix = actual[:len(existing)]
    suffix = actual[len(existing):]
    if (
        _inventory(prefix) != plan["inventory_sha256"]
        or len(suffix) != len(compiled)
        or [nw._id(str(item["id"])) for item in suffix] != added
        or _page(page_id)[1] != metadata
    ):
        raise nw.NotionWriteError("préservation ou ajout non confirmé : inspecter Notion")
    for expected, observed in zip(compiled, suffix, strict=True):
        kind = expected["type"]
        children = expected[kind].get("children", [])
        if not ne._matches(expected, observed) or bool(children) != observed["has_children"]:
            raise nw.NotionWriteError("bloc ajouté non conforme")
        if children:
            ns._verify_blocks(nw._id(str(observed["id"])), children, depth=1)
    receipt = {"mode": "SECTION_API_READBACK", "page_id": page_id, "manifest_sha256": digest,
               "added_ids": added, "preserved_direct_count": len(existing),
               "preserved_inventory_sha256": plan["inventory_sha256"],
               "limitations": "Sous-arbres existants non relus ; rendu et octets non certifiés"}
    nw._private_new(path.with_name(path.name + ".verified.json"), receipt)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m clawfedora.notion_enrich")
    sub = parser.add_subparsers(dest="action", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--page", required=True)
    plan.add_argument("--section", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)
    execute = sub.add_parser("apply")
    execute.add_argument("--plan", type=Path, required=True)
    execute.add_argument("--approve-page", required=True)
    execute.add_argument("--approve-manifest", required=True)
    execute.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.action == "plan":
            result = preview(args.page, args.section, args.output)
        elif args.apply:
            result = apply(args.plan, args.approve_page, args.approve_manifest)
        else:
            raise nw.NotionWriteError("--apply explicite requis")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, TypeError, KeyError, AttributeError) as exc:
        print(json.dumps({"mode": "REFUSED_OR_INCOMPLETE", "reason": str(exc)},
                         ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
