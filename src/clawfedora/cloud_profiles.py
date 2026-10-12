"""User-selected reasoning effort for the single DeepSeek cloud route.

This is *not* a model router: the browser or an OpenClaw agent cannot modify the
profile. The separate operator CLI writes a local 0600 file after explicit --apply.
The gateway reads it before budget reservation and every upstream request.
"""

from __future__ import annotations

import json
import os
import stat
import uuid
from pathlib import Path
from typing import Any

from clawfedora.cloud_state import CLOUD_STATE

PROFILE_FILE = "reasoning-profile.json"
MAX_FILE_BYTES = 512
VALID_EFFORTS = {"low", "medium", "high", "xhigh"}


class ProfileRefused(ValueError):
    """Invalid state or policy: never silently fall back to an unapproved effort."""


def profiles(policy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Validate every profile against the configured model ceiling, fail closed."""
    settings = policy.get("reasoning_profiles")
    if not isinstance(settings, dict) or not settings:
        raise ProfileRefused("profils de raisonnement absents de la politique cloud")
    ceiling = policy.get("model", {}).get("max_output_tokens")
    if type(ceiling) is not int or ceiling < 1:
        raise ProfileRefused("plafond de sortie du modèle cloud invalide")
    for name, value in settings.items():
        if (
            not isinstance(name, str)
            or not isinstance(value, dict)
            or value.get("effort") not in VALID_EFFORTS
            or type(value.get("max_output_tokens")) is not int
            or not 1 <= value["max_output_tokens"] <= ceiling
        ):
            raise ProfileRefused("profil de raisonnement non conforme à la politique")
    default = policy.get("default_reasoning_profile")
    if default not in settings:
        raise ProfileRefused("profil cloud par défaut non déclaré")
    # Backward-compatible: the default remains the formerly enforced xhigh.
    if settings[default]["effort"] != policy["upstream_params"]["reasoning"]["effort"]:
        raise ProfileRefused("profil par défaut divergent des paramètres historiques")
    return settings


def profile_path(runtime: Path) -> Path:
    return runtime / CLOUD_STATE / PROFILE_FILE


def chosen_profile(runtime: Path, policy: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Missing file = explicitly contracted default. Unsafe file = refuse cloud."""
    declared = profiles(policy)
    path = profile_path(runtime)
    try:
        status = path.lstat()
    except FileNotFoundError:
        name = str(policy["default_reasoning_profile"])
        return name, declared[name]
    if not stat.S_ISREG(status.st_mode) or stat.S_IMODE(status.st_mode) != 0o600:
        raise ProfileRefused("profil cloud : fichier ordinaire privé 0600 requis")
    if status.st_size > MAX_FILE_BYTES or status.st_size < 2:
        raise ProfileRefused("profil cloud : taille du fichier invalide")
    try:
        # Check again at open: never follow a replaced symlink.
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "r", encoding="utf-8") as handle:
            record: Any = json.loads(handle.read(MAX_FILE_BYTES + 1))
    except (OSError, ValueError, UnicodeError) as exc:
        raise ProfileRefused("profil cloud : fichier illisible") from exc
    if (
        not isinstance(record, dict)
        or set(record) != {"version", "profile"}
        or record["version"] != 1
        or type(record["profile"]) is not str
        or record["profile"] not in declared
    ):
        raise ProfileRefused("profil cloud : valeur inconnue ou fichier modifié")
    name = str(record["profile"])
    return name, declared[name]


def set_profile(runtime: Path, policy: dict[str, Any], name: str) -> Path:
    """Atomic operator-side write. Call only under worker_lock after --apply."""
    declared = profiles(policy)
    if name not in declared:
        raise ProfileRefused("profil cloud inconnu")
    directory = runtime / CLOUD_STATE
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if directory.is_symlink() or not directory.is_dir():
        raise ProfileRefused("dossier cloud non fiable")
    directory.chmod(0o700)
    target = profile_path(runtime)
    if target.is_symlink():
        raise ProfileRefused("lien symbolique refusé pour le profil")
    old = target if target.exists() else None
    if old is not None:
        chosen_profile(runtime, policy)  # validates state before overwrite
    temporary = directory / ("." + PROFILE_FILE + "-" + uuid.uuid4().hex[:16])
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"version": 1, "profile": name}, handle)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target
