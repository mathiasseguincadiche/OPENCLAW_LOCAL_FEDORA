"""Bounded, operator-selected native Notion inventory (GET only)."""
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlencode

from clawfedora import notion_write as nw

VERSION = "2026-03-11"
ASSESSMENT = "NATIVE_STRUCTURE_CAPTURED_REVIEW_REQUIRED"
SCHEMA = 2
MAX_REQUESTS = 400
MAX_OBJECTS = 2000
MAX_DEPTH = 16
MAX_PAGINATION = 20
ID = r"[0-9a-f]{32}"
OBJECT_PATH = re.compile(rf"/v1/(pages|databases|data_sources|views)/{ID}")
CHILD_PATH = re.compile(rf"/v1/blocks/{ID}/children")
CURSOR = re.compile(r"[A-Za-z0-9_-]{1,200}")
MEDIA = {"image", "file", "pdf", "audio", "video", "embed", "bookmark"}
BASE_LIMITS = frozenset({
    "permissions_and_sharing_not_verified",
    "database_rows_and_progress_not_read",
    "media_bytes_and_native_render_not_verified",
    "non_atomic_snapshot_no_concurrent_edit",
    "hosted_file_urls_excluded_from_fingerprints",
    "dashboard_widgets_and_external_links_not_traversed",
})
OPTIONAL_LIMITS = frozenset({
    "synced_copies_not_traversed",
    "links_or_unsupported_blocks_not_traversed",
})
TRANSPORT_METADATA = {"parent", "created_time", "created_by", "last_edited_time", "last_edited_by"}


def _get(path: str, params: dict[str, str]) -> dict[str, Any]:
    if OBJECT_PATH.fullmatch(path):
        allowed = not params
    elif CHILD_PATH.fullmatch(path):
        allowed = set(params) <= {"page_size", "start_cursor"}
    elif path == "/v1/views":
        allowed = (
            set(params) <= {"database_id", "page_size", "start_cursor"}
            and re.fullmatch(ID, params.get("database_id", "")) is not None
        )
    else:
        allowed = False
    if (
        not allowed or ("start_cursor" in params and not CURSOR.fullmatch(params["start_cursor"]))
        or ("page_size" in params and params["page_size"] != "100")
    ):
        raise nw.NotionWriteError("endpoint inventaire interdit")
    url = nw.API + path + ("?" + urlencode(params) if params else "")
    request = urllib.request.Request(url, method="GET", headers={
        "Authorization": "Bearer " + nw._token(write=False),
        "Notion-Version": VERSION, "Accept": "application/json",
    })
    try:
        with urllib.request.build_opener(nw._NoRedirect()).open(request, timeout=20) as reply:
            raw = reply.read(nw.MAX_REPLY + 1)
    except urllib.error.HTTPError as exc:
        raise nw.NotionWriteError(f"inventaire Notion : HTTP {exc.code}") from None
    except (OSError, urllib.error.URLError) as exc:
        raise nw.NotionWriteError("lecture Notion interrompue") from exc
    if len(raw) > nw.MAX_REPLY:
        raise nw.NotionWriteError("réponse trop volumineuse")
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise nw.NotionWriteError("réponse non objet")
    return cast(dict[str, Any], result)


def _identifier(value: object) -> str:
    if not isinstance(value, str):
        raise nw.NotionWriteError("identifiant absent")
    return nw._id(value)


def _parent(obj: dict[str, Any], ident: str, kinds: set[str]) -> None:
    parent = obj.get("parent")
    if not isinstance(parent, dict):
        raise nw.NotionWriteError("parent non vérifiable")
    kind = parent.get("type")
    if not isinstance(kind, str) or kind not in kinds or _identifier(parent.get(kind)) != ident:
        raise nw.NotionWriteError("objet hors du wiki autorisé")


def _stable(value: Any) -> Any:
    """Exclude transient hosted file URLs, but retain external URL in the hash."""
    if isinstance(value, list):
        return [_stable(item) for item in value]
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key == "file" and isinstance(item, dict):
                result[key] = _stable({
                    k: v for k, v in item.items() if k not in {"url", "expiry_time"}
                })
            else:
                result[key] = _stable(item)
        return result
    return value


def _text_hash(payload: dict[str, Any]) -> str | None:
    parts = payload.get("rich_text")
    if not isinstance(parts, list) or not parts:
        return None
    if any(not isinstance(part, dict) or not isinstance(part.get("plain_text"), str)
           for part in parts):
        return None
    text = "".join(part["plain_text"] for part in parts)
    if not text.strip():
        return None
    return nw._digest(" ".join(text.casefold().split()))


class Inventory:
    def __init__(self) -> None:
        self.requests = 0
        self.rows: list[dict[str, Any]] = []
        self.seen: set[tuple[str, str]] = set()
        self.last_request: float | None = None
        self.limits = set(BASE_LIMITS)

    def get(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        if self.requests >= MAX_REQUESTS:
            raise nw.NotionWriteError("budget de requêtes dépassé")
        if self.last_request is not None:
            time.sleep(max(0.0, 0.35 - (time.monotonic() - self.last_request)))
        self.last_request = time.monotonic()
        self.requests += 1
        return _get(path, params or {})

    def list_items(self, path: str, params: dict[str, str]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        seen_cursors: set[str] = set()
        query = {**params, "page_size": "100"}
        for _ in range(MAX_PAGINATION):
            result = self.get(path, query)
            items, more = result.get("results"), result.get("has_more")
            if not isinstance(items, list) or type(more) is not bool or len(items) > 100:
                raise nw.NotionWriteError("pagination invalide")
            if any(not isinstance(item, dict) for item in items):
                raise nw.NotionWriteError("élément de liste invalide")
            status = result.get("request_status")
            if status is not None and (
                not isinstance(status, dict) or status.get("type") != "complete"
            ):
                raise nw.NotionWriteError("liste Notion incomplète")
            rows.extend(items)
            if len(rows) > MAX_OBJECTS:
                raise nw.NotionWriteError("liste trop volumineuse")
            cursor = result.get("next_cursor")
            if not more:
                if cursor is not None:
                    raise nw.NotionWriteError("curseur final divergent")
                return rows
            if (
                not isinstance(cursor, str) or not CURSOR.fullmatch(cursor)
                or cursor in seen_cursors or not items
            ):
                raise nw.NotionWriteError("curseur invalide ou répété")
            seen_cursors.add(cursor)
            query["start_cursor"] = cursor
        raise nw.NotionWriteError("pagination trop longue")

    def record(self, category: str, ident: str, obj: dict[str, Any],
               parent: str | None, position: int | None, **metadata: Any) -> None:
        if (category, ident) in self.seen or len(self.rows) >= MAX_OBJECTS:
            raise nw.NotionWriteError("objet répété ou budget dépassé")
        if obj.get("archived") is True or obj.get("in_trash") is True:
            raise nw.NotionWriteError("objet archivé rencontré : vérifier le périmètre")
        self.seen.add((category, ident))
        stable = _stable(obj)
        observable = {key: value for key, value in stable.items() if key not in TRANSPORT_METADATA}
        self.rows.append({
            "category": category, "id": ident, "parent_id": parent, "position": position,
            "sha256": nw._digest(stable), "observable_sha256": nw._digest(observable), **metadata,
        })

    def object(self, category: str, ident: str) -> dict[str, Any]:
        plural = {"page": "pages", "database": "databases",
                  "data_source": "data_sources", "view": "views"}[category]
        result = self.get(f"/v1/{plural}/{ident}")
        if _identifier(result.get("id")) != ident or result.get("object") != category:
            raise nw.NotionWriteError("identité d'objet divergente")
        return result

    def page(self, ident: str, parent: str | None, depth: int) -> None:
        obj = self.object("page", ident)
        if parent is not None:
            _parent(obj, parent, {"page_id", "block_id"})
        self.record("page", ident, obj, parent, None,
                    cover_present=obj.get("cover") is not None,
                    icon_present=obj.get("icon") is not None)
        self.children(ident, depth)

    def children(self, parent: str, depth: int) -> None:
        if depth > MAX_DEPTH:
            raise nw.NotionWriteError("profondeur du wiki dépassée")
        for position, block in enumerate(self.list_items(f"/v1/blocks/{parent}/children", {})):
            ident, kind = _identifier(block.get("id")), block.get("type")
            if (
                block.get("object") != "block" or not isinstance(kind, str)
                or not isinstance(block.get(kind), dict)
                or type(block.get("has_children")) is not bool
            ):
                raise nw.NotionWriteError("bloc non vérifiable")
            _parent(block, parent, {"page_id", "block_id"})
            payload = block[kind]
            self.record(
                "block", ident, block, parent, position, type=kind,
                has_children=block["has_children"], text_sha256=_text_hash(payload),
                media=kind in MEDIA,
            )
            if kind == "child_page":
                self.page(ident, parent, depth + 1)
            elif kind == "child_database":
                self.database(ident, parent)
            elif kind == "synced_block" and payload.get("synced_from") is not None:
                self.limits.add("synced_copies_not_traversed")
            elif kind in {"link_to_page", "unsupported"}:
                self.limits.add("links_or_unsupported_blocks_not_traversed")
            elif block["has_children"]:
                self.children(ident, depth + 1)

    def database(self, ident: str, parent: str) -> None:
        obj = self.object("database", ident)
        _parent(obj, parent, {"page_id", "block_id"})
        sources = obj.get("data_sources")
        if not isinstance(sources, list) or len(sources) > 100:
            raise nw.NotionWriteError("sources de données non vérifiables")
        self.record("database", ident, obj, parent, None)
        for ref in sources:
            if not isinstance(ref, dict):
                raise nw.NotionWriteError("référence de source invalide")
            source_id = _identifier(ref.get("id"))
            source = self.object("data_source", source_id)
            _parent(source, ident, {"database_id"})
            properties = source.get("properties")
            if not isinstance(properties, dict):
                raise nw.NotionWriteError("schéma de propriétés absent")
            kinds: Counter[str] = Counter()
            for prop in properties.values():
                if not isinstance(prop, dict) or not isinstance(prop.get("type"), str):
                    raise nw.NotionWriteError("propriété non vérifiable")
                kinds[prop["type"]] += 1
            self.record("data_source", source_id, source, ident, None,
                        property_types=dict(kinds), properties_sha256=nw._digest(_stable(properties)))
        for position, ref in enumerate(self.list_items("/v1/views", {"database_id": ident})):
            view_id = _identifier(ref.get("id"))
            view = self.object("view", view_id)
            _parent(view, ident, {"database_id"})
            kind = view.get("type")
            if not isinstance(kind, str):
                raise nw.NotionWriteError("type de vue absent")
            self.record("view", view_id, view, ident, position, type=kind,
                        filter_present=view.get("filter") is not None,
                        sort_count=len(view.get("sorts") or []))


def capture(root: str) -> dict[str, Any]:
    root = nw._id(root)
    inventory = Inventory()
    inventory.page(root, None, 0)
    body: dict[str, Any] = {
        "schema": SCHEMA, "classification": "private_local_only",
        "assessment": ASSESSMENT,
        "root_page": root, "api_version": VERSION,
        "captured_at": datetime.now(UTC).isoformat(),
        "objects": inventory.rows,
        "counts": dict(Counter(row["category"] for row in inventory.rows)),
        "requests": inventory.requests,
        "limitations": sorted(inventory.limits),
        "remote_write": False, "native_render_verified": False,
    }
    body["structure_sha256"] = nw._digest(body["objects"])
    body["inventory_sha256"] = nw._digest(body)
    return body


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inventaire natif Notion privé en lecture seule")
    parser.add_argument("--page", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--capture", action="store_true")
    args = parser.parse_args(argv)
    try:
        root = nw._id(args.page)
        output = args.output.absolute()
        if not args.capture:
            print("NOTION_NATIVE_INVENTORY=PLAN aucun accès réseau")
            return 0
        if (
            any(p.is_symlink() for p in (output, *output.parents))
            or not output.parent.is_dir() or output.exists()
            or output.parent.stat().st_mode & 0o077
            or any((p / ".git").exists() for p in output.parents)
        ):
            raise nw.NotionWriteError("destination privée hors Git, mode 0700 et fichier neuf requis")
        report = capture(root)
        nw._private_new(output, report)
        print(json.dumps({"assessment": report["assessment"], "counts": report["counts"],
                          "structure_sha256": report["structure_sha256"]}))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"NOTION_NATIVE_INVENTORY=REFUSED {type(exc).__name__}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
