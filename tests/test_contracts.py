from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from clawfedora.contracts import validate_repository

ROOT = Path(__file__).resolve().parents[1]


def _sandbox(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir()
    shutil.copy(ROOT / "VERSION", tmp_path / "VERSION")
    for source in (ROOT / "config").glob("*.yaml"):
        shutil.copy(source, tmp_path / "config" / source.name)
    return tmp_path


def test_repository_contracts_pass() -> None:
    report = validate_repository(ROOT)
    assert report.ok, report.failures
    assert report.warnings


def test_windows_native_marker_is_rejected(tmp_path: Path) -> None:
    root = _sandbox(tmp_path)
    path = root / "config" / "platform.yaml"
    path.write_text(path.read_text(encoding="utf-8") + "\nlegacy: windows-native\n", encoding="utf-8")
    report = validate_repository(root)
    assert not report.ok
    assert any("Windows" in failure for failure in report.failures)


def test_kernel_automatic_promotion_is_rejected(tmp_path: Path) -> None:
    root = _sandbox(tmp_path)
    path = root / "config" / "kernel_policy.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["candidate"]["automatic_promotion"] = True
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    report = validate_repository(root)
    assert not report.ok
    assert any("promotion automatique" in failure for failure in report.failures)


def test_cloud_during_qualification_is_rejected(tmp_path: Path) -> None:
    root = _sandbox(tmp_path)
    path = root / "config" / "qualification_policy.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["safety"]["cloud_calls_allowed"] = True
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    report = validate_repository(root)
    assert not report.ok
    assert any("appel cloud" in failure for failure in report.failures)


def test_hard_40m_budget_cannot_be_silently_extended(tmp_path: Path) -> None:
    root = _sandbox(tmp_path)
    path = root / "config" / "qualification_policy.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["full_gate"]["max_wall_seconds"] = 3600
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    report = validate_repository(root)
    assert not report.ok
    assert any("2400" in failure for failure in report.failures)
