from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_shell_entrypoints_are_strict() -> None:
    for path in (
        "menu.sh",
        "scripts/linux/00_bootstrap.sh",
        "scripts/linux/01_audit_host.sh",
        "scripts/linux/02_deploy_agents.sh",
        "scripts/linux/03_configure_openclaw.sh",
        "scripts/linux/04_check_hardware.sh",
        "scripts/linux/05_provision_models.sh",
        "scripts/linux/06_install.sh",
        "scripts/linux/07_health.sh",
        "scripts/linux/08_backup_restore.sh",
        "scripts/linux/09_repair.sh",
        "scripts/linux/10_uninstall.sh",
        "scripts/linux/11_daily_profile.sh",
        "scripts/linux/12_upgrade.sh",
        "scripts/linux/13_openwebui.sh",
        "scripts/linux/14_cloud.sh",
        "scripts/linux/lib/runtime.sh",
    ):
        text = _read(path)
        assert "set -Eeuo pipefail" in text, path


def test_bootstrap_is_dry_run_by_default_and_does_not_weaken_security() -> None:
    text = _read("scripts/linux/00_bootstrap.sh")
    assert "APPLY=0" in text
    assert "--apply" in text
    assert "getenforce" in text
    assert "firewalld" in text
    assert "policycoreutils-python-utils" in text
    assert '"$RUNTIME_ROOT/state"' in text
    assert '"$RUNTIME_ROOT/backups"' in text
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
    assert "never builds or installs one" in text
    assert not (ROOT / "scripts/linux/20_kernel_candidate.sh").exists()
    assert "kernel.org" not in text


def test_runtime_python_fails_with_explicit_message_when_missing() -> None:
    text = _read("scripts/linux/lib/runtime.sh")
    assert "aucun Python géré ni python3 système disponible" in text
    assert "return 127" in text


def test_openclaw_config_is_dry_run_by_default_and_fail_closed() -> None:
    text = _read("scripts/linux/03_configure_openclaw.sh")
    assert "APPLY=0" in text
    assert "DRY_RUN=PASS" in text
    assert 'OPENCLAW_PIN="$(claw_pin openclaw version)"' in text
    assert 'PARALLEL_PIN="$OPENCLAW_PIN"' in text
    assert "OpenClaw exactement $OPENCLAW_PIN requis" in text
    assert '[[ "$OPENCLAW_VERSION" == "$OPENCLAW_PIN" ]]' in text
    assert '[[ "$OPENCLAW_VERSION" == *"$OPENCLAW_PIN"* ]]' not in text
    assert "require_daily_model" in text
    assert "--backend" not in text
    assert "exactement un modèle quotidien" in text
    assert 'config patch --file "$PATCH_PATH" --dry-run' in text
    assert "config validate --json" in text
    assert "agents list --json" in text
    assert "plugins inspect parallel --runtime --json" in text
    assert "plugins update" in text


def test_openclaw_agent_inventory_accepts_supported_json_shapes() -> None:
    text = _read("scripts/linux/03_configure_openclaw.sh")
    assert 'type == "array" then length' in text
    assert '(.agents? | type) == "array"' in text
    assert '(.list? | type) == "array"' in text
    assert '[[ "$AGENT_COUNT" -eq 7 ]]' in text


def test_full_install_is_explicit_and_pinned() -> None:
    text = _read("scripts/linux/06_install.sh")
    assert "APPLY=0" in text
    assert 'OPENCLAW_PIN="$(claw_pin openclaw version)"' in text
    assert 'OLLAMA_PIN="$(claw_pin ollama version)"' in text
    assert 'OLLAMA_VERSION="$OLLAMA_PIN"' in text
    assert '--install-method npm --version "$OPENCLAW_PIN"' in text
    assert '[[ "$OPENCLAW_VERSION" == "$OPENCLAW_PIN" ]]' in text
    assert '[[ "$OPENCLAW_VERSION" == *"$OPENCLAW_PIN"* ]]' not in text
    assert "05_provision_models.sh" in text
    assert "03_configure_openclaw.sh" in text
    assert "openclaw gateway install" in text
    assert "systemctl --user enable --now openclaw-gateway.service" in text


def test_uninstall_preserves_data_without_explicit_purge() -> None:
    text = _read("scripts/linux/10_uninstall.sh")
    assert "APPLY=0" in text
    assert "PURGE=0" in text
    assert "--purge-data" in text
    assert "openclaw gateway uninstall" in text
    assert "cleanup --apply" in text


def test_repair_backups_before_reconfiguration() -> None:
    text = _read("scripts/linux/09_repair.sh")
    backup_index = text.index('"$LINUX/08_backup_restore.sh" backup')
    configure_index = text.index('"$LINUX/03_configure_openclaw.sh" --apply')
    assert backup_index < configure_index
    assert "gateway restart --preserve-definition" in text


def test_menu_exposes_daily_actions_and_no_retired_machinery() -> None:
    text = _read("menu.sh")
    for action in (
        "install",
        "health",
        "context-probe",
        "webui-install",
        "cloud-status",
        "cloud-set-key",
        "cloud-enable",
        "cloud-disable",
        "cloud-reconcile",
        "dashboard",
        "gaming",
        "daily",
        "backup",
        "upgrade",
        "repair",
        "uninstall",
        "status",
        "validate",
        "audit",
        "check-system",
        "check-gpu",
        "bootstrap",
        "models",
        "agents",
        "configure-openclaw",
    ):
        assert f"  {action})" in text or f"|{action}" in text or f"{action}|" in text, action
    for retired in ("qualification", "golden", "release-readiness", "llama", "kernel", "e2e"):
        assert retired not in text.casefold(), retired
    # Every script the menu calls exists.
    for name in set(re.findall(r"\b(\d\d_[a-z_]+\.sh)\b", text)):
        assert (ROOT / "scripts/linux" / name).is_file(), name


def test_installer_reads_exact_pins_without_third_party_python_packages() -> None:
    result = subprocess.run(
        [
            "bash",
            "-c",
            "source scripts/linux/lib/runtime.sh; claw_pin openclaw version; claw_pin ollama version",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    assert result.stdout.splitlines() == ["2026.9.8", "0.35.1"]


def test_openclaw_toolkit_inventory_matches_the_plugin() -> None:
    """The install check must expect exactly the tools the plugin registers."""
    source = _read("plugins/clawfedora-toolkit/index.mjs")
    plugin = set(re.findall(r'\["(clawfedora_[a-z_]+)"', source))
    script = _read("scripts/linux/03_configure_openclaw.sh")
    expected = re.search(r"\(\[(\"clawfedora_[^\]]+)\] \| sort\)", script)
    assert expected is not None
    declared = set(re.findall(r'"(clawfedora_[a-z_]+)"', expected.group(1)))
    assert len(plugin) == 8
    assert declared == plugin


def test_cloud_script_keeps_the_key_off_the_command_line_and_gates_the_service() -> None:
    text = _read("scripts/linux/14_cloud.sh")
    assert "read -r -s" in text and "| cloud set-key" in text
    assert "--key" not in text.replace("--key-limit-usd", "")
    enable = text[text.index("  enable)") : text.index("  disable)")]
    # The activation record is written first and the service only starts if it succeeded.
    assert enable.index('cloud "${args[@]}" --apply') < enable.index("systemctl --user enable")
    assert enable.index("systemctl --user enable") < enable.index("03_configure_openclaw.sh")
    assert "--confirm-prepaid" in enable and "oui" in enable
    disable = text[text.index("  disable)") :]
    assert disable.index("cloud disable") < disable.index("03_configure_openclaw.sh")


def test_cloud_menu_actions_validate_their_values_before_touching_anything() -> None:
    env = {**os.environ, "OPENCLAW_LOCAL_FEDORA_ROOT": "/nonexistent-runtime"}
    for action, extra in (
        ("cloud-reconcile", []),
        ("cloud-reconcile", ["--value", "abc"]),
        ("cloud-enable", []),
        ("cloud-enable", ["--value", "-3"]),
    ):
        result = subprocess.run(
            [str(ROOT / "menu.sh"), "--action", action, *extra],
            capture_output=True, text=True, env=env, timeout=60, check=False,
        )
        assert result.returncode == 2, (action, extra, result.stdout, result.stderr)
        assert "--value" in result.stderr
