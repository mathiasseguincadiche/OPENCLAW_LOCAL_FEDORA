"""Secure handoff of Open WebUI uploads to the canonical project intake."""

from __future__ import annotations

import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from clawfedora.project_common import project_path, sha256_file, validate_task_id
from clawfedora.project_engine import current_status
from clawfedora.project_intake import append_intake_items
from clawfedora.project_worker import worker_lock

MAX_ATTACHMENTS = 20
_CONTAINER_DATA = Path("/app/backend/data")


def _safe_name(value: object) -> str:
    raw = str(value or "").strip()
    name = Path(raw).name
    if (
        not name
        or name in {".", ".."}
        or name != raw
        or len(name.encode()) > 220
        or not re.fullmatch(r"[^\x00/\\]+", name)
    ):
        raise ValueError("nom de pièce jointe invalide")
    return name


def _resolve_upload(runtime: Path, item: dict[str, Any]) -> tuple[Path, str]:
    host_data = runtime / "state/webui/data"
    uploads = host_data / "uploads"
    path_value = str(item.get("path", "")).strip()
    if not path_value:
        raise ValueError("chemin de pièce jointe absent")
    raw = Path(path_value)
    if raw.is_absolute():
        try:
            relative = raw.relative_to(_CONTAINER_DATA)
        except ValueError as exc:
            raise ValueError("pièce jointe hors du stockage Open WebUI") from exc
    else:
        relative = raw
    if not relative.parts or relative.parts[0] != "uploads" or ".." in relative.parts:
        raise ValueError("pièce jointe hors du dossier uploads")
    candidate = host_data.joinpath(*relative.parts)
    if host_data.is_symlink() or uploads.is_symlink():
        raise ValueError("stockage Open WebUI lié interdit")
    cursor = host_data
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError("pièce jointe liée interdite")
    resolved = candidate.resolve(strict=True)
    root = uploads.resolve(strict=True)
    if os.path.commonpath((str(resolved), str(root))) != str(root) or not resolved.is_file():
        raise ValueError("pièce jointe hors du stockage autorisé")
    expected = item.get("size")
    if isinstance(expected, int) and expected >= 0 and resolved.stat().st_size != expected:
        raise ValueError("taille de pièce jointe différente du manifeste Open WebUI")
    expected_hash = item.get("sha256")
    if expected_hash is not None:
        if not isinstance(expected_hash, str) or not re.fullmatch(
            r"[a-fA-F0-9]{64}", expected_hash
        ):
            raise ValueError("empreinte de pièce jointe invalide")
        if sha256_file(resolved).lower() != expected_hash.lower():
            raise ValueError("empreinte SHA-256 différente de celle d'Open WebUI")
    return resolved, _safe_name(item.get("filename"))


def import_files(
    repo_root: Path,
    runtime: Path,
    project: Path,
    descriptors: object,
) -> list[str]:
    if not isinstance(descriptors, list) or not descriptors:
        return []
    if len(descriptors) > MAX_ATTACHMENTS:
        raise ValueError(f"{MAX_ATTACHMENTS} pièces jointes maximum")
    if current_status(project) != "INTAKE_READY":
        raise ValueError(
            "les pièces jointes deviennent des sources du projet et ne peuvent être ajoutées "
            "qu'avant l'analyse"
        )
    staging = runtime / "state/chat-import" / project.name / uuid.uuid4().hex
    staging.mkdir(parents=True, mode=0o700)
    sources: list[Path] = []
    try:
        seen: set[str] = set()
        for raw in descriptors:
            if not isinstance(raw, dict):
                raise ValueError("descripteur de pièce jointe invalide")
            source, name = _resolve_upload(runtime, raw)
            if name.casefold() in seen:
                raise ValueError(f"nom de pièce jointe dupliqué: {name}")
            seen.add(name.casefold())
            destination = staging / name
            shutil.copy2(source, destination, follow_symlinks=False)
            destination.chmod(0o600)
            sources.append(destination)
        with worker_lock(runtime, allow_gaming=True):
            return append_intake_items(repo_root, runtime, project, sources)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def practice_files(
    runtime: Path,
    project: Path,
    task_id: str,
    descriptors: object,
) -> dict[str, str]:
    """Read human-authored text outputs from Open WebUI without changing project sources."""
    if not isinstance(descriptors, list) or not descriptors:
        raise ValueError("joignez les fichiers demandés par la tâche")
    task_id = validate_task_id(task_id)
    verified = project_path(runtime, project.name)
    if project.is_symlink() or verified != project.resolve(strict=True):
        raise ValueError("projet hors de la racine autorisée")
    tasks = (verified / "context/tasks").resolve(strict=True)
    task_path = (tasks / f"{task_id}.json").resolve(strict=False)
    if task_path.parent != tasks or task_path.is_symlink():
        raise ValueError("chemin de tâche hors de la racine autorisée")
    if not task_path.is_file():
        raise ValueError("tâche inconnue")
    from clawfedora.project_common import read_json

    task = read_json(task_path)["task"]
    expected = task.get("expected_outputs")
    if not isinstance(expected, list) or not expected:
        raise ValueError("sorties attendues invalides")
    by_name: dict[str, str] = {}
    for relative in expected:
        name = Path(str(relative)).name
        if name in by_name:
            raise ValueError("deux sorties attendues portent le même nom; utiliser l'atelier")
        by_name[name] = str(relative)
    files: dict[str, str] = {}
    total = 0
    for raw in descriptors:
        if not isinstance(raw, dict):
            raise ValueError("descripteur de pièce jointe invalide")
        source, name = _resolve_upload(runtime, raw)
        relative = by_name.get(name)
        if relative is None:
            raise ValueError(f"fichier inattendu: {name}")
        data = source.read_bytes()
        total += len(data)
        if total > 60_000:
            raise ValueError("soumission guidée limitée à 60000 octets")
        if b"\x00" in data:
            raise ValueError(f"sortie binaire non prise en charge dans le chat: {name}")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"sortie UTF-8 requise: {name}") from exc
        files[relative] = text
    if set(files) != set(expected):
        missing = sorted(set(map(str, expected)) - set(files))
        raise ValueError("fichiers attendus absents: " + ", ".join(missing))
    return files


def import_inbox(repo_root: Path, runtime: Path, project: Path) -> list[str]:
    """Fallback for browsers/WebUI versions that cannot forward an original upload."""
    inbox = runtime / "state/chat-import/inbox" / project.name
    if inbox.is_symlink():
        raise ValueError("dossier d'import lié interdit")
    inbox.mkdir(parents=True, exist_ok=True, mode=0o700)
    entries = sorted(inbox.iterdir())
    if not entries:
        raise ValueError(f"dossier vide: {inbox}")
    if len(entries) > MAX_ATTACHMENTS:
        raise ValueError(f"{MAX_ATTACHMENTS} fichiers maximum par import")
    if any(path.is_symlink() or not path.is_file() for path in entries):
        raise ValueError("le dossier d'import ne doit contenir que des fichiers ordinaires")
    with worker_lock(runtime, allow_gaming=True):
        copied = append_intake_items(repo_root, runtime, project, entries)
    for path in entries:
        path.unlink()
    return copied
