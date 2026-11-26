"""Create a NEW Notion child page from a bounded editorial plan, operator only.

No updates to existing content, local media uploads, database operations or agent tool.
Plan and receipt are local/private. No retries on ambiguous network writes.
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from clawfedora import notion_write as nw
from clawfedora import source_connectors

TEXT_TYPES = frozenset({
    "paragraph", "heading_1", "heading_2", "heading_3", "bulleted_list_item",
    "numbered_list_item", "quote",
})
COLORS = frozenset({
    "default", "gray_background", "blue_background", "yellow_background",
    "purple_background",
})
ICONS = frozenset({"🧭", "🔎", "🧰", "🛠️", "📈", "📚", "💡", "⚠️"})
LANGUAGES = frozenset({"plain text", "bash", "json", "yaml", "python", "sql"})


def _rich(text: object) -> list[dict[str, Any]]:
    return [{"type": "text", "text": {"content": nw._text(text)}}]


# Only immutable, public GitHub media paths; no signed URL, credentials or query.
PUBLIC_IMAGE = re.compile(
    r"https://raw\.githubusercontent\.com/[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+/"
    r"[0-9a-f]{40}/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_.-]+\.(?:svg|png|jpg|jpeg)\Z"
)
PAGE_LINK = re.compile(
    r"https://(?:github\.com/[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+/"
    r"(?:blob|tree)/[0-9a-f]{40}/[A-Za-z0-9_./-]+"
    r"|(?:app\.notion\.com/p|www\.notion\.so)/[0-9a-f]{32})\Z"
)


def _public_image(url: object) -> dict[str, Any]:
    if (
        not isinstance(url, str) or len(url) > 500 or PUBLIC_IMAGE.fullmatch(url) is None
        or ".." in url
    ):
        raise nw.NotionWriteError("image publique : URL GitHub brute et commit complet requis")
    return {"type": "external", "external": {"url": url}}


def _spans(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not 1 <= len(value) <= 12:
        raise nw.NotionWriteError("texte enrichi limité à 12 segments")
    result = []
    for entry in value:
        if (
            not isinstance(entry, dict) or "text" not in entry
            or not set(entry) <= {"text", "bold", "italic", "code", "url"}
        ):
            raise nw.NotionWriteError("segment éditorial inconnu")
        part = _rich(entry["text"])[0]
        annotations = {}
        for key in ("bold", "italic", "code"):
            if key in entry:
                if type(entry[key]) is not bool:
                    raise nw.NotionWriteError("annotation booléenne requise")
                annotations[key] = entry[key]
        if annotations:
            part["annotations"] = annotations
        if "url" in entry:
            url = entry["url"]
            if (
                not isinstance(url, str) or len(url) > 500
                or PAGE_LINK.fullmatch(url) is None or ".." in url
            ):
                raise nw.NotionWriteError("lien stable GitHub ou Notion requis")
            part["text"]["link"] = {"url": url}
        result.append(part)
    return result


def _block(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"object": "block", "type": kind, kind: payload}


def _compile(entry: object, *, nested: bool = False) -> dict[str, Any]:
    if not isinstance(entry, dict) or not isinstance(entry.get("type"), str):
        raise nw.NotionWriteError("bloc éditorial mal formé")
    kind = entry["type"]
    if kind in TEXT_TYPES and set(entry) == {"type", "text"}:
        return _block(kind, {"rich_text": _rich(entry["text"])})
    if kind in TEXT_TYPES and set(entry) == {"type", "spans"}:
        return _block(kind, {"rich_text": _spans(entry["spans"])})
    if kind == "image" and set(entry) == {"type", "url", "caption"}:
        image = _public_image(entry["url"])
        image["caption"] = _rich(entry["caption"])
        return _block(kind, image)
    if kind == "code" and set(entry) == {"type", "text", "language"}:
        if not isinstance(entry["language"], str) or entry["language"] not in LANGUAGES:
            raise nw.NotionWriteError("langage de code non pris en charge")
        return _block(kind, {
            "rich_text": _rich(entry["text"]), "language": entry["language"],
        })
    if kind in {"divider", "table_of_contents"} and set(entry) == {"type"}:
        return _block(kind, {})
    if kind == "callout" and set(entry) == {"type", "text", "icon", "color"}:
        icon, color = entry["icon"], entry["color"]
        if not isinstance(icon, str) or icon not in ICONS:
            raise nw.NotionWriteError("icône non prise en charge")
        if not isinstance(color, str) or color not in COLORS:
            raise nw.NotionWriteError("couleur non prise en charge")
        return _block(kind, {
            "rich_text": _rich(entry["text"]), "icon": {"type": "emoji", "emoji": icon},
            "color": color,
        })
    if nested:
        raise nw.NotionWriteError("imbrication ou type de bloc non pris en charge")
    if kind == "toggle" and set(entry) == {"type", "text", "children"}:
        return _block(kind, {
            "rich_text": _rich(entry["text"]), "children": _children(entry["children"]),
        })
    if kind == "columns" and set(entry) == {"type", "columns"}:
        columns = entry["columns"]
        if not isinstance(columns, list) or len(columns) != 2:
            raise nw.NotionWriteError("deux colonnes exactement")
        return _block("column_list", {"children": [
            _block("column", {"children": _children(column)}) for column in columns
        ]})
    if kind == "table" and set(entry) == {"type", "rows"}:
        rows = entry["rows"]
        if not isinstance(rows, list) or not 2 <= len(rows) <= 12:
            raise nw.NotionWriteError("tableau de 2 à 12 lignes, en-tête inclus")
        if not isinstance(rows[0], list) or not 2 <= len(rows[0]) <= 5:
            raise nw.NotionWriteError("tableau de 2 à 5 colonnes")
        width = len(rows[0])
        children = []
        for row in rows:
            if not isinstance(row, list) or len(row) != width:
                raise nw.NotionWriteError("lignes de tableau non rectangulaires")
            children.append(_block("table_row", {"cells": [_rich(cell) for cell in row]}))
        return _block("table", {
            "table_width": width, "has_column_header": True,
            "has_row_header": False, "children": children,
        })
    raise nw.NotionWriteError("type de bloc ou champs non autorisés")


def _children(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not 1 <= len(value) <= 8:
        raise nw.NotionWriteError("groupe de 1 à 8 blocs")
    return [_compile(entry, nested=True) for entry in value]


def compile_spec(spec: object, parent_id: str) -> dict[str, Any]:
    if (
        not isinstance(spec, dict) or not {"title", "blocks"} <= set(spec)
        or not set(spec) <= {"title", "blocks", "cover", "icon"}
    ):
        raise nw.NotionWriteError("schéma requis : title, blocks ; cover et icon facultatifs")
    if not isinstance(spec["title"], str) or len(spec["title"]) > 160:
        raise nw.NotionWriteError("titre trop long ou invalide")
    blocks = spec["blocks"]
    if not isinstance(blocks, list) or not 1 <= len(blocks) <= 30:
        raise nw.NotionWriteError("page limitée à 30 blocs directs")
    payload = {
        "parent": {"type": "page_id", "page_id": nw._id(parent_id)},
        "properties": {"title": {"type": "title", "title": _rich(spec["title"])}},
        "children": [_compile(entry) for entry in blocks],
    }
    if "cover" in spec:
        payload["cover"] = _public_image(spec["cover"])
    if "icon" in spec:
        icon = spec["icon"]
        if not isinstance(icon, str) or icon not in ICONS:
            raise nw.NotionWriteError("icône non prise en charge")
        payload["icon"] = {"type": "emoji", "emoji": icon}
    if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > 50_000:
        raise nw.NotionWriteError("page compilée trop volumineuse")
    return payload


def _parent_signature(page_id: str) -> str:
    page = nw._request("GET", f"/v1/pages/{page_id}")
    if (
        nw._id(str(page.get("id", ""))) != page_id
        or page.get("archived") is True or page.get("in_trash") is True
        or not isinstance(page.get("last_edited_time"), str)
        or not isinstance(page.get("parent"), dict)
    ):
        raise nw.NotionWriteError("parent Notion absent, modifié ou incompatible")
    return nw._digest({key: page.get(key) for key in (
        "id", "parent", "last_edited_time", "archived", "in_trash",
    )})


def preview(parent: str, spec_file: Path, output: Path) -> dict[str, Any]:
    page_id = nw._id(parent)
    if spec_file.is_symlink() or not spec_file.is_file() or spec_file.stat().st_size > 8000:
        raise nw.NotionWriteError("spécification absente, liée ou trop volumineuse")
    spec = json.loads(spec_file.read_text(encoding="utf-8"))
    payload = compile_spec(spec, page_id)
    plan: dict[str, Any] = {
        "schema": 1, "action": "create_editorial_child", "parent_id": page_id,
        "parent_sha256": _parent_signature(page_id), "spec": spec,
        "created_at": datetime.now(UTC).isoformat(),
    }
    plan["manifest_sha256"] = nw._digest(plan)
    nw._private_new(output, plan)
    return {
        "mode": "EDITORIAL_PAGE_PREVIEW_ONLY", "remote_writes": False,
        "parent_id": page_id, "manifest_sha256": plan["manifest_sha256"],
        "payload_preview": payload, "plan_file": str(output),
    }


def _post_page(payload: dict[str, Any]) -> dict[str, Any]:
    # A single fixed endpoint; existing notion_write._request stays GET/PATCH only.
    request = urllib.request.Request(
        nw.API + "/v1/pages", method="POST",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + nw._token(write=True),
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json", "Accept": "application/json",
        },
    )
    try:
        with urllib.request.build_opener(nw._NoRedirect()).open(request, timeout=20) as response:
            raw = response.read(nw.MAX_REPLY + 1)
    except urllib.error.HTTPError as exc:
        raise nw.NotionWriteError(f"création Notion refusée : HTTP {exc.code}") from None
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        raise nw.NotionWriteError("résultat ambigu : inspecter le parent, ne pas relancer") from exc
    if len(raw) > nw.MAX_REPLY:
        raise nw.NotionWriteError("réponse Notion trop volumineuse")
    result: object = json.loads(raw)
    if not isinstance(result, dict):
        raise nw.NotionWriteError("réponse de création invalide")
    return result


def _matches(expected: object, observed: object) -> bool:
    """Compare the fields we sent, ignoring extra server-managed fields."""
    if isinstance(expected, dict):
        return isinstance(observed, dict) and all(
            key in observed and _matches(value, observed[key])
            for key, value in expected.items() if key != "children"
        )
    if isinstance(expected, list):
        return (
            isinstance(observed, list) and len(expected) == len(observed)
            and all(_matches(left, right) for left, right in zip(expected, observed, strict=True))
        )
    return expected == observed


def _verify_children(
    page_id: str, expected: list[dict[str, Any]], *, depth: int = 0,
) -> None:
    if depth > 2:
        raise nw.NotionWriteError("imbrication distante inattendue")
    try:
        actual = source_connectors._notion_children(page_id)
    except source_connectors.SourceImportError as exc:
        raise nw.NotionWriteError("lecture de vérification impossible") from exc
    if len(actual) != len(expected):
        raise nw.NotionWriteError("nombre de blocs différent de la proposition")
    for wanted, found in zip(expected, actual, strict=True):
        if found.get("archived") is True or found.get("in_trash") is True:
            raise nw.NotionWriteError("bloc créé archivé")
        if not _matches(wanted, found):
            raise nw.NotionWriteError("contenu créé différent de la proposition")
        nested = wanted[wanted["type"]].get("children", [])
        if bool(nested) != found.get("has_children"):
            raise nw.NotionWriteError("structure distante différente de la proposition")
        if nested:
            _verify_children(nw._id(str(found.get("id", ""))), nested, depth=depth + 1)


def apply(plan_file: Path, parent: str, manifest: str) -> dict[str, Any]:
    plan = nw._load(plan_file)
    if set(plan) != {
        "schema", "action", "parent_id", "parent_sha256", "spec",
        "created_at", "manifest_sha256",
    } or plan.get("schema") != 1 or plan.get("action") != "create_editorial_child":
        raise nw.NotionWriteError("schéma de création non autorisé")
    page_id = nw._id(parent)
    digest = plan.pop("manifest_sha256")
    if (
        not isinstance(digest, str) or nw.SHA256.fullmatch(digest) is None
        or digest != manifest or digest != nw._digest(plan) or plan["parent_id"] != page_id
    ):
        raise nw.NotionWriteError("approbation ou empreinte invalide")
    created = datetime.fromisoformat(plan["created_at"])
    if created.utcoffset() is None or not timedelta(0) <= (
        datetime.now(UTC) - created
    ) <= timedelta(hours=24):
        raise nw.NotionWriteError("plan expiré ou horodatage invalide")
    payload = compile_spec(plan["spec"], page_id)
    marker = plan_file.with_name(plan_file.name + ".attempted.json")
    if marker.exists() or marker.is_symlink():
        raise nw.NotionWriteError("plan déjà tenté ; vérifier Notion")
    if _parent_signature(page_id) != plan["parent_sha256"]:
        raise nw.NotionWriteError("parent modifié : refaire le plan")
    # Exact single-use approval; no automatic retry or remote rollback.
    nw._private_new(marker, {"state": "ATTEMPTED", "manifest_sha256": digest})
    result = _post_page(payload)
    created_id = nw._id(str(result.get("id", "")))
    if created_id == page_id:
        raise nw.NotionWriteError("identifiant créé inattendu")
    verified = nw._request("GET", f"/v1/pages/{created_id}")
    actual_parent = verified.get("parent")
    title = verified.get("properties", {}).get("title", {}).get("title")
    if (
        nw._id(str(verified.get("id", ""))) != created_id
        or not isinstance(actual_parent, dict) or actual_parent.get("type") != "page_id"
        or nw._id(str(actual_parent.get("page_id", ""))) != page_id
        or not _matches(payload["properties"]["title"]["title"], title)
        or verified.get("archived") is True or verified.get("in_trash") is True
    ):
        raise nw.NotionWriteError("page créée non vérifiée : inspecter Notion")
    for field in ("cover", "icon"):
        if field in payload and not _matches(payload[field], verified.get(field)):
            raise nw.NotionWriteError("couverture ou icône non vérifiée")
    _verify_children(created_id, payload["children"])
    receipt = {
        "mode": "EDITORIAL_PAGE_API_VERIFIED", "parent_id": page_id,
        "page_id": created_id, "manifest_sha256": digest,
        "limitations": "Aucune inspection graphique, média ou base de données",
    }
    nw._private_new(plan_file.with_name(plan_file.name + ".verified.json"), receipt)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m clawfedora.notion_editorial")
    sub = parser.add_subparsers(dest="action", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--parent", required=True)
    plan.add_argument("--spec", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)
    execute = sub.add_parser("apply")
    execute.add_argument("--plan", type=Path, required=True)
    execute.add_argument("--approve-parent", required=True)
    execute.add_argument("--approve-manifest", required=True)
    execute.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.action == "plan":
            result = preview(args.parent, args.spec, args.output)
        elif args.apply:
            result = apply(args.plan, args.approve_parent, args.approve_manifest)
        else:
            raise nw.NotionWriteError("--apply explicite requis")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, UnicodeError, TypeError, KeyError) as exc:
        print(json.dumps({"mode": "REFUSED_OR_INCOMPLETE", "reason": str(exc)},
                         ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
