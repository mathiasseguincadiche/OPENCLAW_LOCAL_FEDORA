"""Operator-only creation of a fresh wiki, private raster media and a tracker.

Use the current API in isolation. No edits to existing pages, no remote retry,
no deletion, no upload to GitHub, no signed download URL in receipts.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import stat
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from PIL import Image

from clawfedora import notion_curriculum as nc
from clawfedora import notion_editorial as ne
from clawfedora import notion_navigation as nn
from clawfedora import notion_studio_preview as sp
from clawfedora import notion_write as nw

VERSION = "2026-03-11"
ID = r"[0-9a-f]{32}"
READ = re.compile(
    rf"/v1/(?:pages|databases|data_sources|views|file_uploads)/{ID}"
    rf"|/v1/blocks/{ID}/children\?page_size=100"
)
WRITE = re.compile(rf"/v1/(?:pages|databases|views|file_uploads)|/v1/file_uploads/{ID}/send")
MAX_ASSET = 4_000_000
MAX_TOTAL = 12_000_000
MIMES = {".png": ("PNG", "image/png"), ".jpg": ("JPEG", "image/jpeg"),
         ".jpeg": ("JPEG", "image/jpeg")}
NAME = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9_.-]{0,79}\Z")
FIELDS: dict[str, dict[str, Any]] = {
    "Activité": {"title": {}},
    "Ordre": {"number": {"format": "number"}},
    "État": {"select": {"options": [
        {"name": "À réaliser"}, {"name": "En cours"}, {"name": "À vérifier"},
    ]}},
}


def _request(method: str, resource: str, *, body: dict[str, Any] | None = None,
             binary: bytes | None = None, content_type: str = "application/json",
             ) -> dict[str, Any]:
    allowed = (
        method == "GET" and READ.fullmatch(resource) and body is None and binary is None
    ) or (
        method == "POST" and WRITE.fullmatch(resource)
        and ((binary is not None) == resource.endswith("/send"))
        and (body is not None) != (binary is not None)
    )
    allowed = allowed or (
        method == "PATCH" and re.fullmatch(rf"/v1/data_sources/{ID}", resource)
        and body is not None and binary is None
    )
    allowed = allowed or (
        method == "PATCH" and re.fullmatch(rf"/v1/blocks/{ID}/children", resource)
        and binary is None and isinstance(body, dict) and set(body) == {"children"}
        and isinstance(body["children"], list) and 1 <= len(body["children"]) <= 8
    )
    if not allowed:
        raise nw.NotionWriteError("endpoint studio non autorisé")
    payload = binary if binary is not None else (
        json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    )
    request = urllib.request.Request(
        nw.API + resource, data=payload, method=method,
        headers={"Authorization": "Bearer " + nw._token(write=method != "GET"),
                 "Notion-Version": VERSION, "Content-Type": content_type,
                 "Accept": "application/json"},
    )
    try:
        with urllib.request.build_opener(nw._NoRedirect()).open(request, timeout=30) as response:
            raw = response.read(nw.MAX_REPLY + 1)
    except urllib.error.HTTPError as exc:
        raise nw.NotionWriteError(
            f"studio Notion : HTTP {exc.code} ; vérifier avant reprise",
        ) from None
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        raise nw.NotionWriteError("résultat ambigu ; vérifier Notion, aucune relance") from exc
    if len(raw) > nw.MAX_REPLY:
        raise nw.NotionWriteError("réponse trop volumineuse")
    obj = json.loads(raw)
    if not isinstance(obj, dict):
        raise nw.NotionWriteError("réponse invalide")
    return cast(dict[str, Any], obj)


def _safe_path(path: Path) -> None:
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise nw.NotionWriteError("chemin lié interdit")


def _read_asset(root: Path, name: str) -> tuple[dict[str, Any], bytes]:
    if not NAME.fullmatch(name) or ".." in name or Path(name).suffix.lower() not in MIMES:
        raise nw.NotionWriteError("nom simple PNG/JPEG requis")
    path = root / name
    _safe_path(path)
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    with os.fdopen(os.open(path, flags), "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_ASSET:
            raise nw.NotionWriteError("image locale non régulière ou trop grande")
        data = stream.read(MAX_ASSET + 1)
    if len(data) != info.st_size or len(data) > MAX_ASSET:
        raise nw.NotionWriteError("image modifiée pendant la lecture")
    fmt, mime = MIMES[path.suffix.lower()]
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format != fmt or not all(64 <= d <= 4096 for d in image.size):
                raise nw.NotionWriteError("format ou dimensions image invalides")
            if getattr(image, "n_frames", 1) != 1:
                raise nw.NotionWriteError("image animée interdite")
            image.verify()
    except (OSError, Image.DecompressionBombError) as exc:
        raise nw.NotionWriteError("image non lisible") from exc
    return {"name": name, "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data), "mime": mime}, data


def _page_spec(spec: object, parent: str) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(spec, dict) or not set(spec) <= {
        "title", "blocks", "cover", "icon", "cover_file", "images",
    }:
        raise nw.NotionWriteError("champs de page non autorisés")
    payload = ne.compile_spec(
        {k: v for k, v in spec.items() if k not in {"cover_file", "images"}}, parent,
    )
    names: list[str] = []
    if "cover_file" in spec:
        if "cover" in spec or not isinstance(spec["cover_file"], str):
            raise nw.NotionWriteError("une seule couverture")
        names.append(spec["cover_file"])
    images = spec.get("images", [])
    if not isinstance(images, list) or len(images) > 4:
        raise nw.NotionWriteError("quatre images privées par page maximum")
    for entry in images:
        if (
            not isinstance(entry, dict) or set(entry) != {"file", "caption"}
            or not isinstance(entry["file"], str)
        ):
            raise nw.NotionWriteError("image privée mal formée")
        ne._rich(entry["caption"])
        names.append(entry["file"])
    return payload, names


def _spec(spec: object, parent: str) -> list[str]:
    if (
        not isinstance(spec, dict) or not {"home", "pages", "tracker"} <= set(spec)
        or not set(spec) <= {"home", "pages", "tracker", "curriculum", "navigation"}
    ):
        raise nw.NotionWriteError("schéma studio : home, pages, tracker")
    pages = spec["pages"]
    if not isinstance(pages, list) or not 1 <= len(pages) <= 6:
        raise nw.NotionWriteError("une à six sous-pages")
    titles: set[str] = set()
    assets: set[str] = set()
    for page in [spec["home"], *pages]:
        payload, names = _page_spec(page, parent)
        title = payload["properties"]["title"]["title"][0]["text"]["content"]
        if title in titles:
            raise nw.NotionWriteError("titre de page dupliqué")
        titles.add(title)
        assets.update(names)
    tracker = spec["tracker"]
    if tracker is not None:
        if not isinstance(tracker, dict) or set(tracker) != {"title", "activities", "views"}:
            raise nw.NotionWriteError("suivi : title, activities, views")
        nw._text(tracker["title"])
        if tracker["title"] in titles:
            raise nw.NotionWriteError("titre de suivi dupliqué")
        activities, views = tracker["activities"], tracker["views"]
        if not isinstance(activities, list) or not 1 <= len(activities) <= 12:
            raise nw.NotionWriteError("une à douze activités")
        for activity in activities:
            nw._text(activity)
        if len(set(activities)) != len(activities):
            raise nw.NotionWriteError("activité dupliquée")
        if not isinstance(views, list) or any(
            not isinstance(v, str) or v not in {"list", "gallery", "table"} for v in views
        ) or len(set(views)) != len(views):
            raise nw.NotionWriteError("vues autorisées : list, gallery, table")
    if "curriculum" in spec:
        if tracker is not None:
            raise nw.NotionWriteError("un seul suivi : tracker ou parcours relationnel")
        assets.update(nc.validate(spec["curriculum"], titles))
    if "navigation" in spec:
        nn.validate(spec["navigation"])
    if len(assets) > 8:
        raise nw.NotionWriteError("huit fichiers privés maximum")
    return sorted(assets)


def _assets(root: Path, names: list[str]) -> tuple[list[dict[str, Any]], dict[str, bytes]]:
    _safe_path(root)
    if not root.is_dir():
        raise nw.NotionWriteError("dossier de médias absent")
    records: list[dict[str, Any]] = []
    contents: dict[str, bytes] = {}
    for name in names:
        record, data = _read_asset(root, name)
        records.append(record)
        contents[name] = data
    if sum(len(data) for data in contents.values()) > MAX_TOTAL:
        raise nw.NotionWriteError("ensemble de médias trop volumineux")
    return records, contents


def _parent(page_id: str) -> str:
    page = _request("GET", f"/v1/pages/{page_id}")
    if (
        nw._id(str(page.get("id", ""))) != page_id or page.get("in_trash") is True
        or page.get("archived") is True or not isinstance(page.get("last_edited_time"), str)
        or not isinstance(page.get("parent"), dict)
    ):
        raise nw.NotionWriteError("parent absent ou non actif")
    return nw._digest({k: page.get(k) for k in ("id", "parent", "last_edited_time", "in_trash")})


def preview(parent: str, spec_file: Path, media: Path, output: Path) -> dict[str, Any]:
    page_id = nw._id(parent)
    _safe_path(spec_file)
    _safe_path(output)
    if not spec_file.is_file() or spec_file.stat().st_size > 8000:
        raise nw.NotionWriteError("spécification limitée à 8000 octets")
    spec = json.loads(spec_file.read_text(encoding="utf-8"))
    root = media.absolute()
    records, contents = _assets(root, _spec(spec, page_id))
    plan: dict[str, Any] = {
        "schema": 1, "action": "new_wiki", "parent_id": page_id,
        "parent_sha256": _parent(page_id), "media_root": str(root),
        "assets": records, "spec": spec, "created_at": datetime.now(UTC).isoformat(),
    }
    plan["manifest_sha256"] = nw._digest(plan)
    if len(json.dumps(plan, ensure_ascii=False, indent=2).encode()) + 1 > 12000:
        raise nw.NotionWriteError("plan trop volumineux")
    preview_file = output.with_name(output.name + ".preview.html")
    _safe_path(preview_file)
    if preview_file.exists():
        raise nw.NotionWriteError("aperçu déjà présent")
    html = sp.render(spec, records, contents)
    nw._private_new(output, plan)
    sp.write(preview_file, html)
    return {"mode": "STUDIO_PREVIEW_ONLY", "remote_writes": False,
            "plan_file": str(output), "preview_file": str(preview_file), **plan}


def _upload(record: dict[str, Any], data: bytes) -> str:
    created = _request("POST", "/v1/file_uploads", body={
        "mode": "single_part", "filename": record["name"], "content_type": record["mime"],
    })
    ident = nw._id(str(created.get("id", "")))
    if created.get("object") != "file_upload" or created.get("status") != "pending":
        raise nw.NotionWriteError("upload initial non confirmé")
    boundary = uuid4().hex
    header = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
        f'filename="{record["name"]}"\r\nContent-Type: {record["mime"]}\r\n\r\n'
    ).encode()
    sent = _request("POST", f"/v1/file_uploads/{ident}/send",
                    binary=header + data + f"\r\n--{boundary}--\r\n".encode(),
                    content_type=f"multipart/form-data; boundary={boundary}")
    if (
        nw._id(str(sent.get("id", ""))) != ident or sent.get("status") != "uploaded"
        or sent.get("content_length") != record["bytes"]
        or sent.get("content_type") != record["mime"] or sent.get("filename") != record["name"]
    ):
        raise nw.NotionWriteError("transfert de média non confirmé")
    return ident


def _file(ident: str) -> dict[str, Any]:
    return {"type": "file_upload", "file_upload": {"id": ident}}


def _matches_file(wanted: dict[str, Any], actual: object) -> bool:
    if wanted.get("type") != "file_upload":
        return ne._matches(wanted, actual)
    # Notion resolves an attached upload into a hosted file with a temporary URL.
    return (isinstance(actual, dict) and actual.get("type") == "file"
            and isinstance(actual.get("file"), dict)
            and bool(actual["file"].get("url"))
            and ne._matches(wanted.get("caption", []), actual.get("caption", [])))


def _verify_blocks(page_id: str, expected: list[dict[str, Any]], depth: int = 0) -> None:
    if depth > 2:
        raise nw.NotionWriteError("imbrication inattendue")
    reply = _request("GET", f"/v1/blocks/{page_id}/children?page_size=100")
    actual = reply.get("results")
    if reply.get("has_more") or not isinstance(actual, list) or len(actual) != len(expected):
        raise nw.NotionWriteError("structure de page différente")
    for want, found in zip(expected, actual, strict=True):
        kind = want["type"]
        if not isinstance(found, dict) or found.get("type") != kind or found.get("in_trash"):
            raise nw.NotionWriteError("bloc absent ou incompatible")
        value = want[kind]
        same = (_matches_file(value, found.get(kind)) if kind == "image"
                else ne._matches(value, found.get(kind)))
        children = value.get("children", [])
        if not same or bool(children) != found.get("has_children"):
            raise nw.NotionWriteError("contenu de bloc différent")
        if children:
            _verify_blocks(nw._id(str(found.get("id", ""))), children, depth + 1)


def _created_page(spec: dict[str, Any], parent: str, uploads: dict[str, str]) -> str:
    payload, _ = _page_spec(spec, parent)
    if "cover_file" in spec:
        payload["cover"] = _file(uploads[spec["cover_file"]])
    for entry in spec.get("images", []):
        image = {**_file(uploads[entry["file"]]), "caption": ne._rich(entry["caption"])}
        payload["children"].append(ne._block("image", image))
    ident = nw._id(str(_request("POST", "/v1/pages", body=payload).get("id", "")))
    page = _request("GET", f"/v1/pages/{ident}")
    if (
        ident == parent or nw._id(str(page.get("id", ""))) != ident
        or page.get("parent", {}).get("type") != "page_id"
        or nw._id(str(page.get("parent", {}).get("page_id", ""))) != parent
        or page.get("in_trash") or not ne._matches(
            payload["properties"]["title"]["title"], page.get("properties", {}).get(
                "title", {}).get("title"),
        )
    ):
        raise nw.NotionWriteError("page créée non confirmée")
    if "cover" in payload and not _matches_file(payload["cover"], page.get("cover")):
        raise nw.NotionWriteError("couverture non confirmée")
    if "icon" in payload and not ne._matches(payload["icon"], page.get("icon")):
        raise nw.NotionWriteError("icône non confirmée")
    _verify_blocks(ident, payload["children"])
    return ident


def _tracker(parent: str, spec: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "parent": {"type": "page_id", "page_id": parent},
        "title": ne._rich(spec["title"]), "is_inline": True,
        "initial_data_source": {"properties": FIELDS},
    }
    db = nw._id(str(_request("POST", "/v1/databases", body=payload).get("id", "")))
    result = _request("GET", f"/v1/databases/{db}")
    sources = result.get("data_sources", [])
    if (
        nw._id(str(result.get("id", ""))) != db
        or result.get("parent", {}).get("type") != "page_id"
        or nw._id(str(result.get("parent", {}).get("page_id", ""))) != parent
        or result.get("in_trash") is True
        or not ne._matches(payload["title"], result.get("title"))
        or not isinstance(sources, list) or len(sources) != 1
    ):
        raise nw.NotionWriteError("base de suivi non confirmée")
    source = nw._id(str(sources[0].get("id", "")))
    source_reply = _request("GET", f"/v1/data_sources/{source}")
    if nw._id(str(source_reply.get("id", ""))) != source:
        raise nw.NotionWriteError("source de données non confirmée")
    schema = source_reply.get("properties", {})
    if not isinstance(schema, dict) or any(
        schema.get(key, {}).get("type") != next(iter(value)) for key, value in FIELDS.items()
    ):
        raise nw.NotionWriteError("propriétés du suivi non confirmées")
    options = schema["État"]["select"].get("options", [])
    if {item.get("name") for item in options} != {
        "À réaliser", "En cours", "À vérifier",
    }:
        raise nw.NotionWriteError("états initiaux du suivi non confirmés")
    rows: list[str] = []
    views: list[dict[str, str]] = []
    for index, name in enumerate(spec["activities"], 1):
        properties = {"Activité": {"title": ne._rich(name)}, "Ordre": {"number": index},
                      "État": {"select": {"name": "À réaliser"}}}
        row = nw._id(str(_request("POST", "/v1/pages", body={
            "parent": {"type": "data_source_id", "data_source_id": source},
            "properties": properties,
        }).get("id", "")))
        observed = _request("GET", f"/v1/pages/{row}")
        if (
            nw._id(str(observed.get("id", ""))) != row
            or observed.get("parent", {}).get("type") != "data_source_id"
            or nw._id(str(observed.get("parent", {}).get("data_source_id", ""))) != source
            or observed.get("in_trash") is True
            or not ne._matches(properties, observed.get("properties"))
        ):
            raise nw.NotionWriteError("activité non confirmée")
        rows.append(row)
    for kind in spec["views"]:
        name = {"list": "Parcours", "gallery": "Galerie", "table": "Suivi ordonné"}[kind]
        definition = {"database_id": db, "data_source_id": source, "name": name,
                      "type": kind, "sorts": [{"property": "Ordre", "direction": "ascending"}]}
        view = nw._id(str(_request("POST", "/v1/views", body=definition).get("id", "")))
        actual = _request("GET", f"/v1/views/{view}")
        if (
            nw._id(str(actual.get("id", ""))) != view or actual.get("name") != name
            or actual.get("type") != kind
            or nw._id(str(actual.get("parent", {}).get("database_id", ""))) != db
        ):
            raise nw.NotionWriteError("vue non confirmée")
        sorts = actual.get("sorts")
        if not isinstance(sorts, list) or len(sorts) != 1 or (
            sorts[0].get("property") not in ("Ordre", schema["Ordre"].get("id"))
            or sorts[0].get("direction") != "ascending"
        ):
            raise nw.NotionWriteError("tri de la vue non confirmé")
        views.append({"id": view, "type": kind})
    return {"database_id": db, "data_source_id": source, "rows": rows, "views": views}


def apply(plan_file: Path, parent: str, manifest: str) -> dict[str, Any]:
    _safe_path(plan_file)
    plan = nw._load(plan_file)
    if set(plan) != {
        "schema", "action", "parent_id", "parent_sha256", "media_root",
        "assets", "spec", "created_at", "manifest_sha256",
    } or plan["schema"] != 1 or plan["action"] != "new_wiki":
        raise nw.NotionWriteError("plan studio invalide")
    page_id = nw._id(parent)
    digest = plan.pop("manifest_sha256")
    if digest != manifest or digest != nw._digest(plan) or page_id != plan["parent_id"]:
        raise nw.NotionWriteError("approbation ou empreinte invalide")
    created = datetime.fromisoformat(plan["created_at"])
    if created.utcoffset() is None or not timedelta(0) <= (
        datetime.now(UTC) - created
    ) <= timedelta(hours=24):
        raise nw.NotionWriteError("plan expiré")
    spec = plan["spec"]
    records, contents = _assets(Path(plan["media_root"]), _spec(spec, page_id))
    if records != plan["assets"]:
        raise nw.NotionWriteError("média modifié après approbation")
    marker = plan_file.with_name(plan_file.name + ".attempted.json")
    if marker.exists() or marker.is_symlink() or _parent(page_id) != plan["parent_sha256"]:
        raise nw.NotionWriteError("plan déjà tenté ou parent modifié")
    nw._private_new(marker, {"state": "ATTEMPTED", "manifest_sha256": digest})
    uploads: dict[str, str] = {}
    for record in records:
        uploads[record["name"]] = _upload(record, contents[record["name"]])
    home = _created_page(spec["home"], page_id, uploads)
    # Persist the new root before subsequent calls so partial results can be located.
    nw._private_new(plan_file.with_name(plan_file.name + ".root.json"),
                    {"root_page_id": home, "manifest_sha256": digest})
    pages = [_created_page(page, home, uploads) for page in spec["pages"]]
    page_map = {spec["home"]["title"]: home}
    page_map.update({page["title"]: ident for page, ident in zip(
        spec["pages"], pages, strict=True,
    )})
    navigation = (nn.create(_request, home, page_map, spec["navigation"])
                  if "navigation" in spec else None)
    tracker = _tracker(home, spec["tracker"]) if spec["tracker"] is not None else None
    if "curriculum" in spec:
        tracker = nc.create(_request, home, spec["curriculum"], page_map, uploads)
    for ident in uploads.values():
        actual = _request("GET", f"/v1/file_uploads/{ident}")
        if (
            nw._id(str(actual.get("id", ""))) != ident or actual.get("status") != "uploaded"
            or "expiry_time" not in actual or actual["expiry_time"] is not None
        ):
            raise nw.NotionWriteError("attachement durable non confirmé")
    receipt = {"mode": "STUDIO_API_READBACK", "manifest_sha256": digest,
               "root_page_id": home, "page_ids": pages, "tracker": tracker,
               "assets": [{**record, "upload_id": uploads[record["name"]]} for record in records],
               "limitations": "Rendu, octets distants et droits de partage non certifiés"}
    if navigation is not None:
        receipt["navigation"] = navigation
    nw._private_new(plan_file.with_name(plan_file.name + ".verified.json"), receipt)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m clawfedora.notion_studio")
    sub = parser.add_subparsers(dest="action", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--parent", required=True)
    plan.add_argument("--spec", type=Path, required=True)
    plan.add_argument("--media", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)
    execute = sub.add_parser("apply")
    execute.add_argument("--plan", type=Path, required=True)
    execute.add_argument("--approve-parent", required=True)
    execute.add_argument("--approve-manifest", required=True)
    execute.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.action == "plan":
            result = preview(args.parent, args.spec, args.media, args.output)
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
