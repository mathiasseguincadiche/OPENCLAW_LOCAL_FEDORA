"""Standalone native Atelier service has no Open WebUI/LM Studio runtime dependency."""
from __future__ import annotations

from pathlib import Path

import pytest

from clawfedora.atelier_setup import render

ROOT = Path(__file__).resolve().parents[1]


def test_standalone_user_unit_preserves_mount_and_does_not_start_webui(
    tmp_path: Path,
) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / ".openclaw-fedora-runtime").touch()
    python = runtime / "runtime/venv/bin/python"
    python.parent.mkdir(parents=True)
    python.touch()
    unit = render(ROOT, runtime, tmp_path / "user")
    content = unit.read_text()
    assert unit.name == "clawfedora-dashboard.service"
    assert "clawfedora.cli" in content
    assert "After=openclaw-gateway.service" in content
    assert "RequiresMountsFor=" in content
    assert "ExecStartPre=" in content
    assert "open-webui" not in content.lower()
    assert "podman" not in content.lower()
    assert unit.stat().st_mode & 0o077 == 0
    assert render(ROOT, runtime, tmp_path / "user") == unit
    unit.write_text("[Service]\nExecStart=/bin/false\n")
    with pytest.raises(ValueError, match="non gérée"):
        render(ROOT, runtime, tmp_path / "user")


def test_standalone_unit_does_not_accept_symlink_runtime(
    tmp_path: Path,
) -> None:
    actual = tmp_path / "actual"
    actual.mkdir()
    (tmp_path / "runtime").symlink_to(actual, target_is_directory=True)
    with pytest.raises(ValueError, match="symboliques"):
        render(ROOT, tmp_path / "runtime", tmp_path / "user")
