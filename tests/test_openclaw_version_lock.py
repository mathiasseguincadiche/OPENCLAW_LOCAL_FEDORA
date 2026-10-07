from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from clawfedora.core_contracts import validate_core_contracts
from clawfedora.version_lock import extract_openclaw_version

ROOT = Path(__file__).resolve().parents[1]


def test_openclaw_version_is_written_once_and_locked_exactly() -> None:
    versions = yaml.safe_load((ROOT / "config/runtime_versions.yaml").read_text(encoding="utf-8"))
    policy = yaml.safe_load((ROOT / "config/core/openclaw_policy.yaml").read_text(encoding="utf-8"))

    openclaw = versions["openclaw"]
    locked = openclaw["version"]
    assert openclaw["lock"] == "exact"
    assert openclaw["automatic_update"] is False

    assert policy["runtime"]["required_version"] == locked
    assert policy["runtime"]["version_lock"] == "exact"
    assert policy["runtime"]["automatic_update_allowed"] is False

    parallel = openclaw["plugins"]["parallel"]
    parallel_policy = policy["plugins"]["parallel_search"]
    assert parallel["version"] == locked
    assert parallel["lock"] == "exact"
    assert parallel_policy["version"] == locked
    assert parallel_policy["version_lock"] == "exact"
    assert parallel_policy["automatic_update_allowed"] is False

    upgrade = versions["upgrade_policy"]
    assert upgrade["openclaw_version_locked"] is True
    assert upgrade["openclaw_update_requires_explicit_contract_change"] is True
    assert upgrade["parallel_plugin_version_locked"] is True
    assert upgrade["automatic_runtime_upgrade"] is False

    failures, _warnings = validate_core_contracts(ROOT)
    assert failures == ()


def test_python_parser_does_not_confuse_neighbor_versions() -> None:
    assert extract_openclaw_version("OpenClaw 2026.9.8") == "2026.9.8"
    assert extract_openclaw_version("OpenClaw 2026.9.80") == "2026.9.80"
    assert extract_openclaw_version("OpenClaw 2026.9.80") != "2026.9.8"

    with pytest.raises(ValueError, match="absente ou ambiguë"):
        extract_openclaw_version("OpenClaw version inconnue")
    with pytest.raises(ValueError, match="absente ou ambiguë"):
        extract_openclaw_version("OpenClaw 2026.9.8 puis 2026.9.80")


def test_shell_parser_extracts_the_whole_version_token() -> None:
    helper = ROOT / "scripts/linux/lib/runtime.sh"
    completed = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; claw_extract_openclaw_version "$2"',
            "bash",
            str(helper),
            "OpenClaw 2026.9.80",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert completed.stdout.strip() == "2026.9.80"
    assert completed.stdout.strip() != "2026.9.8"


def test_install_and_config_scripts_use_exact_openclaw_equality() -> None:
    install = (ROOT / "scripts/linux/06_install.sh").read_text(encoding="utf-8")
    configure = (ROOT / "scripts/linux/03_configure_openclaw.sh").read_text(encoding="utf-8")

    assert 'OPENCLAW_PIN="$(claw_pin openclaw version)"' in install
    assert '--install-method npm --version "$OPENCLAW_PIN"' in install
    assert '[[ "$OPENCLAW_VERSION" == "$OPENCLAW_PIN" ]]' in install
    assert '[[ "$OPENCLAW_VERSION" == *"$OPENCLAW_PIN"* ]]' not in install

    assert 'OPENCLAW_PIN="$(claw_pin openclaw version)"' in configure
    assert '[[ "$OPENCLAW_VERSION" == "$OPENCLAW_PIN" ]]' in configure
    assert '[[ "$OPENCLAW_VERSION" == *"$OPENCLAW_PIN"* ]]' not in configure
