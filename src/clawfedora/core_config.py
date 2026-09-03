from __future__ import annotations

import os
from pathlib import Path
from typing import Any, cast

import yaml

AGENT_IDS = (
    "chef-operations",
    "expert-recherche",
    "architecte-solutions",
    "ingenieur-devops",
    "ingenieur-securite",
    "ingenieur-release-forges",
    "redacteur-technique",
    "auditeur-qualite",
)


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        payload: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"YAML illisible: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"YAML invalide: {path}: racine non mapping")
    return cast(dict[str, Any], payload)


def core_contract(repo_root: Path, name: str) -> dict[str, Any]:
    path = repo_root / "config" / "core" / name
    if not path.is_file():
        raise FileNotFoundError(path)
    return load_yaml(path)


def root_contract(repo_root: Path, name: str) -> dict[str, Any]:
    path = repo_root / "config" / name
    if not path.is_file():
        raise FileNotFoundError(path)
    return load_yaml(path)


def resolve_runtime_root(explicit: str | Path | None = None) -> Path:
    if explicit is not None:
        return Path(explicit).expanduser().resolve()
    configured = os.environ.get("OPENCLAW_LOCAL_FEDORA_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    preferred = Path("/srv/openclaw-local")
    if preferred.is_dir():
        return preferred.resolve()
    return (Path.home() / ".local" / "share" / "openclaw-local").resolve()
