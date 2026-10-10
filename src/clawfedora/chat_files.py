"""Secure handoff of Open WebUI uploads to the canonical project intake."""

from __future__ import annotations

import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

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
    if candidate.is_symlink():
        raise ValueError("pièce jointe liée interdite")
    resolved = candidate.resolve(strict=True)
    root = uploads.resolve(strict=True)
    if os.path.commonpath((str(resolved), str(root))) != str(root) or not resolved.is_file():
        raise ValueError("pièce jointe hors du stockage autorisé")
    expected = item.get("size")
    if isinstance(expected, int) and expected >= 0 and resolved.stat().st_size != expected:
        raise ValueError("taille de pièce jointe différente du manifeste Open WebUI")
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
            return append_intake_items(repo_root, project, sources)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
