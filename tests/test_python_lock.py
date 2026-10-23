"""Production Python versions are pinned and drift cannot pass unnoticed."""

from __future__ import annotations

import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
lock = SimpleNamespace(**runpy.run_path(str(ROOT / "scripts/validation/check_python_lock.py")))


def test_repository_python_constraints_are_exact_and_cover_direct_packages() -> None:
    entries = lock.constraints(ROOT / "config/python-runtime-constraints.txt")
    assert len(entries) >= 20
    assert entries["pillow"] == "13.0.0"
    assert entries["pyyaml"] == "6.0.3"
    assert entries["pypdf"] == "6.21.2"
    assert lock.verify(ROOT)["verdict"] == "PYTHON_RUNTIME_CONSTRAINTS_PASS"


@pytest.mark.parametrize("bad", ["PyYAML>=6", "PyYAML==6\npyyaml==7", ""])
def test_unlocked_invalid_or_empty_constraints_are_rejected(
    tmp_path: Path, bad: str,
) -> None:
    file = tmp_path / "constraints.txt"
    file.write_text(bad, encoding="utf-8")
    with pytest.raises(ValueError):
        lock.constraints(file)


def test_runtime_drift_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    real = lock.metadata.distributions

    class Package:
        metadata = {"Name": "PyYAML"}
        version = "9.9.9"

    def with_drift() -> object:
        return [*(d for d in real() if d.metadata.get("Name", "").lower() != "pyyaml"),
                Package()]

    monkeypatch.setattr(lock.metadata, "distributions", with_drift)
    with pytest.raises(ValueError, match="versions="):
        lock.verify(ROOT)


def test_constraint_file_rejects_links(tmp_path: Path) -> None:
    real = tmp_path / "real.txt"
    real.write_text("pillow==13.0.0", encoding="utf-8")
    alias = tmp_path / "alias.txt"
    alias.symlink_to(real)
    with pytest.raises(ValueError, match="lié"):
        lock.constraints(alias)


def test_ci_unlocked_python_installs_are_prevented() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    constraints = "--constraint config/python-runtime-constraints.txt"
    assert workflow.count(f'run: python -m pip install {constraints} -e ".[dev]"') == 2
    assert f"run: python -m pip install {constraints} -e .\n" in workflow
    assert 'run: python -m pip install -e ".[dev]"' not in workflow
    assert "run: python -m pip install -e .\n" not in workflow
