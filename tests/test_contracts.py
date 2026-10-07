from __future__ import annotations

import shutil
from pathlib import Path

import pytest

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
    assert not (ROOT / "config/kernel_policy.yaml").exists()


def test_missing_required_contract_is_rejected(tmp_path: Path) -> None:
    root = _sandbox(tmp_path)
    (root / "config" / "platform.yaml").unlink()
    report = validate_repository(root)
    assert not report.ok
    assert any("fichier requis absent" in failure for failure in report.failures)


def test_invalid_yaml_is_fail_closed(tmp_path: Path) -> None:
    root = _sandbox(tmp_path)
    path = root / "config" / "platform.yaml"
    path.write_text("platform: [broken\n", encoding="utf-8")
    with pytest.raises(ValueError, match="contrat illisible"):
        validate_repository(root)
