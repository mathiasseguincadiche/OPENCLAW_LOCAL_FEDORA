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


def test_repository_has_no_non_linux_entrypoint_files() -> None:
    forbidden_suffixes = {".ps1", ".cmd", ".bat"}
    offenders = [
        path.relative_to(ROOT)
        for path in ROOT.rglob("*")
        if path.is_file() and path.suffix.lower() in forbidden_suffixes
    ]
    assert not offenders, offenders


def test_bootstrap_is_dry_run_by_default_and_does_not_weaken_security() -> None:
    text = _read("scripts/linux/00_bootstrap.sh")
    assert "APPLY=0" in text
    assert "--apply" in text
    assert "getenforce" in text
    lower_text = text.lower()
    forbidden = (
        "setenforce 0",
        "selinux=0",
        "--nogpgcheck",
        "chmod 777",
        "firewall-cmd --permanent --disable",
    )
    for marker in forbidden:
        assert marker.lower() not in lower_text, f"marqueur interdit présent: {marker}"


def test_bootstrap_targets_calling_user_even_when_elevated() -> None:
    text = _read("scripts/linux/00_bootstrap.sh")
    assert "SUDO_USER" in text
    assert 'TARGET_USER="${SUDO_USER:-${USER:-}}"' in text
    assert 'usermod -aG "$group" "$TARGET_USER"' in text
    assert 'enable-linger "$TARGET_USER"' in text
    assert 'as_target "$VENV/bin/python"' in text


def test_upstream_kernel_is_not_installed_by_bootstrap() -> None:
    text = _read("scripts/linux/00_bootstrap.sh")
    assert "7.2.3 is NOT installed here" in text
    assert "kernel.org" not in text


def test_gpu_stack_is_vulkan_only() -> None:
    bootstrap = _read("scripts/linux/00_bootstrap.sh")
    gpu_gate = _read("scripts/linux/02_verify_gpu.sh")
    assert "mesa-vulkan-drivers" in bootstrap
    assert "vulkaninfo" in gpu_gate


def test_runtime_python_fails_with_explicit_message_when_missing() -> None:
    text = _read("scripts/linux/lib/runtime.sh")
    assert "aucun Python géré ni python3 système disponible" in text
    assert "return 127" in text


def test_menu_exposes_only_implemented_foundation_actions() -> None:
    text = _read("menu.sh")
    for action in ("status", "validate", "bootstrap", "audit", "audit-strict", "gpu"):
        assert action in text
    assert "qualification)" not in text
    assert "golden)" not in text
