"""Operator choices for the cloud route: reasoning effort and upstream model.

Neither is a router a client can drive: the browser or an OpenClaw agent cannot change
them. The separate operator CLI writes a local 0600 file after explicit --apply. The
gateway reads both before the budget reservation and every upstream request. OpenClaw
always talks to the same ``cloud-main`` alias; the gateway decides which reviewed model
answers behind it, with that model's own price ceilings.
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
MODEL_FILE = "upstream-model.json"
MAX_FILE_BYTES = 512
VALID_EFFORTS = {"low", "medium", "high", "xhigh"}
# Optional request fields a model's providers may not declare (require_parameters would
# then exclude every provider): a reviewed model may drop them, never anything else.
DROPPABLE_PARAMETERS = {"parallel_tool_calls", "seed", "stop"}
QUANTIZATIONS = {"int4", "int8", "fp4", "fp6", "fp8", "fp16", "bf16", "fp32", "unknown"}


class ProfileRefused(ValueError):
    """Invalid state or policy: never silently fall back to an unapproved choice."""


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


def _price(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and value > 0


def _optional_list(value: dict[str, Any], key: str, allowed: set[str]) -> bool:
    items = value.get(key)
    return items is None or (
        isinstance(items, list) and bool(items) and all(item in allowed for item in items)
    )


def _provider_overrides(value: Any) -> bool:
    """Only a narrower quantization filter may be added to the policy's provider settings."""
    if value is None:
        return True
    return (
        isinstance(value, dict)
        and set(value) <= {"quantizations"}
        and _optional_list(value, "quantizations", QUANTIZATIONS)
    )


def require_compatible(model_name: str, model: dict[str, Any], profile_name: str,
                       profile: dict[str, Any]) -> None:
    """A model that does not accept the profile's effort is refused, never silently changed."""
    allowed = model.get("allowed_efforts")
    if allowed is not None and profile["effort"] not in allowed:
        raise ProfileRefused(
            f"le modèle cloud « {model_name} » n'accepte pas l'effort {profile['effort']} du "
            f"profil « {profile_name} » : choisir un profil d'effort {' ou '.join(allowed)}"
        )


def upstream_models(policy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Reviewed upstream models; the default one must be the contracted ``model``."""
    models = policy.get("upstream_models")
    if not isinstance(models, dict) or not models:
        raise ProfileRefused("modèles cloud absents de la politique")
    seen: set[str] = set()
    for name, value in models.items():
        pricing = value.get("pricing_usd_per_million") if isinstance(value, dict) else None
        if (
            not isinstance(name, str)
            or not isinstance(value, dict)
            or not isinstance(value.get("upstream_id"), str)
            or "/" not in value["upstream_id"]
            or value["upstream_id"] in seen
            or not isinstance(value.get("display_name"), str)
            or type(value.get("enabled")) is not bool
            or not isinstance(pricing, dict)
            or not (_price(pricing.get("input")) and _price(pricing.get("output")))
            or not _optional_list(value, "allowed_efforts", VALID_EFFORTS)
            or not _optional_list(value, "drop_parameters", DROPPABLE_PARAMETERS)
            or not _provider_overrides(value.get("provider"))
        ):
            raise ProfileRefused("modèle cloud non conforme à la politique")
        seen.add(value["upstream_id"])
    default = policy.get("default_upstream_model")
    contracted = policy.get("model", {})
    chosen = models.get(default) if isinstance(default, str) else None
    if (
        chosen is None
        or chosen["enabled"] is not True
        or chosen["upstream_id"] != contracted.get("upstream_id")
        or chosen["pricing_usd_per_million"] != contracted.get("pricing_usd_per_million")
    ):
        raise ProfileRefused("modèle cloud par défaut divergent du modèle contractuel")
    return models


def profile_path(runtime: Path) -> Path:
    return runtime / CLOUD_STATE / PROFILE_FILE


def model_path(runtime: Path) -> Path:
    return runtime / CLOUD_STATE / MODEL_FILE


def _read_choice(path: Path, field: str, label: str) -> str | None:
    """The stored choice, ``None`` when no file exists. Any unsafe state is refused."""
    if path.parent.is_symlink():
        raise ProfileRefused(f"{label} : répertoire lié refusé")
    try:
        status = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ProfileRefused(f"{label} : inaccessible") from exc
    if not stat.S_ISREG(status.st_mode) or stat.S_IMODE(status.st_mode) != 0o600:
        raise ProfileRefused(f"{label} : fichier ordinaire privé 0600 requis")
    if status.st_size > MAX_FILE_BYTES or status.st_size < 2:
        raise ProfileRefused(f"{label} : taille du fichier invalide")
    try:
        # Check again at open: never follow a replaced symlink.
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "r", encoding="utf-8") as handle:
            opened = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(opened.st_mode)
                or stat.S_IMODE(opened.st_mode) != 0o600
                or opened.st_size > MAX_FILE_BYTES
            ):
                raise ProfileRefused(f"{label} : fichier modifié pendant la lecture")
            record: Any = json.loads(handle.read(MAX_FILE_BYTES + 1))
    except (OSError, ValueError, UnicodeError) as exc:
        raise ProfileRefused(f"{label} : fichier illisible") from exc
    if (
        not isinstance(record, dict)
        or set(record) != {"version", field}
        or record["version"] != 1
        or type(record[field]) is not str
    ):
        raise ProfileRefused(f"{label} : valeur inconnue ou fichier modifié")
    return str(record[field])


def _write_choice(runtime: Path, path: Path, field: str, value: str, label: str) -> Path:
    directory = runtime / CLOUD_STATE
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if directory.is_symlink() or not directory.is_dir():
        raise ProfileRefused("dossier cloud non fiable")
    directory.chmod(0o700)
    if path.is_symlink():
        raise ProfileRefused(f"lien symbolique refusé pour le {label}")
    temporary = directory / ("." + path.name + "-" + uuid.uuid4().hex[:16])
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"version": 1, field: value}, handle)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def chosen_profile(runtime: Path, policy: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Missing file = explicitly contracted default. Unsafe file = refuse cloud."""
    declared = profiles(policy)
    name = _read_choice(profile_path(runtime), "profile", "profil cloud")
    if name is None:
        name = str(policy["default_reasoning_profile"])
    if name not in declared:
        raise ProfileRefused("profil cloud : valeur inconnue ou fichier modifié")
    return name, declared[name]


def set_profile(runtime: Path, policy: dict[str, Any], name: str) -> Path:
    """Atomic operator-side write. Call only under worker_lock after --apply."""
    declared = profiles(policy)
    if name not in declared:
        raise ProfileRefused("profil cloud inconnu")
    if profile_path(runtime).exists():
        chosen_profile(runtime, policy)  # validates state before overwrite
    return _write_choice(runtime, profile_path(runtime), "profile", name, "profil")


def chosen_upstream_model(runtime: Path, policy: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """The model the gateway calls. Missing file = contracted default; a model disabled in
    the policy (even if chosen earlier) or an unsafe file refuses the cloud, never falls back.
    """
    declared = upstream_models(policy)
    name = _read_choice(model_path(runtime), "model", "modèle cloud")
    if name is None:
        name = str(policy["default_upstream_model"])
    if name not in declared:
        raise ProfileRefused("modèle cloud : valeur inconnue ou fichier modifié")
    if declared[name]["enabled"] is not True:
        raise ProfileRefused(
            f"modèle cloud « {name} » désactivé dans la politique : le réactiver après "
            "vérification, ou revenir au modèle standard"
        )
    return name, declared[name]


def set_upstream_model(runtime: Path, policy: dict[str, Any], name: str) -> Path:
    """Atomic operator-side write. Call only under worker_lock after --apply."""
    declared = upstream_models(policy)
    if name not in declared:
        raise ProfileRefused("modèle cloud inconnu")
    if declared[name]["enabled"] is not True:
        raise ProfileRefused(
            f"modèle cloud « {name} » désactivé dans la politique : vérifier son identifiant, "
            "son prix et sa confidentialité sur openrouter.ai, puis passer enabled: true"
        )
    return _write_choice(runtime, model_path(runtime), "model", name, "modèle")
