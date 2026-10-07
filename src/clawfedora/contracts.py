from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ContractReport:
    failures: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.failures


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"contrat illisible: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"contrat invalide: {path}: racine YAML non mapping")
    return payload


def validate_repository(root: Path) -> ContractReport:
    failures: list[str] = []
    warnings: list[str] = []
    version_path = root / "VERSION"
    if not version_path.is_file():
        return ContractReport(("VERSION absent",), ())
    version = version_path.read_text(encoding="utf-8").strip()

    required = {
        "platform": root / "config" / "platform.yaml",
        "hardware": root / "config" / "hardware.yaml",
        "models": root / "config" / "model_catalog.yaml",
    }
    missing = [str(path.relative_to(root)) for path in required.values() if not path.is_file()]
    if missing:
        return ContractReport(tuple(f"fichier requis absent: {item}" for item in missing), ())

    contracts = {name: _load_yaml(path) for name, path in required.items()}
    for name, payload in contracts.items():
        if str(payload.get("platform_version", "")) != version:
            failures.append(f"{name}: platform_version != VERSION ({version})")

    platform = contracts["platform"]
    os_cfg = platform.get("os", {})
    runtime = platform.get("runtime", {})
    security = platform.get("security", {})
    if platform.get("deployment_mode") != "fedora-native":
        failures.append("platform: deployment_mode doit être fedora-native")
    if os_cfg.get("distribution") != "Fedora Linux" or int(os_cfg.get("release", 0)) != 44:
        failures.append("platform: Fedora Linux 44 requis")
    if os_cfg.get("desktop") != "GNOME" or int(os_cfg.get("desktop_major", 0)) != 50:
        failures.append("platform: GNOME 50 requis")
    if os_cfg.get("display_server") != "wayland":
        failures.append("platform: Wayland requis")
    if runtime.get("service_manager") != "systemd-user":
        failures.append("platform: systemd-user requis pour le cycle de vie OpenClaw")
    if security.get("selinux_required") != "enforcing":
        failures.append("platform: SELinux enforcing doit rester requis")
    if security.get("local_model_loopback_only") is not True:
        failures.append("platform: providers locaux doivent rester loopback-only")
    if security.get("cloud_enabled_by_default") is not False:
        failures.append("platform: cloud doit être désactivé par défaut")

    hardware = contracts["hardware"].get("host", {})
    cpu = hardware.get("cpu", {})
    memory = hardware.get("memory", {})
    gpu = hardware.get("gpu", {})
    if cpu.get("model") != "Ryzen 7 7700" or int(cpu.get("cores", 0)) != 8:
        failures.append("hardware: cible CPU Ryzen 7 7700 8C requise")
    if int(memory.get("minimum_supported_gib", 0)) < 48:
        failures.append("hardware: minimum RAM ne doit pas descendre sous 48 Gio")
    if gpu.get("model") != "Arc B580" or int(gpu.get("vram_gib", 0)) != 12:
        failures.append("hardware: Intel Arc B580 12 Gio requise")
    if gpu.get("kernel_driver") != "xe":
        failures.append("hardware: driver kernel xe requis")
    if gpu.get("require_resizable_bar") is not True:
        failures.append("hardware: Resizable BAR doit rester requis")

    models = contracts["models"]
    model_map = models.get("models", {})
    required_models = {key for key, value in model_map.items() if value.get("required") is True}
    if required_models != {"qwen-max"}:
        failures.append("models: seul qwen-max est requis pour le profil quotidien")
    runtime_ids = [str(value.get("runtime_id", "")) for value in model_map.values()]
    runtime_ids_invalid = any(not runtime_id for runtime_id in runtime_ids)
    runtime_ids_duplicated = len(runtime_ids) != len(set(runtime_ids))
    if runtime_ids_invalid or runtime_ids_duplicated:
        failures.append("models: runtime_id absents ou dupliqués")
    fleet_policy = models.get("fleet_policy", {})
    if int(fleet_policy.get("exact_required_model_count", 0)) != 1:
        failures.append("models: exactement un modèle quotidien requis")
    if fleet_policy.get("cloud_model_as_local_fallback") is not False:
        failures.append("models: fallback cloud interdit")

    return ContractReport(tuple(failures), tuple(warnings))
