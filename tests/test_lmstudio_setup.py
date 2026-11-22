from __future__ import annotations

from pathlib import Path

import pytest

from clawfedora.lmstudio_bridge import PORT, read_token
from clawfedora.lmstudio_setup import render

ROOT = Path(__file__).resolve().parents[1]


def _runtime(tmp_path: Path) -> Path:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / ".openclaw-fedora-runtime").touch()
    python = runtime / "runtime/venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text("#!/usr/bin/python3\n", encoding="utf-8")
    return runtime


def test_independent_bridge_uses_private_stable_token_without_webui(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    units = tmp_path / "units"
    info = render(ROOT, runtime, units)
    token_file = runtime / "state/lmstudio/bridge.token"
    token = read_token(runtime)
    assert len(token) == 64
    assert token_file.stat().st_mode & 0o077 == 0
    assert info["address"] == "http://127.0.0.1:18894"
    assert PORT == 18894
    unit = (units / "clawfedora-lmstudio-bridge.service").read_text()
    assert "clawfedora.lmstudio_bridge" in unit
    assert "18891" not in unit
    assert "clawfedora-webui.service" not in unit
    assert "podman" not in unit
    assert "NoNewPrivileges=true" in unit
    assert "UMask=0077" in unit
    assert "Environment=OPENCLAW_LOCAL_FEDORA_ROOT=" in unit
    assert not (runtime / "state/webui").exists()
    assert render(ROOT, runtime, units) == info
    assert read_token(runtime) == token


def test_bad_permissions_symlinks_and_foreign_unit_fail_closed(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    units = tmp_path / "units"
    render(ROOT, runtime, units)
    token = runtime / "state/lmstudio/bridge.token"
    token.chmod(0o644)
    with pytest.raises(PermissionError, match="0600"):
        read_token(runtime)
    token.chmod(0o600)
    old = token.read_bytes()
    token.unlink()
    external = tmp_path / "external-secret"
    external.write_bytes(old)
    token.symlink_to(external)
    with pytest.raises(PermissionError, match="lié"):
        read_token(runtime)
    with pytest.raises(ValueError, match="lien symbolique"):
        render(ROOT, runtime, units)
    token.unlink()
    token.write_bytes(old)
    token.chmod(0o600)
    unit = units / "clawfedora-lmstudio-bridge.service"
    unit.write_text("[Unit]\nDescription=foreign service\n")
    with pytest.raises(ValueError, match="non gérée"):
        render(ROOT, runtime, units)


def test_uninstall_stops_the_independent_bridge() -> None:
    uninstall = (
        ROOT / "scripts/linux/10_uninstall.sh"
    ).read_text(encoding="utf-8")
    assert "for unit in clawfedora-lmstudio-bridge.service " in uninstall
    assert "systemctl --user disable --now" in uninstall
    assert "systemctl --user is-active --quiet" in uninstall


def test_parent_state_symlink_is_rejected_before_creating_secret(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (runtime / "state").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="État ClawFedora lié"):
        render(ROOT, runtime, tmp_path / "units")
    assert not (outside / "lmstudio").exists()


def test_missing_runtime_or_managed_venv_is_not_created(tmp_path: Path) -> None:
    runtime = tmp_path / "missing"
    runtime.mkdir()
    with pytest.raises(ValueError, match="non initialisé"):
        render(ROOT, runtime, tmp_path / "units")
    (runtime / ".openclaw-fedora-runtime").touch()
    with pytest.raises(ValueError, match="Python"):
        render(ROOT, runtime, tmp_path / "units")
