"""Native synced navigation for freshly created wiki pages only."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from clawfedora import notion_editorial as ne
from clawfedora import notion_write as nw

Request = Callable[..., dict[str, Any]]


def validate(value: object) -> str:
    if not isinstance(value, dict) or set(value) != {"title"}:
        raise nw.NotionWriteError("navigation : titre uniquement, aucun ID externe")
    return nw._text(value["title"])


def _id(value: object) -> str:
    return nw._id(str(value))


def _read(request: Request, page: str) -> list[dict[str, Any]]:
    result = request("GET", f"/v1/blocks/{page}/children?page_size=100")
    rows = result.get("results")
    if (
        result.get("has_more") is not False or not isinstance(rows, list)
        or any(not isinstance(row, dict) for row in rows)
    ):
        raise nw.NotionWriteError("navigation : inventaire incomplet")
    ids = [_id(row.get("id")) for row in rows]
    if len(ids) != len(set(ids)):
        raise nw.NotionWriteError("navigation : blocs dupliqués")
    return rows


def _append(request: Request, page: str, block: dict[str, Any]) -> dict[str, Any]:
    before = _read(request, page)
    result = request("PATCH", f"/v1/blocks/{page}/children", body={"children": [block]})
    rows = result.get("results")
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise nw.NotionWriteError("navigation : écriture ambiguë")
    ident = _id(rows[0].get("id"))
    after = _read(request, page)
    if (
        len(after) != len(before) + 1
        or [_id(row.get("id")) for row in after[:-1]] != [_id(row.get("id")) for row in before]
        or _id(after[-1].get("id")) != ident
        or after[-1].get("type") != "synced_block"
        or after[-1].get("in_trash") is True or after[-1].get("archived") is True
    ):
        raise nw.NotionWriteError("navigation : ajout non confirmé")
    return after[-1]


def create(request: Request, home: str, pages: dict[str, str],
           navigation: dict[str, Any]) -> dict[str, Any]:
    title = validate(navigation)
    if not 2 <= len(pages) <= 7 or list(pages.values())[0] != home:
        raise nw.NotionWriteError("navigation : accueil et sous-pages créés requis")
    if len(set(pages.values())) != len(pages):
        raise nw.NotionWriteError("navigation : identifiants de pages dupliqués")
    # The only targets are fresh IDs returned by studio creation.
    links = []
    for label, page_id in pages.items():
        links.append(ne._block("bulleted_list_item", {
            "rich_text": ne._spans([{"text": label, "url": f"https://www.notion.so/{page_id}"}]),
        }))
    children = [ne._block("paragraph", {"rich_text": ne._spans([
        {"text": title, "bold": True},
    ])}), *links]
    original = _append(request, home, ne._block("synced_block", {
        "synced_from": None, "children": children,
    }))
    origin = _id(original.get("id"))
    if original.get("synced_block", {}).get("synced_from", "missing") is not None:
        raise nw.NotionWriteError("navigation : original non confirmé")
    observed = _read(request, origin)
    if not ne._matches(children, observed):
        raise nw.NotionWriteError("navigation : liens de l'original différents")
    copies: list[dict[str, str]] = []
    for page_id in list(pages.values())[1:]:
        duplicate = _append(request, page_id, ne._block("synced_block", {
            "synced_from": {"type": "block_id", "block_id": origin},
        }))
        pointer = duplicate.get("synced_block", {}).get("synced_from")
        if (
            not isinstance(pointer, dict) or pointer.get("type") != "block_id"
            or _id(pointer.get("block_id")) != origin
        ):
            raise nw.NotionWriteError("navigation : copie liée au mauvais original")
        copies.append({"page_id": page_id, "block_id": _id(duplicate.get("id"))})
    if not ne._matches(children, _read(request, origin)):
        raise nw.NotionWriteError("navigation : original modifié pendant la création")
    return {"original_block_id": origin, "copies": copies,
            "verified_links": len(links), "mode": "SYNC_POINTERS_READBACK"}
