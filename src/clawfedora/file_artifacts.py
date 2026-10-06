"""Managed file production: fixed formats, generated filenames, provenance and bounded exports."""

from __future__ import annotations

import ast
import hashlib
import importlib.metadata
import json
import re
import tomllib
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml
from defusedxml.ElementTree import fromstring

from clawfedora.core_config import AGENT_IDS
from clawfedora.document_exports import export
from clawfedora.project_common import assert_no_symlinks, now, read_json, sha256_file, write_json

DOCUMENT_FORMATS = {"markdown": "md", "text": "txt"}
TECHNICAL_FORMATS = {
    "yaml": "yaml",
    "json": "json",
    "python": "py",
    "shell": "sh",
    "hcl": "tf",
    "ini": "ini",
    "toml": "toml",
    "xml": "xml",
    "dockerfile": "dockerfile",
    "template": "j2",
}
TECHNICAL_ROLES = {"architecte-solutions", "ingenieur-devops", "ingenieur-securite"}


def formats(role: str) -> dict[str, str]:
    return DOCUMENT_FORMATS | (TECHNICAL_FORMATS if role in TECHNICAL_ROLES else {})


def produce(workspace: Path, role: str, data: dict[str, Any]) -> dict[str, Any]:
    kind, content, exports = data.get("format"), data.get("content"), data.get("exports", [])
    if kind not in formats(role):
        raise ValueError("format de fichier interdit pour ce rôle")
    if not isinstance(content, str) or not 0 < len(content.encode()) <= 12000 or "\x00" in content:
        raise ValueError("contenu UTF-8 non vide, sans NUL, limité à 12000 octets")
    if (
        not isinstance(exports, list)
        or len(exports) > 3
        or any(x not in {"pdf", "docx", "txt"} for x in exports)
        or len(set(exports)) != len(exports)
        or exports
        and kind != "markdown"
    ):
        raise ValueError("exports pdf/docx/txt uniquement depuis une source Markdown")
    # Jinja/HCL/INI/Dockerfile are preserved, not interpreted as executable configuration.
    try:
        if kind == "json":
            json.loads(content)
        elif kind == "yaml":
            list(yaml.safe_load_all(content))
        elif kind == "python":
            ast.parse(content)
        elif kind == "toml":
            tomllib.loads(content)
        elif kind == "xml":
            fromstring(content, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except Exception as exc:
        raise ValueError(f"syntaxe {kind} invalide") from exc
    extension = formats(role)[kind]
    filename = data.get("filename", "Dockerfile" if kind == "dockerfile" else "document." + extension)
    if (
        not isinstance(filename, str)
        or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", filename)
        or ".." in filename
        or filename in {".", ".."}
    ):
        raise ValueError("nom de fichier simple, sans chemin, requis")
    aliases = {
        "yaml": {".yaml", ".yml"},
        "tf": {".tf", ".tfvars", ".hcl"},
        "ini": {".ini", ".conf", ".cfg", ".service", ".timer"},
        "j2": {".j2", ".tmpl"},
    }
    if Path(filename).suffix.lower() not in aliases.get(extension, {"." + extension}) and not (
        kind == "dockerfile" and filename == "Dockerfile"
    ):
        raise ValueError("nom de fichier incompatible avec le format")
    generated = {extension: content.encode()}
    try:
        for output in exports:
            generated[output] = export(content, output)
    except Exception as exc:
        raise ValueError("export indisponible ou document hors limites; réduire le document") from exc
    if any(len(value) > 2_000_000 for value in generated.values()):
        raise ValueError("fichier généré limité à 2 Mo")
    directory = workspace / ".clawfedora-tool-evidence"
    assert_no_symlinks(directory, label="artefacts")
    directory.mkdir(exist_ok=True)
    directory.chmod(0o750)
    identifier = uuid4().hex
    records = {}
    for ext, value in generated.items():
        target = directory / f"{identifier}.artifact.{ext}.data"
        target.write_bytes(value)
        target.chmod(0o440)
        records[ext] = {
            "name": target.name,
            "sha256": hashlib.sha256(value).hexdigest(),
            "size": len(value),
            "download_name": filename
            if ext == extension
            else str(Path(filename).with_suffix("." + ext)),
        }
    proof = directory / f"{identifier}.json"
    write_json(
        proof,
        {
            "origin": "managed-tool-runner",
            "tool": "clawfedora_artifact",
            "role": role,
            "at": now(),
            "format": kind,
            "artifacts": records,
            "runtime_tested": False,
            "renderer_versions": {
                name: importlib.metadata.version(name)
                for name in ("reportlab", "python-docx", "markdown-it-py")
            },
            "source_sha256": hashlib.sha256(content.encode()).hexdigest(),
        },
    )
    proof.chmod(0o440)
    return {
        "references": {ext: f"@tool-file:{identifier}:{ext}" for ext in generated},
        "receipt": proof.relative_to(workspace).as_posix(),
        "source_format": extension,
        "instruction": "Retourner les références comme contenus JSON des chemins attendus. "
        "Pour PDF/DOCX/TXT dérivés, prévoir aussi la source .md dans le même dossier. "
        "Dans le chat, la passerelle ajoute les liens de téléchargement.",
        "scope": "fichiers produits, code non exécuté, déploiement non testé",
    }


def read_artifact(
    workspace: Path, role: str, identifier: str, extension: str
) -> tuple[Path, dict[str, Any]]:
    if (
        role not in AGENT_IDS
        or len(identifier) != 32
        or any(c not in "0123456789abcdef" for c in identifier)
    ):
        raise ValueError("identité d’artefact invalide")
    for parent in (workspace.parent.parent, workspace.parent, workspace):
        if parent.is_symlink():
            raise ValueError("workspace lié interdit")
    directory = workspace / ".clawfedora-tool-evidence"
    assert_no_symlinks(directory, label="artefact")
    # Select existing managed files by name instead of building paths from download input.
    managed = {path.name: path for path in directory.iterdir() if path.is_file()}
    receipt = managed.get(f"{identifier}.json")
    if receipt is None:
        raise ValueError("reçu d’artefact absent")
    proof = read_json(receipt)
    records = proof.get("artifacts", {})
    if (
        proof.get("origin") != "managed-tool-runner"
        or proof.get("tool") != "clawfedora_artifact"
        or proof.get("role") != role
        or extension not in records
    ):
        raise ValueError("artefact non produit par ce rôle")
    record = records[extension]
    expected = f"{identifier}.artifact.{extension}.data"
    if record.get("name") != expected or extension not in {*formats(role).values(), "pdf", "docx"}:
        raise ValueError("format ou chemin d’artefact invalide")
    path = managed.get(expected)
    if path is None or path.stat().st_size > 2_000_000 or sha256_file(path) != record["sha256"]:
        raise ValueError("artefact modifié ou absent")
    return path, proof
