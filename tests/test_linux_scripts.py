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
        "scripts/linux/03_deploy_agents.sh",
        "scripts/linux/04_configure_openclaw.sh",
        "scripts/linux/lib/runtime.sh",
    ):
        text = _read(path)
        assert "set -Eeuo pipefail" in text, path


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


def test_baseline_gpu_stack_is_vulkan() -> None:
    bootstrap = _read("scripts/linux/00_bootstrap.sh")
    gpu_gate = _read("scripts/linux/02_verify_gpu.sh")
    assert "mesa-vulkan-drivers" in bootstrap
    assert "vulkaninfo" in gpu_gate


def test_runtime_python_fails_with_explicit_message_when_missing() -> None:
    text = _read("scripts/linux/lib/runtime.sh")
    assert "aucun Python géré ni python3 système disponible" in text
    assert "return 127" in text


def test_openclaw_config_is_dry_run_by_default_and_fail_closed() -> None:
    text = _read("scripts/linux/04_configure_openclaw.sh")
    assert "APPLY=0" in text
    assert "DRY_RUN=PASS" in text
    assert 'OPENCLAW_PIN="2026.7.1-2"' in text
    assert "OpenClaw $OPENCLAW_PIN requis" in text
    assert "require_backend_models" in text
    assert "exactement 3 modèles" in text
    assert "config patch --file \"$PATCH_PATH\" --dry-run" in text
    assert "config validate --json" in text
    assert "agents list --json" in text
    assert "plugins inspect parallel --runtime --json" in text


def test_openclaw_agent_inventory_accepts_supported_json_shapes() -> None:
    text = _read("scripts/linux/04_configure_openclaw.sh")
    assert 'type == "array" then length' in text
    assert '(.agents? | type) == "array"' in text
    assert '(.list? | type) == "array"' in text
    assert '[[ "$AGENT_COUNT" -eq 8 ]]' in text


def test_menu_exposes_only_implemented_actions() -> None:
    text = _read("menu.sh")
    for action in (
        "status",
        "validate",
        "bootstrap",
        "audit",
        "audit-strict",
        "gpu",
        "agents",
        "configure-openclaw",
    ):
        assert action in text
    assert "qualification)" not in text
    assert "golden)" not in text
