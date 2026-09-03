from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from clawfedora.lifecycle_contracts import validate_lifecycle_contracts

ROOT = Path(__file__).resolve().parents[1]


def _sandbox(tmp_path: Path) -> Path:
    (tmp_path / "config/core").mkdir(parents=True)
    for relative in (
        "config/lifecycle_policy.yaml",
        "config/core/telemetry_policy.yaml",
        "config/core/budget_policy.yaml",
    ):
        target = tmp_path / relative
        shutil.copy(ROOT / relative, target)
    return tmp_path


def test_lifecycle_contract_passes() -> None:
    failures, warnings = validate_lifecycle_contracts(ROOT)
    assert failures == ()
    assert warnings


def test_lifecycle_rejects_dangerous_uninstall(tmp_path: Path) -> None:
    root = _sandbox(tmp_path)
    path = root / "config/lifecycle_policy.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["uninstall"]["preserve_projects"] = False
    payload["uninstall"]["purge_data_requires_explicit_flag"] = False
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    failures, _ = validate_lifecycle_contracts(root)
    joined = "\n".join(failures)
    assert "preserve_projects" in joined
    assert "purge explicite" in joined


def test_lifecycle_rejects_implicit_models_and_non_loopback_gateway(tmp_path: Path) -> None:
    root = _sandbox(tmp_path)
    path = root / "config/lifecycle_policy.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["installation"]["implicit_model_downloads"] = True
    payload["service"]["bind"] = "0.0.0.0"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    failures, _ = validate_lifecycle_contracts(root)
    joined = "\n".join(failures)
    assert "téléchargements implicites" in joined
    assert "Gateway loopback" in joined


def test_lifecycle_rejects_unsafe_restore_and_remote_telemetry(tmp_path: Path) -> None:
    root = _sandbox(tmp_path)
    path = root / "config/lifecycle_policy.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["backup"]["restore_overwrite_allowed"] = True
    payload["telemetry"]["local_only"] = False
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    failures, _ = validate_lifecycle_contracts(root)
    joined = "\n".join(failures)
    assert "écrasement interdite" in joined
    assert "télémétrie locale" in joined


def test_lifecycle_rejects_telemetry_and_finops_contract_drift(tmp_path: Path) -> None:
    root = _sandbox(tmp_path)
    telemetry_path = root / "config/core/telemetry_policy.yaml"
    telemetry = yaml.safe_load(telemetry_path.read_text(encoding="utf-8"))
    telemetry["retention"]["relative_path"] = "state/telemetry/drift.jsonl"
    telemetry_path.write_text(yaml.safe_dump(telemetry, sort_keys=False), encoding="utf-8")

    budget_path = root / "config/core/budget_policy.yaml"
    budget = yaml.safe_load(budget_path.read_text(encoding="utf-8"))
    budget["ledger"]["relative_path"] = "state/finops/drift.jsonl"
    budget["behavior"]["default_reservation_eur"] = 0.5
    budget_path.write_text(yaml.safe_dump(budget, sort_keys=False), encoding="utf-8")

    failures, _ = validate_lifecycle_contracts(root)
    joined = "\n".join(failures)
    assert "telemetry.event_file" in joined
    assert "finops.ledger_file" in joined
    assert "default_reservation_eur" in joined
