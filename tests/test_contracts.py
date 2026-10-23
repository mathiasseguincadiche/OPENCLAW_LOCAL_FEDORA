from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from clawfedora.contracts import validate_repository

ROOT = Path(__file__).resolve().parents[1]


def _sandbox(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir()
    shutil.copy(ROOT / "VERSION", tmp_path / "VERSION")
    for source in (ROOT / "config").glob("*.yaml"):
        shutil.copy(source, tmp_path / "config" / source.name)
    shutil.copy(ROOT / "config/storage.json", tmp_path / "config/storage.json")
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


@pytest.mark.parametrize(
    ("key", "value", "error"),
    [
        ("release", 44, "Fedora Linux 45 requis"),
        ("desktop_major", 50, "GNOME 51 requis"),
    ],
)
def test_old_platform_versions_are_rejected(
    tmp_path: Path, key: str, value: int, error: str,
) -> None:
    root = _sandbox(tmp_path)
    config = root / "config/platform.yaml"
    payload = yaml.safe_load(config.read_text(encoding="utf-8"))
    payload["os"][key] = value
    config.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    report = validate_repository(root)
    assert not report.ok
    assert any(error in failure for failure in report.failures)
