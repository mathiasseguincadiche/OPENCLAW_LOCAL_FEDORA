from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from clawfedora.optimization_contracts import validate_optimization_contracts

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "optimization_policy.yaml",
    "runtime_versions.yaml",
    "runtime_backends.yaml",
    "kernel_policy.yaml",
    "model_catalog.yaml",
)


def _sandbox(tmp_path: Path) -> Path:
    config = tmp_path / "config"
    config.mkdir()
    for name in FILES:
        shutil.copy(ROOT / "config" / name, config / name)
    return tmp_path


def _load(root: Path, name: str) -> dict[str, object]:
    payload = yaml.safe_load((root / "config" / name).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _save(root: Path, name: str, payload: dict[str, object]) -> None:
    (root / "config" / name).write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


def test_l6_contract_passes_repository_contracts() -> None:
    failures, warnings = validate_optimization_contracts(ROOT)
    assert failures == ()
    assert warnings == (
        "L6 logiciel prêt; aucun gagnant runtime/kernel/modèle n'est revendiqué",
    )


def test_l6_contract_reports_missing_contract(tmp_path: Path) -> None:
    failures, warnings = validate_optimization_contracts(tmp_path)
    assert len(failures) == 1
    assert failures[0].startswith("l6:")
    assert warnings == ()


def test_l6_contract_rejects_policy_and_version_drift(tmp_path: Path) -> None:
    root = _sandbox(tmp_path)
    policy = _load(root, "optimization_policy.yaml")
    policy["gate"] = "L5"
    pins = policy["pins"]
    assert isinstance(pins, dict)
    ollama = pins["ollama"]
    llama = pins["llama_cpp"]
    kernel_pin = pins["kernel_candidate"]
    assert isinstance(ollama, dict)
    assert isinstance(llama, dict)
    assert isinstance(kernel_pin, dict)
    ollama["version"] = "0.0.0"
    ollama["commit"] = "bad"
    llama["tag"] = "bad"
    llama["commit"] = "bad"
    kernel_pin["version"] = "0.0.0"
    kernel_pin["sha256"] = "bad"

    runtime_cmp = policy["runtime_comparison"]
    kernel_cmp = policy["kernel_comparison"]
    challenger = policy["model_challenger"]
    staging = policy["artifact_staging"]
    evidence = policy["comparison_evidence"]
    promotion = policy["promotion"]
    for value in (runtime_cmp, kernel_cmp, challenger, staging, evidence, promotion):
        assert isinstance(value, dict)
    runtime_cmp["baseline"] = "bad"
    runtime_cmp["aggregate_improvement_target_pct"] = 9.0
    runtime_cmp["maximum_single_model_regression_pct"] = 6.0
    runtime_cmp["minimum_repeated_runs"] = 2
    runtime_cmp["automatic_promotion"] = True
    kernel_cmp["minimum_aggregate_improvement_pct"] = 4.0
    kernel_cmp["maximum_single_model_regression_pct"] = 3.0
    kernel_cmp["minimum_repeated_runs"] = 2
    challenger["incumbent"] = "bad"
    challenger["challenger"] = "bad"
    challenger["automatic_promotion"] = True
    staging["network_downloads_allowed"] = True
    staging["explicit_only"] = False
    staging["require_sha256"] = False
    evidence["raw_outputs_persisted"] = True
    evidence["cloud_calls_allowed"] = True
    promotion["human_approval_required"] = False
    promotion["no_automatic_config_mutation"] = False
    _save(root, "optimization_policy.yaml", policy)

    versions = _load(root, "runtime_versions.yaml")
    version_ollama = versions["ollama"]
    version_llama = versions["llama_cpp"]
    version_kernel = versions["kernel"]
    assert isinstance(version_ollama, dict)
    assert isinstance(version_llama, dict)
    assert isinstance(version_kernel, dict)
    version_ollama["version"] = "different"
    version_llama["commit"] = "different"
    version_kernel["upstream_candidate"] = "different"
    version_kernel["upstream_candidate_sha256"] = "different"
    _save(root, "runtime_versions.yaml", versions)

    failures, warnings = validate_optimization_contracts(root)
    joined = "\n".join(failures)
    assert warnings == ()
    assert "gate doit être L6" in joined
    assert "pin Ollama exact invalide" in joined
    assert "commit Ollama exact invalide" in joined
    assert "tag llama.cpp exact invalide" in joined
    assert "commit llama.cpp exact invalide" in joined
    assert "version kernel candidate invalide" in joined
    assert "SHA-256 kernel candidate invalide" in joined
    assert "drift runtime_versions/optimization" in joined
    assert "drift SHA-256 kernel" in joined
    assert "baseline runtime" in joined
    assert "cible runtime agrégée" in joined
    assert "régression runtime" in joined
    assert "au moins 3 runs runtime" in joined
    assert "promotion runtime automatique" in joined
    assert "seuil agrégé kernel divergent" in joined
    assert "seuil régression kernel divergent" in joined
    assert "au moins 3 runs kernel" in joined
    assert "incumbent documentaire inattendu" in joined
    assert "challenger Ministral divergent" in joined
    assert "promotion modèle automatique" in joined
    assert "staging ne doit jamais télécharger" in joined
    assert "staging explicite requis" in joined
    assert "SHA-256 des artefacts requis" in joined
    assert "sorties brutes persistées interdites" in joined
    assert "appels cloud interdits" in joined
    assert "approbation humaine requise" in joined
    assert "mutation automatique de config interdite" in joined


def test_l6_contract_rejects_backend_kernel_and_challenger_drift(tmp_path: Path) -> None:
    root = _sandbox(tmp_path)

    backends = _load(root, "runtime_backends.yaml")
    backend_map = backends["backends"]
    selection = backends["selection"]
    assert isinstance(backend_map, dict)
    assert isinstance(selection, dict)
    for backend_id in ("ollama-vulkan", "llama-cpp-vulkan", "llama-cpp-sycl"):
        backend = backend_map[backend_id]
        assert isinstance(backend, dict)
        backend["endpoint"] = "http://0.0.0.0:9999"
        backend["linux_native"] = False
    selection["automatic_promotion"] = True
    selection["no_cloud_fallback"] = False
    _save(root, "runtime_backends.yaml", backends)

    kernel = _load(root, "kernel_policy.yaml")
    candidate = kernel["candidate"]
    performance = kernel["performance_policy"]
    assert isinstance(candidate, dict)
    assert isinstance(performance, dict)
    candidate["version"] = "0.0.0"
    candidate["automatic_promotion"] = True
    performance["minimum_aggregate_improvement_pct"] = 99.0
    performance["maximum_single_model_regression_pct"] = 99.0
    _save(root, "kernel_policy.yaml", kernel)

    models = _load(root, "model_catalog.yaml")
    challengers = models["challengers"]
    assert isinstance(challengers, dict)
    gemma = challengers["gemma-deep"]
    assert isinstance(gemma, dict)
    ministral = gemma["ministral-3-14b"]
    assert isinstance(ministral, dict)
    ministral["automatic_promotion"] = True
    _save(root, "model_catalog.yaml", models)

    failures, warnings = validate_optimization_contracts(root)
    joined = "\n".join(failures)
    assert warnings == ()
    assert joined.count("doit rester loopback") == 3
    assert joined.count("doit être Linux-native") == 3
    assert "promotion backend automatique interdite" in joined
    assert "fallback cloud interdit" in joined
    assert "kernel_policy candidate divergent" in joined
    assert "promotion kernel automatique interdite" in joined
    assert "seuil agrégé kernel divergent" in joined
    assert "seuil régression kernel divergent" in joined
    assert "promotion automatique challenger interdite" in joined
