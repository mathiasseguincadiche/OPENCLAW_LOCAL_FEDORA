from __future__ import annotations

from pathlib import Path

import yaml

from clawfedora.qualification_contracts import validate_qualification_contracts

ROOT = Path(__file__).resolve().parents[1]


def test_qualification_contracts_pass_on_repository() -> None:
    failures, warnings = validate_qualification_contracts(ROOT)
    assert failures == ()
    assert warnings


def test_contract_rejects_weakened_hard40_threshold(tmp_path: Path) -> None:
    config = tmp_path / "config"
    suite_dir = tmp_path / "benchmarks" / "suites"
    config.mkdir(parents=True)
    suite_dir.mkdir(parents=True)
    for name in ("qualification_policy.yaml", "model_catalog.yaml"):
        (config / name).write_text(
            (ROOT / "config" / name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    (suite_dir / "linux_devops_v1.yaml").write_text(
        (ROOT / "benchmarks" / "suites" / "linux_devops_v1.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    policy_path = config / "qualification_policy.yaml"
    payload = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    payload["automated_gates"]["thresholds"]["min_check_pass_rate"] = 0.5
    policy_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    failures, _ = validate_qualification_contracts(tmp_path)
    assert any("min_check_pass_rate" in item for item in failures)


def test_contract_rejects_external_endpoint_policy_and_auto_promotion(tmp_path: Path) -> None:
    config = tmp_path / "config"
    suite_dir = tmp_path / "benchmarks" / "suites"
    config.mkdir(parents=True)
    suite_dir.mkdir(parents=True)
    for name in ("qualification_policy.yaml", "model_catalog.yaml"):
        (config / name).write_text(
            (ROOT / "config" / name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    (suite_dir / "linux_devops_v1.yaml").write_text(
        (ROOT / "benchmarks" / "suites" / "linux_devops_v1.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    policy_path = config / "qualification_policy.yaml"
    payload = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    payload["safety"]["endpoint_loopback_only"] = False
    payload["promotion"]["automatic_backend_promotion"] = True
    policy_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    failures, _ = validate_qualification_contracts(tmp_path)
    assert any("loopback-only" in item for item in failures)
    assert any("automatic_backend_promotion" in item for item in failures)
