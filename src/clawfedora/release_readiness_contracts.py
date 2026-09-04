from __future__ import annotations

from pathlib import Path
from typing import Any

from clawfedora.core_config import root_contract


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"L8: {label} doit être un objet")
    return value


def _safe_relative_pattern(value: str, label: str) -> bool:
    path = Path(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts


def validate_release_readiness_contracts(
    repo_root: Path,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    failures: list[str] = []
    warnings: list[str] = []
    try:
        contract = root_contract(repo_root, "release_readiness.yaml")
        catalog = root_contract(repo_root, "model_catalog.yaml")
        qualification = root_contract(repo_root, "qualification_policy.yaml")
        optimization = root_contract(repo_root, "optimization_policy.yaml")
        golden = root_contract(repo_root, "golden_projects.yaml")
    except (FileNotFoundError, ValueError) as exc:
        return (f"L8: {exc}",), ()

    if contract.get("schema_version") != "1.0.0":
        failures.append("L8: schema_version doit rester 1.0.0")
    if contract.get("platform_version") != "0.1.0":
        failures.append("L8: platform_version doit rester 0.1.0")
    if contract.get("gate") != "L8":
        failures.append("L8: gate doit rester L8")

    policy = _mapping(contract.get("policy"), "policy")
    if list(policy.get("required_gates", [])) != [
        "L0",
        "L1",
        "L2",
        "L3",
        "L4",
        "L5",
        "L6",
        "L7",
    ]:
        failures.append("L8: les gates requis doivent rester exactement L0 à L7")
    if list(policy.get("runtime_evidence_gates", [])) != ["L2", "L3", "L4", "L5", "L6", "L7"]:
        failures.append("L8: les preuves runtime doivent rester exactement L2 à L7")
    if list(policy.get("readiness_verdicts", [])) != ["BLOCKED", "READY_FOR_HUMAN_REVIEW"]:
        failures.append("L8: verdicts readiness invalides")
    if policy.get("approval_verdict") != "APPROVED_FOR_V1_PREPARATION":
        failures.append("L8: verdict d'approbation invalide")

    required_false = (
        "automatic_human_approval",
        "approval_mutates_runtime_config",
        "approval_publishes_release",
        "thresholds_may_be_lowered",
        "cloud_calls_allowed",
    )
    for key in required_false:
        if policy.get(key) is not False:
            failures.append(f"L8: policy.{key} doit rester false")
    for key in (
        "explicit_human_approval_required",
        "approval_requires_acknowledgement",
        "evidence_must_be_under_runtime_root",
    ):
        if policy.get(key) is not True:
            failures.append(f"L8: policy.{key} doit rester true")
    if policy.get("evidence_hash_algorithm") != "sha256":
        failures.append("L8: seul SHA-256 est autorisé pour le manifeste de preuves")

    software = _mapping(contract.get("software_contracts"), "software_contracts")
    expected_software = {
        "repository",
        "core",
        "lifecycle",
        "qualification",
        "optimization",
        "golden_projects",
        "release_readiness",
    }
    software_required = all(value == "required" for value in software.values())
    if set(software) != expected_software or not software_required:
        failures.append("L8: tous les contrats logiciels requis doivent rester obligatoires")

    evidence = _mapping(contract.get("evidence"), "evidence")
    for gate in ("l2", "l3", "l4", "l5", "l6", "l7"):
        if gate not in evidence:
            failures.append(f"L8: evidence.{gate} absent")
            continue
        item = _mapping(evidence[gate], f"evidence.{gate}")
        expected_gate = gate.upper()
        if item.get("gate") != expected_gate:
            failures.append(f"L8: evidence.{gate}.gate doit être {expected_gate}")
        for key in ("glob", "fallback_glob"):
            raw = item.get(key)
            if raw is not None and not _safe_relative_pattern(str(raw), f"evidence.{gate}.{key}"):
                failures.append(f"L8: chemin interdit evidence.{gate}.{key}")

    l4 = _mapping(evidence.get("l4"), "evidence.l4")
    if l4.get("required_backend") != "ollama-vulkan":
        failures.append("L8: L4 doit rester qualifié sur la baseline Ollama Vulkan")
    if int(l4.get("required_agent_smokes", 0)) != 8:
        failures.append("L8: L4 doit conserver 8 smokes agents")
    if int(l4.get("required_stability_runs", 0)) != 3:
        failures.append("L8: L4 doit conserver 3 runs de stabilité")

    l5 = _mapping(evidence.get("l5"), "evidence.l5")
    if int(l5.get("required_cases", 0)) != 30:
        failures.append("L8: L5 doit conserver 30 cas")
    if l5.get("thresholds_source") != "qualification_policy.yaml":
        failures.append("L8: les seuils L5 doivent provenir du contrat qualification courant")
    full_gate = _mapping(qualification.get("full_gate"), "qualification.full_gate")
    if int(full_gate.get("max_wall_seconds", 0)) != 2400:
        failures.append("L8: HARD-40M doit rester limité à 2400 s")
    promotion = _mapping(qualification.get("promotion"), "qualification.promotion")
    if promotion.get("automatic_v1_release") is not False:
        failures.append("L8: qualification ne peut pas publier automatiquement V1")
    if promotion.get("final_human_approval_required") is not True:
        failures.append("L8: qualification doit exiger l'approbation humaine finale")

    l6 = _mapping(evidence.get("l6"), "evidence.l6")
    accepted = set(str(value) for value in l6.get("accepted_decision_verdicts", []))
    if accepted != {"KEEP_BASELINE", "ELIGIBLE_FOR_HUMAN_PROMOTION"}:
        failures.append("L8: verdicts de décision L6 invalides")
    if l6.get("automatic_promotion_required") is not False:
        failures.append("L8: L6 ne doit jamais exiger de promotion automatique")
    required_decisions = l6.get("required_decisions", [])
    if not isinstance(required_decisions, list):
        failures.append("L8: required_decisions L6 invalide")
    else:
        normalized = {
            (str(item.get("kind")), str(item.get("candidate_id")))
            for item in required_decisions
            if isinstance(item, dict)
        }
        expected = {
            ("runtime", "llama-cpp-vulkan"),
            ("kernel", "upstream-7.2.3"),
            ("model-challenger", "ministral-3:14b-instruct-2512-q4_K_M"),
        }
        if normalized != expected:
            failures.append("L8: les trois décisions L6 obligatoires ont dérivé")

    runtime_cfg = _mapping(
        optimization.get("runtime_comparison"),
        "optimization.runtime_comparison",
    )
    kernel_cfg = _mapping(
        optimization.get("kernel_comparison"),
        "optimization.kernel_comparison",
    )
    challenger_cfg = _mapping(
        optimization.get("model_challenger"),
        "optimization.model_challenger",
    )
    if runtime_cfg.get("automatic_promotion") is not False:
        failures.append("L8: promotion automatique runtime interdite")
    if kernel_cfg.get("automatic_promotion") is not False:
        failures.append("L8: promotion automatique kernel interdite")
    if challenger_cfg.get("automatic_promotion") is not False:
        failures.append("L8: promotion automatique challenger interdite")
    if challenger_cfg.get("slot") != "gemma-deep":
        failures.append("L8: Ministral doit challenger uniquement gemma-deep")
    if challenger_cfg.get("challenger") != "ministral-3:14b-instruct-2512-q4_K_M":
        failures.append("L8: challenger Ministral inattendu")

    models = _mapping(catalog.get("models"), "model_catalog.models")
    required_aliases = {
        str(alias)
        for alias, raw in models.items()
        if isinstance(raw, dict) and raw.get("required") is True
    }
    if required_aliases != {"qwen-max", "gemma-deep", "devstral-devops"}:
        failures.append("L8: flotte nominale doit rester exactement à trois alias")
    fleet = _mapping(catalog.get("fleet_policy"), "model_catalog.fleet_policy")
    if int(fleet.get("exact_required_model_count", 0)) != 3:
        failures.append("L8: exact_required_model_count doit rester 3")
    if fleet.get("challenger_counts_toward_required_fleet") is not False:
        failures.append("L8: le challenger ne doit pas compter dans la flotte nominale")

    golden_policy = _mapping(golden.get("policy"), "golden_projects.policy")
    if golden_policy.get("final_human_completion_allowed") is not False:
        failures.append("L8: L7 ne doit jamais permettre la complétion humaine automatique")
    if golden_policy.get("require_human_gate_preserved") is not True:
        failures.append("L8: L7 doit préserver le gate humain")

    approval = _mapping(contract.get("approval"), "approval")
    for key in ("report_directory", "approval_directory"):
        value = str(approval.get(key, ""))
        safe = _safe_relative_pattern(value, f"approval.{key}")
        if not safe or not value.startswith("proofs/l8/"):
            failures.append(f"L8: approval.{key} doit rester sous proofs/l8")
    if approval.get("immutable_records") is not True:
        failures.append("L8: les approbations doivent rester immuables")
    if approval.get("report_hash_required") is not True:
        failures.append("L8: l'approbation doit référencer le hash du rapport")
    if approval.get("current_evidence_recheck_required") is not True:
        failures.append("L8: l'approbation doit revérifier les preuves courantes")
    if approval.get("human_approval_field") != "human_approved":
        failures.append("L8: champ d'approbation humaine inattendu")
    if approval.get("approval_scope") != "prepare-v1":
        failures.append("L8: scope d'approbation inattendu")

    warnings.append(
        "L8: framework logiciel prêt; READY_FOR_HUMAN_REVIEW exige les preuves réelles L2-L7"
    )
    warnings.append("L8: aucune approbation V1 n'est automatique")
    return tuple(failures), tuple(warnings)
