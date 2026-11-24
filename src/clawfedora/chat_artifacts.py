"""Short-lived signed download links for artifacts from the current personal chat turn."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import stat
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from clawfedora.core_config import AGENT_IDS
from clawfedora.file_artifacts import read_artifact
from clawfedora.project_common import read_json


def signature(secret: str, role: str, identifier: str, extension: str, expires: int) -> str:
    message = f"{role}/{identifier}/{extension}/{expires}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


MAX_FILE_BYTES = 2_000_000
MAX_FILES_PER_TURN = 80
_REFERENCE_KEYS = {"receipt", "format", "name", "sha256", "size"}


def validate_reference(value: Any) -> dict[str, Any]:
    """Only canonical receipt metadata, never arbitrary URLs or paths."""
    if not isinstance(value, dict) or set(value) != _REFERENCE_KEYS:
        raise ValueError("référence de fichier invalide")
    for key, pattern in (
        ("receipt", r"[0-9a-f]{32}"),
        ("format", r"[a-z0-9]{1,16}"),
        ("name", r"[A-Za-z0-9_.-]{1,100}"),
        ("sha256", r"[0-9a-f]{64}"),
    ):
        if not isinstance(value[key], str) or not re.fullmatch(pattern, value[key]):
            raise ValueError("référence de fichier invalide")
    if (
        value["name"] in {".", ".."}
        or type(value["size"]) is not int or not 0 <= value["size"] <= MAX_FILE_BYTES
    ):
        raise ValueError("référence de fichier invalide")
    return dict(value)


def references(runtime: Path, role: str, before: set[Path]) -> list[dict[str, Any]]:
    """Called under the worker lock; collect only receipts created by this turn."""
    from clawfedora.project_worker import _tool_receipts

    if role not in AGENT_IDS:
        raise ValueError("rôle inconnu")
    workspace = runtime / "workspaces" / role
    new = _tool_receipts(workspace) - before
    if len(new) > 20:
        raise ValueError("vingt outils maximum par tour de chat")
    result = []
    for proof in sorted(new):
        if proof.stat().st_size > 20000:
            raise ValueError("reçu de fichier trop volumineux")
        record = read_json(proof)
        if record.get("tool") not in {"clawfedora_artifact", "clawfedora_diagram"}:
            continue
        for extension in record.get("artifacts", {}):
            target, verified = read_artifact(workspace, role, proof.stem, extension)
            metadata = verified["artifacts"][extension]
            result.append(validate_reference({
                "receipt": proof.stem,
                "format": extension,
                "name": metadata["download_name"],
                "sha256": metadata["sha256"],
                "size": target.stat().st_size,
            }))
            if len(result) > MAX_FILES_PER_TURN:
                raise ValueError("trop de fichiers par tour")
    return result


def links(runtime: Path, role: str, before: set[Path], port: int, secret: str) -> str:
    lines = []
    expires = int(time.time()) + 86400
    for item in references(runtime, role, before):
        identifier, extension = item["receipt"], item["format"]
        query = urlencode({
            "expires": expires,
            "signature": signature(secret, role, identifier, extension, expires),
        })
        url = f"http://127.0.0.1:{port}/artifacts/{role}/{identifier}/{extension}?{query}"
        lines.append(f'[Télécharger {item["name"]}]({url})')
    return (
        "\n\nFichiers produits localement (liens valables 24 h) :\n\n" + "\n\n".join(lines)
        if lines else ""
    )


def native_bytes(
    runtime: Path, role: str, reference: dict[str, Any],
) -> tuple[bytes, str]:
    """Revalidate receipt AND the exact bytes returned, against the committed turn."""
    reference = validate_reference(reference)
    if role not in AGENT_IDS:
        raise ValueError("rôle inconnu")
    path, proof = read_artifact(
        runtime / "workspaces" / role, role, reference["receipt"], reference["format"],
    )
    record = proof["artifacts"][reference["format"]]
    if record["sha256"] != reference["sha256"] or record["download_name"] != reference["name"]:
        raise ValueError("reçu modifié depuis la conversation")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as reader:
        info = os.fstat(reader.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size != reference["size"]:
            raise ValueError("fichier modifié depuis la conversation")
        raw = reader.read(MAX_FILE_BYTES + 1)
    if len(raw) != reference["size"] or hashlib.sha256(raw).hexdigest() != reference["sha256"]:
        raise ValueError("intégrité du fichier non vérifiée")
    return raw, reference["name"]


def download(runtime: Path, secret: str, path: str, expires: str, supplied: str) -> tuple[Path, str]:
    parts = path.split("/")
    if len(parts) != 5 or parts[:2] != ["", "artifacts"]:
        raise ValueError("lien d’artefact invalide")
    _, _, role, identifier, extension = parts
    expiry = int(expires)
    if not int(time.time()) <= expiry <= int(time.time()) + 86400:
        raise ValueError("lien expiré")
    if not hmac.compare_digest(supplied, signature(secret, role, identifier, extension, expiry)):
        raise ValueError("signature invalide")
    # Select a contract-owned workspace; the URL never contributes a filesystem path.
    workspaces = {name: runtime / "workspaces" / name for name in AGENT_IDS}
    if role not in workspaces:
        raise ValueError("rôle inconnu")
    target, proof = read_artifact(workspaces[role], role, identifier, extension)
    name = proof["artifacts"][extension]["download_name"]
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", name):
        raise ValueError("nom de fichier invalide")
    return target, name
