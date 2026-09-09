from __future__ import annotations

from pathlib import Path
from typing import Any

from clawfedora.core_config import root_contract

EXPECTED_OLLAMA_VERSION = "0.32.14"
EXPECTED_OLLAMA_COMMIT = "d67ad83426633195089509347ffd4fe795120198"
EXPECTED_LLAMA_TAG = "b10516"
EXPECTED_LLAMA_COMMIT = "b95502ba9aa0eb73a2f4fc8878d7fbe6a847a0b9"
EXPECTED_KERNEL = "7.2.3"
EXPECTED_KERNEL_SHA256 = "8ba259e8e7b13ec6ef0941c8a39ad90b24bd4a4d6c0010ba6bafb794550ecd03"
EXPECTED_SPECIALIST = "hf.co/mistralai/Ministral-3-14B-Reasoning-2512-GGUF:Q4_K_M"
EXPECTED_CHALLENGER = "granite4.2:8b-q4_K_M"


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def validate_optimization_contracts(
    repo_root: Path,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    failures: list[str] = []
    warnings: list[str] = []
    try:
        policy = root_contract(repo_root, "optimization_policy.yaml")
        versions = root_contract(repo_root, "runtime_versions.yaml")
        backends = root_contract(repo_root, "runtime_backends.yaml")
        kernel = root_contract(repo_root, "kernel_policy.yaml")
        models = root_contract(repo_root, "model_catalog.yaml")
    except (FileNotFoundError, ValueError) as exc:
        return (f"l6: {exc}",), ()

    if policy.get("gate") != "L6":
        failures.append("l6: gate doit être L6")

    pins = _mapping(policy.get("pins"))
    ollama_pin = _mapping(pins.get("ollama"))
    llama_pin = _mapping(pins.get("llama_cpp"))
    kernel_pin = _mapping(pins.get("kernel_candidate"))
    if ollama_pin.get("version") != EXPECTED_OLLAMA_VERSION:
        failures.append("l6: pin Ollama exact invalide")
    if ollama_pin.get("commit") != EXPECTED_OLLAMA_COMMIT:
        failures.append("l6: commit Ollama exact invalide")
    if llama_pin.get("tag") != EXPECTED_LLAMA_TAG:
        failures.append("l6: tag llama.cpp exact invalide")
    if llama_pin.get("commit") != EXPECTED_LLAMA_COMMIT:
        failures.append("l6: commit llama.cpp exact invalide")
    if kernel_pin.get("version") != EXPECTED_KERNEL:
        failures.append("l6: version kernel candidate invalide")
    if kernel_pin.get("sha256") != EXPECTED_KERNEL_SHA256:
        failures.append("l6: SHA-256 kernel candidate invalide")

    version_llama = _mapping(versions.get("llama_cpp"))
    version_ollama = _mapping(versions.get("ollama"))
    version_kernel = _mapping(versions.get("kernel"))
    if version_llama.get("commit") != llama_pin.get("commit"):
        failures.append("l6: drift runtime_versions/optimization llama.cpp")
    if version_ollama.get("version") != ollama_pin.get("version"):
        failures.append("l6: drift runtime_versions/optimization Ollama")
    if version_kernel.get("upstream_candidate") != kernel_pin.get("version"):
        failures.append("l6: drift runtime_versions/optimization kernel")
    if version_kernel.get("upstream_candidate_sha256") != kernel_pin.get("sha256"):
        failures.append("l6: drift SHA-256 kernel")

    backend_map = _mapping(backends.get("backends"))
    expected_backend_ids = {"ollama-vulkan", "llama-cpp-vulkan"}
    if set(backend_map) != expected_backend_ids:
        failures.append("l6: matrice runtime doit rester strictement Vulkan")
    for backend_id in sorted(expected_backend_ids):
        backend = _mapping(backend_map.get(backend_id))
        endpoint = str(backend.get("endpoint", ""))
        if not endpoint.startswith("http://127.0.0.1:"):
            failures.append(f"l6: {backend_id} doit rester loopback")
        if backend.get("linux_native") is not True:
            failures.append(f"l6: {backend_id} doit être Linux-native")
        if backend.get("accelerator") != "vulkan":
            failures.append(f"l6: {backend_id} doit utiliser Vulkan")
    selection = _mapping(backends.get("selection"))
    if selection.get("automatic_promotion") is not False:
        failures.append("l6: promotion backend automatique interdite")
    if selection.get("no_cloud_fallback") is not True:
        failures.append("l6: fallback cloud interdit")

    runtime_cmp = _mapping(policy.get("runtime_comparison"))
    if runtime_cmp.get("baseline") != "ollama-vulkan":
        failures.append("l6: baseline runtime doit rester ollama-vulkan")
    if runtime_cmp.get("candidates") != ["llama-cpp-vulkan"]:
        failures.append("l6: llama.cpp Vulkan doit être l'unique candidat runtime")
    if float(runtime_cmp.get("aggregate_improvement_target_pct", 0)) != 10.0:
        failures.append("l6: cible runtime agrégée doit rester 10%")
    if float(runtime_cmp.get("maximum_single_model_regression_pct", 999)) != 5.0:
        failures.append("l6: régression runtime modèle max doit rester 5%")
    if int(runtime_cmp.get("minimum_repeated_runs", 0)) < 3:
        failures.append("l6: au moins 3 runs runtime requis")
    if runtime_cmp.get("automatic_promotion") is not False:
        failures.append("l6: promotion runtime automatique interdite")

    kernel_cmp = _mapping(policy.get("kernel_comparison"))
    kernel_candidate = _mapping(kernel.get("candidate"))
    kernel_perf = _mapping(kernel.get("performance_policy"))
    if kernel_candidate.get("version") != EXPECTED_KERNEL:
        failures.append("l6: kernel_policy candidate divergent")
    if kernel_candidate.get("automatic_promotion") is not False:
        failures.append("l6: promotion kernel automatique interdite")
    if float(kernel_cmp.get("minimum_aggregate_improvement_pct", 0)) != float(
        kernel_perf.get("minimum_aggregate_improvement_pct", -1)
    ):
        failures.append("l6: seuil agrégé kernel divergent")
    if float(kernel_cmp.get("maximum_single_model_regression_pct", 999)) != float(
        kernel_perf.get("maximum_single_model_regression_pct", -1)
    ):
        failures.append("l6: seuil régression kernel divergent")
    if int(kernel_cmp.get("minimum_repeated_runs", 0)) < 3:
        failures.append("l6: au moins 3 runs kernel requis")

    challenger_policy = _mapping(policy.get("model_challenger"))
    challengers = _mapping(models.get("challengers"))
    devops_challengers = _mapping(challengers.get("devstral-devops"))
    granite = _mapping(devops_challengers.get("granite-devops"))
    if challenger_policy.get("slot") != "devstral-devops":
        failures.append("l6: challenger doit cibler le slot spécialiste DevOps")
    if challenger_policy.get("incumbent") != EXPECTED_SPECIALIST:
        failures.append("l6: incumbent spécialiste inattendu")
    if challenger_policy.get("challenger") != EXPECTED_CHALLENGER:
        failures.append("l6: challenger Granite inattendu")
    if challenger_policy.get("challenger") != granite.get("runtime_id"):
        failures.append("l6: challenger Granite divergent du catalogue")
    if granite.get("automatic_promotion") is not False:
        failures.append("l6: promotion automatique challenger interdite")
    if challenger_policy.get("automatic_promotion") is not False:
        failures.append("l6: promotion modèle automatique interdite")
    for required in (
        "require_coding_pass",
        "require_tool_calling_pass",
        "require_tool_repair_pass",
        "require_security_pass",
    ):
        if challenger_policy.get(required) is not True:
            failures.append(f"l6: {required}=true requis")

    staging = _mapping(policy.get("artifact_staging"))
    if staging.get("network_downloads_allowed") is not False:
        failures.append("l6: staging ne doit jamais télécharger pendant comparaison")
    if staging.get("explicit_only") is not True:
        failures.append("l6: staging explicite requis")
    if staging.get("require_sha256") is not True:
        failures.append("l6: SHA-256 des artefacts requis")

    evidence = _mapping(policy.get("comparison_evidence"))
    if evidence.get("raw_outputs_persisted") is not False:
        failures.append("l6: sorties brutes persistées interdites")
    if evidence.get("cloud_calls_allowed") is not False:
        failures.append("l6: appels cloud interdits")

    promotion = _mapping(policy.get("promotion"))
    if promotion.get("human_approval_required") is not True:
        failures.append("l6: approbation humaine requise")
    if promotion.get("no_automatic_config_mutation") is not True:
        failures.append("l6: mutation automatique de config interdite")

    if not failures:
        warnings.append("L6 logiciel prêt; aucun gagnant runtime/kernel/modèle n'est revendiqué")
    return tuple(failures), tuple(warnings)
