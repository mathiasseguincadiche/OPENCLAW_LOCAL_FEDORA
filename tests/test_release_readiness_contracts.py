from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from clawfedora.release_readiness_contracts import validate_release_readiness_contracts

ROOT = Path(__file__).resolve().parents[1]


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    shutil.copytree(ROOT / "config", root / "config")
    return root


def _load(path: Path) -> dict[str, object]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _save(path: Path, value: dict[str, object]) -> None:
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")


def test_repository_release_readiness_contract_passes() -> None:
    failures, warnings = validate_release_readiness_contracts(ROOT)
    assert failures == ()
    assert any("preuves réelles" in warning for warning in warnings)
    assert any("aucune approbation" in warning for warning in warnings)


def test_l8_rejects_automatic_human_approval(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    path = root / "config/release_readiness.yaml"
    payload = _load(path)
    policy = payload["policy"]
    assert isinstance(policy, dict)
    policy["automatic_human_approval"] = True
    _save(path, payload)
    failures, _ = validate_release_readiness_contracts(root)
    assert any("automatic_human_approval" in failure for failure in failures)


def test_l8_rejects_missing_mandatory_ministral_decision(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    path = root / "config/release_readiness.yaml"
    payload = _load(path)
    evidence = payload["evidence"]
    assert isinstance(evidence, dict)
    l6 = evidence["l6"]
    assert isinstance(l6, dict)
    decisions = l6["required_decisions"]
    assert isinstance(decisions, list)
    l6["required_decisions"] = [
        item
        for item in decisions
        if not (isinstance(item, dict) and item.get("kind") == "model-challenger")
    ]
    _save(path, payload)
    failures, _ = validate_release_readiness_contracts(root)
    assert any("trois décisions L6 obligatoires" in failure for failure in failures)


def test_l8_rejects_challenger_counting_as_fourth_nominal_model(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    path = root / "config/model_catalog.yaml"
    payload = _load(path)
    fleet = payload["fleet_policy"]
    assert isinstance(fleet, dict)
    fleet["challenger_counts_toward_required_fleet"] = True
    _save(path, payload)
    failures, _ = validate_release_readiness_contracts(root)
    assert any("challenger ne doit pas compter" in failure for failure in failures)


def test_l8_rejects_lowered_hard40_wall_limit(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    path = root / "config/qualification_policy.yaml"
    payload = _load(path)
    full = payload["full_gate"]
    assert isinstance(full, dict)
    full["max_wall_seconds"] = 1800
    _save(path, payload)
    failures, _ = validate_release_readiness_contracts(root)
    assert any("2400" in failure for failure in failures)
