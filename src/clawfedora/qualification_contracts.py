from __future__ import annotations

from pathlib import Path
from typing import Any

from clawfedora.core_config import load_yaml, root_contract
from clawfedora.qualification import build_plan


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def validate_qualification_contracts(repo_root: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    failures: list[str] = []
    warnings: list[str] = []
    try:
        policy = root_contract(repo_root, "qualification_policy.yaml")
        catalog = root_contract(repo_root, "model_catalog.yaml")
        suite_path = repo_root / "benchmarks" / "suites" / "linux_devops_v1.yaml"
        suite = load_yaml(suite_path)
    except (FileNotFoundError, ValueError) as exc:
        return (f"qualification: {exc}",), ()

    if policy.get("suite") != "linux-devops-v1" or suite.get("id") != "linux-devops-v1":
        failures.append("qualification: suite linux-devops-v1 requise")
    try:
        plan = build_plan(catalog, policy, suite)
    except (KeyError, TypeError, ValueError) as exc:
        failures.append(f"qualification: plan invalide: {exc}")
        plan = None

    full = _mapping(policy.get("full_gate"))
    if full.get("name") != "HARD-40M":
        failures.append("qualification: nom HARD-40M requis")
    if int(full.get("max_wall_seconds", 0)) != 2400:
        failures.append("qualification: plafond global doit rester exactement 2400 s")
    if int(full.get("evaluation_reserve_seconds", 0)) < 60:
        failures.append("qualification: réserve évaluation >=60 s requise")
    if int(full.get("total_cases", 0)) != 30:
        failures.append("qualification: exactement 30 cas requis")
    contexts = {int(key): int(value) for key, value in _mapping(full.get("contexts")).items()}
    if contexts != {8192: 24, 16384: 6}:
        failures.append("qualification: distribution 24x8K + 6x16K requise")
    if int(full.get("qwen_native_reasoning_probes", 0)) != 3:
        failures.append("qualification: exactement 3 probes Qwen natifs requis")
    if int(full.get("qwen_native_max_output_tokens", 0)) != 768:
        failures.append("qualification: plafond probes Qwen doit rester à 768 tokens")
    if int(full.get("case_timeout_seconds", 0)) != 210:
        failures.append("qualification: timeout/cas doit rester à 210 s")

    expected_models = {"qwen-max", "gemma-deep", "devstral-devops"}
    if set(policy.get("required_models", [])) != expected_models:
        failures.append("qualification: les trois modèles requis doivent rester exacts")

    thresholds = _mapping(_mapping(policy.get("automated_gates")).get("thresholds"))
    if float(thresholds.get("max_error_rate", 1.0)) > 0.0:
        failures.append("qualification: max_error_rate ne peut dépasser 0")
    if float(thresholds.get("min_check_pass_rate", 0.0)) < 0.875:
        failures.append("qualification: min_check_pass_rate ne peut descendre sous 0.875")
    if float(thresholds.get("min_median_tokens_per_second", 0.0)) < 6.0:
        failures.append("qualification: min median tok/s ne peut descendre sous 6")
    if float(thresholds.get("max_p95_first_token_ms", 999999.0)) > 12000:
        failures.append("qualification: p95 premier token ne peut dépasser 12000 ms")
    per_context = _mapping(thresholds.get("per_context_min_check_pass_rate"))
    if float(per_context.get("8192", 0.0)) < 0.875:
        failures.append("qualification: seuil 8K ne peut descendre sous 0.875")
    if float(per_context.get("16384", 0.0)) < 0.75:
        failures.append("qualification: seuil 16K ne peut descendre sous 0.75")

    safety = _mapping(policy.get("safety"))
    required_false = (
        "cloud_calls_allowed",
        "implicit_model_downloads_allowed",
        "suspend_allowed",
        "persist_raw_outputs_in_git",
    )
    for key in required_false:
        if safety.get(key) is not False:
            failures.append(f"qualification: safety.{key}=false requis")
    if safety.get("endpoint_loopback_only") is not True:
        failures.append("qualification: endpoint loopback-only requis")
    if safety.get("fail_fast_on_api_error") is not True:
        failures.append("qualification: fail-fast API requis")
    if safety.get("fail_fast_on_case_timeout") is not True:
        failures.append("qualification: fail-fast timeout requis")
    if safety.get("fail_on_output_truncation") is not True:
        failures.append("qualification: sortie tronquée doit échouer")

    preflight = _mapping(policy.get("preflight"))
    if preflight.get("l2_fedora_hardware_gate_required") is not True:
        failures.append("qualification: preflight L2 obligatoire")
    if preflight.get("l3_b580_vulkan_gate_required") is not True:
        failures.append("qualification: preflight L3 obligatoire")
    if preflight.get("performance_profile_required") is not True:
        failures.append("qualification: profil performance obligatoire")
    if preflight.get("no_suspend_required") is not True:
        failures.append("qualification: protection contre suspension obligatoire")
    if preflight.get("qualification_backend") != "ollama-vulkan":
        failures.append("qualification: baseline L5 doit rester Ollama Vulkan")

    promotion = _mapping(policy.get("promotion"))
    for key in (
        "automatic_backend_promotion",
        "automatic_kernel_promotion",
        "automatic_v1_release",
    ):
        if promotion.get(key) is not False:
            failures.append(f"qualification: {key}=false requis")
    if promotion.get("final_human_approval_required") is not True:
        failures.append("qualification: approbation humaine finale requise")

    comparison = _mapping(policy.get("runtime_comparison"))
    candidates = comparison.get("candidates", [])
    if candidates != ["ollama-vulkan", "llama-cpp-vulkan", "llama-cpp-sycl"]:
        failures.append("qualification: matrice de backends Linux attendue")
    if comparison.get("automatic_winner_promotion") is not False:
        failures.append("qualification: promotion automatique du backend interdite")

    scenarios = suite.get("scenarios", [])
    if not isinstance(scenarios, list) or len(scenarios) != 12:
        failures.append("qualification: la suite doit contenir exactement 12 scénarios")
    else:
        for raw in scenarios:
            if not isinstance(raw, dict):
                failures.append("qualification: scénario invalide")
                continue
            limit = int(raw.get("max_output_tokens", suite.get("default_max_output_tokens", 0)))
            if limit < 32 or limit > 768:
                failures.append(
                    f"qualification: limite sortie invalide pour {raw.get('id')}: {limit}"
                )

    if plan is not None:
        if len(plan.cases) != 30 or plan.contexts != {8192: 24, 16384: 6}:
            failures.append("qualification: plan matérialisé incohérent")
        if len(plan.qwen_native_cases) != 3:
            failures.append("qualification: probes Qwen matérialisés incohérents")

    if not failures:
        warnings.append(
            "L5 est logiciellement prêt; aucun PASS matériel/performance n'est "
            "revendiqué avant run Fedora"
        )
    return tuple(failures), tuple(warnings)
