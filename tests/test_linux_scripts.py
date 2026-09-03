from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_shell_entrypoints_are_strict() -> None:
    for path in (
        "menu.sh",
        "scripts/linux/00_bootstrap.sh",
        "scripts/linux/01_audit_host.sh",
        "scripts/linux/02_verify_gpu.sh",
        "scripts/linux/lib/runtime.sh",
    ):
        text = _read(path)
        assert "set -Eeuo pipefail" in text, path
        assert "powershell" not in text.lower(), path
        assert "pwsh" not in text.lower(), path


def test_bootstrap_is_dry_run_by_default_and_does_not_weaken_security() -> None:
    text = _read("scripts/linux/00_bootstrap.sh")
    assert "APPLY=0" in text
    assert "--apply" in text
    assert "getenforce" in text
    forbidden = (
        "setenforce 0",
        "selinux=0",
        "--nogpgcheck",
        "chmod 777",
        "firewall-cmd --permanent --disable",
    )
    lower_text = text.lower()
    for marker in forbidden:
        assert marker.lower() not in lower_text, f"marqueur sécurité interdit: {marker}"


def test_bootstrap_preserves_invoking_user_under_sudo() -> None:
    text = _read("scripts/linux/00_bootstrap.sh")
    assert "SUDO_USER" in text
    assert "TARGET_USER" in text
    assert 'TARGET_USER" == "root"' in text
    assert 'usermod -aG "$group" "$TARGET_USER"' in text
    assert 'loginctl enable-linger "$TARGET_USER"' in text
    assert 'as_target "$VENV/bin/python"' in text


def test_runtime_reports_missing_python_explicitly() -> None:
    text = _read("scripts/linux/lib/runtime.sh")
    assert "aucun Python géré ni python3 système disponible" in text
    assert "return 127" in text


def test_upstream_kernel_is_not_installed_by_bootstrap() -> None:
    text = _read("scripts/linux/00_bootstrap.sh")
    assert "7.2.3 is NOT installed here" in text
    assert "kernel.org" not in text


def test_menu_exposes_only_implemented_foundation_actions() -> None:
    text = _read("menu.sh")
    for action in ("status", "validate", "bootstrap", "audit", "audit-strict", "gpu"):
        assert action in text
    assert "qualification)" not in text
    assert "golden)" not in text
