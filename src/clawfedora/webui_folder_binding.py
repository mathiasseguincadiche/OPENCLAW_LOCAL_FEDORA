"""Verify short-lived native Open WebUI folder claims at the local bridge.

Folder names, chat prompts, model messages and arbitrary unsigned parameters
are not authentication. Only the owner-scoped Open WebUI filter signs a claim.
No claim alone authorizes cloud use, code execution or project mutations.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from pathlib import Path
from typing import Any

from clawfedora.chat_projects import open_project

FIELD = "clawfedora_folder_binding"
PROJECT_ID = re.compile(r"[a-z0-9][a-z0-9-]{1,62}[a-z0-9]\Z")
CHAT_ID = re.compile(r"[a-zA-Z0-9-]{8,128}\Z")
HEX64 = re.compile(r"[a-f0-9]{64}\Z")
CLAIM_KEYS = {
    "project_id", "chat_id", "user_id", "issued_at", "message_sha256", "signature",
}
MAX_AGE_SECONDS = 90


def resolve(data: dict[str, Any], token: str, runtime: Path) -> str | None:
    """Accept only a fresh HMAC claim bound to the current user message."""
    raw = data.get(FIELD)
    if raw is None:
        return None
    if not isinstance(raw, dict) or set(raw) != CLAIM_KEYS:
        raise ValueError("liaison de dossier WebUI non fiable")
    project = raw["project_id"]
    chat_id, user_id = raw["chat_id"], raw["user_id"]
    timestamp, digest, signature = (
        raw["issued_at"], raw["message_sha256"], raw["signature"],
    )
    if (
        not isinstance(project, str) or not PROJECT_ID.fullmatch(project)
        or not isinstance(chat_id, str) or not CHAT_ID.fullmatch(chat_id)
        or not isinstance(user_id, str) or not 0 < len(user_id) <= 128
        or type(timestamp) is not int
        or abs(int(time.time()) - timestamp) > MAX_AGE_SECONDS
        or not isinstance(digest, str) or not HEX64.fullmatch(digest)
        or not isinstance(signature, str) or not HEX64.fullmatch(signature)
    ):
        raise ValueError("liaison de dossier WebUI expirée ou invalide")
    messages = data.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ValueError("liaison de dossier sans message utilisateur")
    last = messages[-1]
    if not isinstance(last, dict) or last.get("role") != "user":
        raise ValueError("liaison de dossier sans dernier message utilisateur")
    content = last.get("content")
    if not isinstance(content, (str, list)):
        raise ValueError("message utilisateur non compatible avec le dossier")
    actual = hashlib.sha256(json.dumps(
        content, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")).hexdigest()
    if not hmac.compare_digest(digest, actual):
        raise ValueError("message différent de la liaison de dossier")
    if not isinstance(token, str) or not HEX64.fullmatch(token):
        raise ValueError("secret de pont local indisponible")
    claim = {key: val for key, val in raw.items() if key != "signature"}
    payload = json.dumps(
        claim, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")
    expected = hmac.new(token.encode(), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise ValueError("signature de dossier WebUI non fiable")
    if open_project(runtime, project) is None:
        raise ValueError("projet du dossier WebUI absent ou non autorisé")
    return project
