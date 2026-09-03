from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$")
TASK_ID_RE = PROJECT_ID_RE
ALLOWED_OUTPUT_ROOTS = {"work", "deliverables", "evidence", "diagrams"}


def now() -> str:
    return datetime.now(UTC).isoformat()


def validate_project_id(value: str) -> str:
    normalized = value.strip().lower()
    if not PROJECT_ID_RE.fullmatch(normalized):
        raise ValueError(
            "project_id invalide: 3-64 caractères [a-z0-9-], "
            "sans tiret aux extrémités"
        )
    return normalized


def validate_task_id(value: str) -> str:
    normalized = value.strip().lower()
    if not TASK_ID_RE.fullmatch(normalized):
        raise ValueError(f"task id invalide: {value}")
    return normalized


def project_path(platform_root: Path, project_id: str, *, require: bool = True) -> Path:
    normalized = validate_project_id(project_id)
    projects_root = (platform_root / "projects").resolve()
    project = (projects_root / normalized).resolve()
    if project.parent != projects_root:
        raise ValueError("projet hors racine autorisée")
    if require and not (project / "project.json").is_file():
        raise FileNotFoundError(project / "project.json")
    return project


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON invalide: {path}")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def mime_type(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def assert_no_symlinks(root: Path, *, label: str) -> None:
    if root.is_symlink():
        raise ValueError(f"{label}: lien symbolique racine interdit")
    if root.is_dir():
        for path in root.rglob("*"):
            if path.is_symlink():
                raise ValueError(f"{label}: lien symbolique interdit: {path}")


def safe_output(project: Path, relative: str) -> Path:
    value = Path(relative)
    if value.is_absolute() or not value.parts or ".." in value.parts:
        raise ValueError(f"sortie invalide: {relative}")
    if value.parts[0] not in ALLOWED_OUTPUT_ROOTS:
        raise ValueError(f"racine de sortie non autorisée: {relative}")
    target = (project / value).resolve()
    root = project.resolve()
    if root not in target.parents or not target.is_file():
        raise ValueError(f"sortie absente ou hors projet: {relative}")
    current = project / value.parts[0]
    for part in value.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"sortie liée interdite: {relative}")
    return target


def aggregate_records(records: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for record in sorted(records, key=lambda item: str(item["path"])):
        digest.update(
            f"{record['path']}\0{record['sha256']}\0{record['size']}\n".encode()
        )
    return digest.hexdigest()


def chmod_read_only_files(root: Path) -> None:
    if os.name == "nt" or not root.exists():
        return
    for path in root.rglob("*"):
        if path.is_file() and not path.is_symlink():
            path.chmod(0o444)
