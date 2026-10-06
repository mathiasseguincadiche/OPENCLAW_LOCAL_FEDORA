"""Short-lived signed download links for artifacts from the current personal chat turn."""

from __future__ import annotations

import hashlib
import hmac
import time
from pathlib import Path
from urllib.parse import urlencode

from clawfedora.file_artifacts import read_artifact
from clawfedora.project_common import read_json


def signature(secret: str, role: str, identifier: str, extension: str, expires: int) -> str:
    message = f"{role}/{identifier}/{extension}/{expires}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def links(runtime: Path, role: str, before: set[Path], port: int, secret: str) -> str:
    directory = runtime / "workspaces" / role / ".clawfedora-tool-evidence"
    new = set(directory.glob("*.json")) - before
    if len(new) > 20:
        raise ValueError("vingt outils maximum par tour de chat")
    lines = []
    expires = int(time.time()) + 86400
    for proof in sorted(new):
        record = read_json(proof)
        if record.get("tool") != "clawfedora_artifact":
            continue
        for extension in record["artifacts"]:
            read_artifact(directory.parent, role, proof.stem, extension)
            query = urlencode(
                {
                    "expires": expires,
                    "signature": signature(secret, role, proof.stem, extension, expires),
                }
            )
            url = f"http://127.0.0.1:{port}/artifacts/{role}/{proof.stem}/{extension}?{query}"
            label = record["artifacts"][extension]["download_name"]
            lines.append(f"[Télécharger {label}]({url})")
    return (
        "\n\nFichiers produits localement (liens valables 24 h) :\n\n" + "\n\n".join(lines)
        if lines
        else ""
    )


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
    target, proof = read_artifact(runtime / "workspaces" / role, role, identifier, extension)
    name = proof["artifacts"][extension]["download_name"]
    import re

    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", name):
        raise ValueError("nom de fichier invalide")
    return target, name
