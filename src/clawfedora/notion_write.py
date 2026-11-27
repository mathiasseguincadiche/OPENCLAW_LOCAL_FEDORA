"""Opt-in, single-block Notion editorial revisions with exact human approval.

This intentionally does not create, delete, reorder or touch child pages, databases,
images, exercises or progress. Plans are private local files; the LLM cannot apply them.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import stat
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

API = "https://api.notion.com"
HEX_ID = re.compile(r"[0-9a-f]{32}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
EDIT_TYPES = frozenset({"paragraph", "heading_2", "heading_3", "bulleted_list_item",
                        "numbered_list_item"})
MAX_TEXT = 1900
MAX_REPLY = 1_000_000


class NotionWriteError(ValueError):
    """A refused or unverified Notion operation (never includes response bodies)."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: urllib.request.Request, fp: Any, code: int,
        msg: str, headers: Any, newurl: str,
    ) -> None:
        raise NotionWriteError("redirection Notion refusée")


def _id(value: str) -> str:
    clean = value.replace("-", "").lower()
    if HEX_ID.fullmatch(clean) is None:
        raise NotionWriteError("ID Notion invalide")
    return clean


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def _text(value: object) -> str:
    if (
        not isinstance(value, str) or not value.strip() or len(value) > MAX_TEXT
        or "\x00" in value or "\r" in value
    ):
        raise NotionWriteError("texte vide, trop long ou invalide (1900 caractères max)")
    return value


def _token(*, write: bool) -> str:
    name = "NOTION_WRITE_TOKEN" if write else "NOTION_API_TOKEN"
    result = os.environ.get(name, "").strip()
    if not result:
        raise NotionWriteError(f"{name} absent du processus local")
    return result


def _request(
    method: str, resource: str, *, write: bool = False,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if re.fullmatch(r"/v1/(?:pages|blocks)/[0-9a-f]{32}", resource) is None:
        raise NotionWriteError("endpoint Notion non autorisé")
    if method not in ("GET", "PATCH") or (method == "PATCH" and (
        not write or not resource.startswith("/v1/blocks/")
    )):
        raise NotionWriteError("méthode Notion refusée")
    token = _token(write=write)
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        API + resource, data=payload, method=method,
        headers={
            "Authorization": "Bearer " + token,
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "clawfedora-notion-edit/0.2",
        },
    )
    try:
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=20) as response:
            raw = response.read(MAX_REPLY + 1)
    except urllib.error.HTTPError as exc:
        raise NotionWriteError(f"Notion a refusé la requête : HTTP {exc.code}") from None
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise NotionWriteError(
            "Notion inaccessible ou résultat ambigu : vérifier la page avant toute relance",
        ) from exc
    if len(raw) > MAX_REPLY:
        raise NotionWriteError("réponse Notion trop volumineuse")
    try:
        value: object = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise NotionWriteError("réponse Notion non JSON") from exc
    if not isinstance(value, dict):
        raise NotionWriteError("réponse Notion invalide")
    return cast(dict[str, Any], value)


def _block(page_id: str, block_id: str) -> tuple[dict[str, Any], str, str]:
    page = _request("GET", f"/v1/pages/{page_id}")
    block = _request("GET", f"/v1/blocks/{block_id}")
    if _id(str(page.get("id", ""))) != page_id or page.get("archived") is True:
        raise NotionWriteError("page Notion absente ou archivée")
    parent = block.get("parent")
    if (
        _id(str(block.get("id", ""))) != block_id
        or not isinstance(parent, dict)
        or parent.get("type") != "page_id"
        or _id(str(parent.get("page_id", ""))) != page_id
        or block.get("archived") is True or block.get("has_children") is True
    ):
        raise NotionWriteError("bloc non direct, archivé, imbriqué ou incompatible")
    kind = block.get("type")
    if kind not in EDIT_TYPES:
        raise NotionWriteError("seuls les textes simples de blocs non imbriqués sont éditables")
    return block, str(kind), _plain_text(block, kind)


def _plain_text(block: dict[str, Any], kind: str) -> str:
    data = block.get(kind)
    if not isinstance(data, dict):
        raise NotionWriteError("contenu du bloc introuvable")
    rich = data.get("rich_text")
    if not isinstance(rich, list) or len(rich) != 1 or not isinstance(rich[0], dict):
        raise NotionWriteError("bloc riche ou multi-segment : préserver son formatage")
    part = rich[0]
    text_obj = part.get("text")
    annotations = part.get("annotations", {})
    if (
        part.get("type") != "text" or not isinstance(text_obj, dict)
        or text_obj.get("link") is not None or part.get("href") is not None
        or (isinstance(annotations, dict) and (
            any(annotations.get(key) for key in (
                "bold", "italic", "strikethrough", "underline", "code",
            )) or annotations.get("color", "default") != "default"
        ))
    ):
        raise NotionWriteError("bloc avec liens ou formatage : modification non autorisée")
    original = text_obj.get("content")
    if not isinstance(original, str) or original != part.get("plain_text"):
        raise NotionWriteError("texte du bloc non vérifiable")
    return original


def _fingerprint(block: dict[str, Any], kind: str) -> str:
    rich = cast(dict[str, Any], block[kind])["rich_text"]
    return _digest({
        "id": block["id"], "type": kind,
        "last_edited_time": block.get("last_edited_time"),
        "rich_text": rich,
    })


def _private_new(path: Path, data: dict[str, Any]) -> None:
    if path.is_symlink() or not path.parent.is_dir():
        raise NotionWriteError("destination de plan non sûre")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise NotionWriteError("fichier de plan ou reçu déjà présent / inaccessible") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def _load(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 12_000:
        raise NotionWriteError("plan absent, lié ou trop volumineux")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise NotionWriteError("plan non privé : chmod 600 requis")
    try:
        obj: object = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError, OSError) as exc:
        raise NotionWriteError("plan JSON invalide") from exc
    if not isinstance(obj, dict):
        raise NotionWriteError("plan mal formé")
    return cast(dict[str, Any], obj)


def preview(page: str, block: str, new_text: str, output: Path) -> dict[str, Any]:
    page_id, block_id = _id(page), _id(block)
    proposed = _text(new_text)
    current, kind, old = _block(page_id, block_id)
    if old == proposed:
        raise NotionWriteError("aucune modification à appliquer")
    data: dict[str, Any] = {
        "schema": 1, "action": "replace_plain_text",
        "page_id": page_id, "block_id": block_id, "block_type": kind,
        "old_sha256": _fingerprint(current, kind), "new_text": proposed,
        "created_at": datetime.now(UTC).isoformat(),
    }
    data["manifest_sha256"] = _digest(data)
    _private_new(output, data)
    diff = "\n".join(difflib.unified_diff(
        old.splitlines(), proposed.splitlines(), fromfile="Notion actuel",
        tofile="Proposition", lineterm="",
    ))
    return {
        "mode": "PREVIEW_ONLY", "page_id": page_id, "block_id": block_id,
        "plan_file": str(output), "manifest_sha256": data["manifest_sha256"],
        "diff": diff, "remote_writes": False,
    }


def apply(plan_file: Path, page: str, manifest: str) -> dict[str, Any]:
    data = _load(plan_file)
    expected_keys = {
        "schema", "action", "page_id", "block_id", "block_type",
        "old_sha256", "new_text", "created_at", "manifest_sha256",
    }
    if set(data) != expected_keys or data.get("schema") != 1 or data.get(
        "action",
    ) != "replace_plain_text":
        raise NotionWriteError("schéma de plan non autorisé")
    digest = data.pop("manifest_sha256")
    if (
        not isinstance(digest, str) or SHA256.fullmatch(digest) is None
        or digest != _digest(data) or digest != manifest
        or _id(page) != data["page_id"]
        or not isinstance(data["old_sha256"], str)
        or SHA256.fullmatch(data["old_sha256"]) is None
        or data["block_type"] not in EDIT_TYPES
    ):
        raise NotionWriteError("approbation ou intégrité du plan invalide")
    _text(data["new_text"])
    page_id = _id(data["page_id"])
    block_id = _id(data["block_id"])
    try:
        created_at = datetime.fromisoformat(data["created_at"])
    except (ValueError, TypeError) as exc:
        raise NotionWriteError("date du plan invalide") from exc
    age = datetime.now(UTC) - created_at
    if created_at.utcoffset() is None or not timedelta(0) <= age <= timedelta(hours=24):
        raise NotionWriteError("plan expiré ou horodatage invalide")
    marker = plan_file.with_name(plan_file.name + ".attempted.json")
    if marker.exists() or marker.is_symlink():
        raise NotionWriteError("plan déjà tenté : inspecter Notion avant de recommencer")
    current, kind, old = _block(page_id, block_id)
    if kind != data["block_type"] or _fingerprint(current, kind) != data["old_sha256"]:
        raise NotionWriteError("page ou bloc modifié depuis l'aperçu : nouveau plan requis")
    if old == data["new_text"]:
        raise NotionWriteError("contenu déjà identique : vérifier la page")
    # Durable single-use marker precedes the network write. Never silently retry an
    # ambiguous PATCH: Notion does not expose compare-and-swap on block revisions.
    _private_new(marker, {
        "state": "ATTEMPTED", "page_id": page_id, "block_id": block_id,
        "manifest_sha256": digest, "marked_at": datetime.now(UTC).isoformat(),
    })
    result = _request(
        "PATCH", f"/v1/blocks/{block_id}", write=True,
        body={kind: {"rich_text": [
            {"type": "text", "text": {"content": data["new_text"]}},
        ]}},
    )
    if _id(str(result.get("id", ""))) != block_id:
        raise NotionWriteError("réponse d'écriture inattendue : inspecter Notion")
    verified, new_kind, content = _block(page_id, block_id)
    if new_kind != kind or content != data["new_text"]:
        raise NotionWriteError("résultat distant non vérifié : contrôler Notion")
    return {
        "mode": "NOTION_BLOCK_UPDATED_VERIFIED", "page_id": page_id,
        "block_id": block_id, "manifest_sha256": digest,
        "last_edited_time": verified.get("last_edited_time"),
        "limitations": "Aucune vérification graphique ou mobile",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clawfedora-notion-write")
    cmds = parser.add_subparsers(dest="action", required=True)
    plan = cmds.add_parser("plan", help="lecture Notion et diff ciblé, sans écriture distante")
    plan.add_argument("--page", required=True)
    plan.add_argument("--block", required=True)
    plan.add_argument("--text-file", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)
    write = cmds.add_parser("apply", help="modifier un seul bloc après approbation exacte")
    write.add_argument("--plan", type=Path, required=True)
    write.add_argument("--approve-page", required=True)
    write.add_argument("--approve-manifest", required=True)
    write.add_argument("--apply", action="store_true", help="confirmation d'écriture explicite")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.action == "plan":
            if args.text_file.is_symlink() or args.text_file.stat().st_size > 8000:
                raise NotionWriteError("fichier texte non sûr ou trop volumineux")
            text = args.text_file.read_text(encoding="utf-8")
            result = preview(args.page, args.block, text, args.output)
        else:
            if not args.apply:
                raise NotionWriteError("--apply explicite requis")
            result = apply(args.plan, args.approve_page, args.approve_manifest)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (NotionWriteError, OSError, UnicodeError, TypeError, KeyError) as exc:
        print(json.dumps({
            "mode": "REFUSED_OR_INCOMPLETE", "reason": str(exc),
            "next_step": "Vérifier la page Notion avant toute nouvelle tentative.",
        }, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
