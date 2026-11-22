"""Open WebUI global filter owned by OPENCLAW_LOCAL_FEDORA.

Only authenticated, user-owned uploads are forwarded as metadata. The
built-in file RAG stays disabled. A saved chat in a native, *managed*
ClawFedora project folder receives a short-lived signed binding so the
local bridge can choose the correct read-only project context. Folder
names, user prompts and arbitrary client fields are never trusted.
"""

import hashlib
import hmac
import json
import os
import re
import time
from typing import Any

from open_webui.models.files import Files

_PROJECT_ID = re.compile(r"[a-z0-9][a-z0-9-]{1,62}[a-z0-9]\Z")
_CHAT_ID = re.compile(r"[a-zA-Z0-9-]{8,128}\Z")
_TOKEN = re.compile(r"[a-f0-9]{64}\Z")
_FOLDER_FIELD = "clawfedora_folder_binding"


def _last_message_sha256(body: dict[str, Any]) -> str | None:
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        return None
    last = messages[-1]
    if not isinstance(last, dict) or last.get("role") != "user":
        return None
    content = last.get("content")
    if not isinstance(content, (str, list)):
        return None
    encoded = json.dumps(
        content, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _chat_id(body: dict[str, Any], extra: dict[str, Any] | None) -> str | None:
    metadata = body.get("metadata")
    sources = [body, metadata if isinstance(metadata, dict) else {}, extra or {}]
    identifiers = [
        item["chat_id"] for item in sources
        if isinstance(item.get("chat_id"), str) and item["chat_id"]
    ]
    if not identifiers:
        return None
    if len(set(identifiers)) != 1:
        raise ValueError("identifiants de conversation WebUI contradictoires")
    value = identifiers[0]
    # Unsaved/temporary chats still work with explicit !projet; no auto-binding.
    return value if _CHAT_ID.fullmatch(value) else None


async def _managed_project(
    user_id: str, chat_id: str,
) -> str | None:
    """Use the pinned Open WebUI 0.12.3 owner-scoped native ORM."""
    from open_webui.models.chats import Chats
    from open_webui.models.folders import Folders

    chat = await Chats.get_chat_by_id_and_user_id(chat_id, user_id)
    if chat is None or not chat.folder_id:
        return None
    folder = await Folders.get_folder_by_id_and_user_id(chat.folder_id, user_id)
    if folder is None:
        return None
    meta = getattr(folder, "meta", None)
    if not isinstance(meta, dict) or meta.get("clawfedora_folder_kind") != "project":
        return None
    project = meta.get("clawfedora_project_id")
    if (
        meta.get("clawfedora_schema") != 1
        or not isinstance(project, str) or not _PROJECT_ID.fullmatch(project)
        or not isinstance(folder.parent_id, str)
    ):
        raise ValueError("métadonnées du dossier ClawFedora invalides")
    root = await Folders.get_folder_by_id_and_user_id(folder.parent_id, user_id)
    root_meta = getattr(root, "meta", None)
    if (
        root is None or root.parent_id is not None
        or not isinstance(root_meta, dict)
        or root_meta.get("clawfedora_schema") != 1
        or root_meta.get("clawfedora_folder_kind") != "root"
        or root_meta.get("clawfedora_project_id") is not None
    ):
        raise ValueError("racine du dossier ClawFedora non autorisée")
    return project


async def _signed_folder_binding(
    body: dict[str, Any], user: dict[str, Any] | None,
    extra_metadata: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if (user or {}).get("role") != "admin":
        return None
    user_id = (user or {}).get("id")
    if not isinstance(user_id, str) or not user_id or len(user_id) > 128:
        return None
    chat_id = _chat_id(body, extra_metadata)
    message_digest = _last_message_sha256(body)
    if chat_id is None or message_digest is None:
        return None
    project = await _managed_project(user_id, chat_id)
    if project is None:
        return None
    key = os.environ.get("OPENAI_API_KEY", "")
    if not _TOKEN.fullmatch(key):
        raise ValueError("clé du pont local absente : contexte de dossier refusé")
    claim: dict[str, Any] = {
        "project_id": project,
        "chat_id": chat_id,
        "user_id": user_id,
        "issued_at": int(time.time()),
        "message_sha256": message_digest,
    }
    payload = json.dumps(
        claim, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")
    claim["signature"] = hmac.new(key.encode(), payload, hashlib.sha256).hexdigest()
    return claim


class Filter:
    file_handler = True

    def __init__(self) -> None:
        self.file_handler = True

    async def inlet(
        self,
        body: dict[str, Any],
        __user__: dict[str, Any] | None = None,
        __metadata__: dict[str, Any] | None = None,
        **_: object,
    ) -> dict[str, Any]:
        # Drop a client-supplied field before deriving a new claim from native
        # owner-scoped records. Unmanaged/unsaved chats retain manual selection.
        body.pop(_FOLDER_FIELD, None)
        binding = await _signed_folder_binding(body, __user__, __metadata__)
        if binding is not None:
            body[_FOLDER_FIELD] = binding

        raw_metadata = body.get("metadata")
        metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
        raw_message = metadata.get("user_message")
        message: dict[str, Any] = raw_message if isinstance(raw_message, dict) else {}
        # Prefer the latest user message, never re-import a whole thread's older attachments.
        refs = (
            message.get("files") or []
            if "files" in message
            else body.get("files") or metadata.get("files") or []
        )
        if not isinstance(refs, list) or not refs:
            return body
        user_id = str((__user__ or {}).get("id", ""))
        if not user_id:
            raise ValueError("utilisateur Open WebUI absent pour les pièces jointes")
        if len(refs) > 20:
            raise ValueError("20 pièces jointes maximum par message")
        exported = []
        seen = set()
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            file_id = str(ref.get("id", ""))
            if not file_id or file_id in seen:
                continue
            seen.add(file_id)
            item = await Files.get_file_by_id_and_user_id(file_id, user_id)
            if item is None or not item.path:
                raise ValueError("pièce jointe introuvable ou non autorisée")
            meta = item.meta if isinstance(item.meta, dict) else {}
            exported.append(
                {
                    "id": item.id,
                    "filename": item.filename,
                    "path": item.path,
                    "sha256": meta.get("file_hash") or item.hash,
                    "content_type": meta.get("content_type"),
                    "size": meta.get("size"),
                    "kind": ref.get("type", "file"),
                }
            )
        if exported:
            body["clawfedora_files"] = exported
        return body
