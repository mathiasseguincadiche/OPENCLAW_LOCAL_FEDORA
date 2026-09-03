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


def _loopback(endpoint: str) -> bool:
    return endpoint.startswith("http://127.0.0.1:") or endpoint.startswith("http://localhost:")


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
        "kernel": root / "config" / "kernel_policy.yaml",
        "models": root / "config" / "model_catalog.yaml",
        "backends": root / "config" / "runtime_backends.yaml",
        "qualification": root / "config" / "qualification_policy.yaml",
        "roadmap": root / "config" / "roadmap_policy.yaml",
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
    if security.get("cloud_escalation_explicit_only") is not True:
        failures.append("platform: escalade cloud explicite uniquement")

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

    kernel = contracts["kernel"]
    baseline = kernel.get("baseline", {})
    candidate = kernel.get("candidate", {})
    boot = kernel.get("boot_policy", {})
    if baseline.get("source") != "fedora-official" or baseline.get("removable") is not False:
        failures.append("kernel: baseline Fedora officielle et non supprimable requise")
    if candidate.get("version") != "7.2.3" or candidate.get("source") != "kernel.org":
        failures.append("kernel: candidat Linux 7.2.3 kernel.org attendu")
    if candidate.get("automatic_promotion") is not False:
        failures.append("kernel: promotion automatique interdite")
    if int(boot.get("keep_minimum_bootable_kernels", 0)) < 2:
        failures.append("kernel: au moins deux kernels bootables requis")
    if boot.get("baseline_must_remain_bootable") is not True:
        failures.append("kernel: baseline Fedora doit rester bootable")

    models = contracts["models"]
    model_map = models.get("models", {})
    required_models = {key for key, value in model_map.items() if value.get("required") is True}
    expected_models = {"qwen-max", "gemma-deep", "devstral-devops"}
    if required_models != expected_models:
        failures.append("models: flotte requise doit rester exactement qwen/gemma/devstral")
    runtime_ids = [str(value.get("runtime_id", "")) for value in model_map.values()]
    if any(not runtime_id for runtime_id in runtime_ids) or len(runtime_ids) != len(set(runtime_ids)):
        failures.append("models: runtime_id absents ou dupliqués")
    fleet_policy = models.get("fleet_policy", {})
    if int(fleet_policy.get("exact_required_model_count", 0)) != 3:
        failures.append("models: exactement trois modèles requis")
    if fleet_policy.get("cloud_model_as_local_fallback") is not False:
        failures.append("models: fallback cloud interdit")

    backends = contracts["backends"]
    backend_map = backends.get("backends", {})
    expected_backends = {"ollama-vulkan", "llama-cpp-vulkan"}
    if set(backend_map) != expected_backends:
        failures.append("backends: seuls Ollama Vulkan et llama.cpp Vulkan sont autorisés")
    for backend_id, backend in backend_map.items():
        if backend.get("linux_native") is not True:
            failures.append(f"backends: {backend_id} doit être Linux natif")
        if backend.get("accelerator") != "vulkan":
            failures.append(f"backends: {backend_id} doit utiliser Vulkan")
        endpoint = str(backend.get("endpoint", ""))
        if endpoint and not _loopback(endpoint):
            failures.append(f"backends: {backend_id} endpoint non loopback")
    selection = backends.get("selection", {})
    if selection.get("automatic_promotion") is not False:
        failures.append("backends: promotion automatique interdite")
    if selection.get("no_cloud_fallback") is not True:
        failures.append("backends: aucun fallback cloud doit rester garanti")

    qualification = contracts["qualification"]
    full = qualification.get("full_gate", {})
    if full.get("name") != "HARD-40M" or int(full.get("max_wall_seconds", 0)) != 2400:
        failures.append("qualification: HARD-40M doit rester à 2400 s")
    if int(full.get("total_cases", 0)) != 30:
        failures.append("qualification: matrice complète doit rester à 30 cas")
    if full.get("contexts") != {8192: 24, 16384: 6}:
        failures.append("qualification: répartition 24 cas 8K + 6 cas 16K requise")
    if int(full.get("qwen_native_max_output_tokens", 0)) != 768:
        failures.append("qualification: probes Qwen natifs doivent rester bornés à 768 tokens")
    if int(full.get("case_timeout_seconds", 0)) != 210:
        failures.append("qualification: timeout/cas doit rester à 210 s")
    if set(qualification.get("required_models", [])) != expected_models:
        failures.append("qualification: les trois modèles doivent être obligatoires")
    safety = qualification.get("safety", {})
    if safety.get("cloud_calls_allowed") is not False:
        failures.append("qualification: aucun appel cloud autorisé")
    target = qualification.get("linux_performance_target", {})
    if target.get("baseline") != "fedora-stock-kernel-plus-ollama-vulkan":
        failures.append("qualification: baseline Linux Fedora stock attendue")
    promotion = qualification.get("promotion", {})
    promotion_keys = (
        "automatic_backend_promotion",
        "automatic_kernel_promotion",
        "automatic_v1_release",
    )
    if any(promotion.get(key) is not False for key in promotion_keys):
        failures.append("qualification: aucune promotion automatique autorisée")
    if promotion.get("final_human_approval_required") is not True:
        failures.append("qualification: approbation humaine finale requise")

    roadmap = contracts["roadmap"]
    project = roadmap.get("project", {})
    if project.get("identity") != "linux-native":
        failures.append("roadmap: identité Linux native requise")
    linux_stack = roadmap.get("linux_stack", {})
    if linux_stack.get("gpu_kernel_driver") != "xe":
        failures.append("roadmap: driver GPU xe requis")
    if linux_stack.get("gpu_api") != "vulkan" or linux_stack.get("gpu_userspace") != "mesa":
        failures.append("roadmap: pile GPU xe + Mesa/Vulkan requise")
    gates = roadmap.get("roadmap_gates", {})
    if list(gates) != [f"L{i}" for i in range(9)]:
        failures.append("roadmap: gates L0..L8 incomplets ou désordonnés")

    disallowed_suffixes = {".ps1", ".cmd", ".bat"}
    disallowed_files = [
        path.relative_to(root)
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in disallowed_suffixes
    ]
    if disallowed_files:
        failures.append(f"repository: entrypoints non Linux interdits: {disallowed_files}")

    if candidate.get("version") == "7.2.3":
        warnings.append(
            "Linux 7.2.3 reste un candidat: conserver le kernel Fedora officiel comme rollback"
        )

    return ContractReport(tuple(failures), tuple(warnings))
