from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from clawfedora.qualification_contracts import validate_qualification_contracts

ROOT = Path(__file__).resolve().parents[1]


def _copy_contracts(tmp_path: Path) -> tuple[Path, Path]:
    config = tmp_path / "config"
    suite_dir = tmp_path / "benchmarks" / "suites"
    config.mkdir(parents=True)
    suite_dir.mkdir(parents=True)
    for name in ("qualification_policy.yaml", "model_catalog.yaml"):
        (config / name).write_text(
            (ROOT / "config" / name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    suite_path = suite_dir / "linux_devops_v1.yaml"
    suite_path.write_text(
        (ROOT / "benchmarks" / "suites" / "linux_devops_v1.yaml").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    return config / "qualification_policy.yaml", suite_path


def _load(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _save(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_qualification_contracts_pass_on_repository() -> None:
    failures, warnings = validate_qualification_contracts(ROOT)
    assert failures == ()
    assert warnings


def test_contract_rejects_model_fleet_drift(tmp_path: Path) -> None:
    _copy_contracts(tmp_path)
    catalog_path = tmp_path / "config" / "model_catalog.yaml"
    payload = _load(catalog_path)
    payload["models"]["qwen-max"]["runtime_id"] = "qwen3.5:27b"
    payload["models"]["devstral-devops"]["family"] = "qwen"
    payload["models"]["gemma-deep"]["nominal_context_tokens"] = 16384
    _save(catalog_path, payload)
    failures, _ = validate_qualification_contracts(tmp_path)
    joined = "\n".join(failures)
    assert "runtime nominal inattendu pour qwen-max" in joined
    assert "spécialiste DevOps" in joined
    assert "contexte nominal 8K requis pour gemma-deep" in joined


def test_contract_rejects_challenger_auto_promotion(tmp_path: Path) -> None:
    _copy_contracts(tmp_path)
    catalog_path = tmp_path / "config" / "model_catalog.yaml"
    payload = _load(catalog_path)
    challenger = payload["challengers"]["gemma-deep"]["ministral-3-14b"]
    challenger["automatic_promotion"] = True
    _save(catalog_path, payload)
    failures, _ = validate_qualification_contracts(tmp_path)
    assert any("promotion automatique challenger" in item for item in failures)


def test_contract_rejects_weakened_hard40_threshold(tmp_path: Path) -> None:
    policy_path, _ = _copy_contracts(tmp_path)
    payload = _load(policy_path)
    payload["automated_gates"]["thresholds"]["min_check_pass_rate"] = 0.5
    _save(policy_path, payload)
    failures, _ = validate_qualification_contracts(tmp_path)
    assert any("min_check_pass_rate" in item for item in failures)


def test_contract_rejects_external_endpoint_policy_and_auto_promotion(tmp_path: Path) -> None:
    policy_path, _ = _copy_contracts(tmp_path)
    payload = _load(policy_path)
    payload["safety"]["endpoint_loopback_only"] = False
    payload["promotion"]["automatic_backend_promotion"] = True
    _save(policy_path, payload)
    failures, _ = validate_qualification_contracts(tmp_path)
    assert any("loopback-only" in item for item in failures)
    assert any("automatic_backend_promotion" in item for item in failures)


def test_contract_reports_all_critical_policy_regressions(tmp_path: Path) -> None:
    policy_path, _ = _copy_contracts(tmp_path)
    payload = _load(policy_path)
    payload["suite"] = "wrong-suite"
    payload["full_gate"].update(
        {
            "name": "SOFT",
            "max_wall_seconds": 3600,
            "evaluation_reserve_seconds": 0,
            "total_cases": 29,
            "contexts": {8192: 23, 16384: 6},
            "qwen_native_reasoning_probes": 2,
            "qwen_native_max_output_tokens": 1024,
            "case_timeout_seconds": 300,
        }
    )
    payload["required_models"] = ["qwen-max"]
    thresholds = payload["automated_gates"]["thresholds"]
    thresholds.update(
        {
            "max_error_rate": 0.1,
            "min_check_pass_rate": 0.5,
            "min_median_tokens_per_second": 1.0,
            "max_p95_first_token_ms": 30000,
        }
    )
    thresholds["per_context_min_check_pass_rate"] = {"8192": 0.5, "16384": 0.5}
    for key in (
        "cloud_calls_allowed",
        "implicit_model_downloads_allowed",
        "suspend_allowed",
        "persist_raw_outputs_in_git",
    ):
        payload["safety"][key] = True
    payload["safety"]["endpoint_loopback_only"] = False
    payload["safety"]["fail_fast_on_api_error"] = False
    payload["safety"]["fail_fast_on_case_timeout"] = False
    payload["safety"]["fail_on_output_truncation"] = False
    payload["preflight"].update(
        {
            "l2_fedora_hardware_gate_required": False,
            "l3_b580_vulkan_gate_required": False,
            "performance_profile_required": False,
            "no_suspend_required": False,
            "qualification_backend": "llama-cpp-vulkan",
        }
    )
    payload["promotion"].update(
        {
            "automatic_backend_promotion": True,
            "automatic_kernel_promotion": True,
            "automatic_v1_release": True,
            "final_human_approval_required": False,
        }
    )
    payload["runtime_comparison"]["candidates"] = ["ollama-vulkan"]
    payload["runtime_comparison"]["automatic_winner_promotion"] = True
    _save(policy_path, payload)

    failures, warnings = validate_qualification_contracts(tmp_path)
    joined = "\n".join(failures)
    assert warnings == ()
    for marker in (
        "suite linux-devops-v1",
        "nom HARD-40M",
        "2400 s",
        "réserve évaluation",
        "exactement 30 cas",
        "24x8K + 6x16K",
        "3 probes Qwen",
        "768 tokens",
        "210 s",
        "trois modèles",
        "max_error_rate",
        "min_check_pass_rate",
        "median tok/s",
        "p95 premier token",
        "seuil 8K",
        "seuil 16K",
        "cloud_calls_allowed",
        "implicit_model_downloads_allowed",
        "suspend_allowed",
        "persist_raw_outputs_in_git",
        "loopback-only",
        "fail-fast API",
        "fail-fast timeout",
        "sortie tronquée",
        "preflight L2",
        "preflight L3",
        "profil performance",
        "protection contre suspension",
        "baseline L5",
        "automatic_backend_promotion",
        "automatic_kernel_promotion",
        "automatic_v1_release",
        "approbation humaine",
        "matrice de backends",
        "promotion automatique du backend",
    ):
        assert marker in joined


def test_contract_rejects_invalid_suite_shape_and_output_limit(tmp_path: Path) -> None:
    _, suite_path = _copy_contracts(tmp_path)
    suite = _load(suite_path)
    suite["id"] = "wrong-suite"
    scenarios = suite["scenarios"]
    assert isinstance(scenarios, list)
    scenarios[0]["max_output_tokens"] = 769
    scenarios.pop()
    _save(suite_path, suite)
    failures, _ = validate_qualification_contracts(tmp_path)
    joined = "\n".join(failures)
    assert "suite linux-devops-v1" in joined
    assert "exactement 12 scénarios" in joined


def test_contract_returns_controlled_failure_when_files_are_missing(tmp_path: Path) -> None:
    failures, warnings = validate_qualification_contracts(tmp_path)
    assert len(failures) == 1
    assert "qualification:" in failures[0]
    assert warnings == ()
