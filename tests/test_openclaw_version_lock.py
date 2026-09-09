from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from clawfedora import openclaw_e2e, release_readiness
from clawfedora.core_contracts import LOCKED_OPENCLAW_VERSION, validate_core_contracts
from clawfedora.version_lock import extract_openclaw_version

ROOT = Path(__file__).resolve().parents[1]


def test_openclaw_contract_is_exactly_locked_to_2026_9_2() -> None:
    versions = yaml.safe_load((ROOT / "config/runtime_versions.yaml").read_text(encoding="utf-8"))
    policy = yaml.safe_load(
        (ROOT / "config/core/openclaw_policy.yaml").read_text(encoding="utf-8")
    )

    openclaw = versions["openclaw"]
    assert LOCKED_OPENCLAW_VERSION == "2026.9.2"
    assert openclaw["version"] == LOCKED_OPENCLAW_VERSION
    assert openclaw["initial_qualification_pin"] == openclaw["version"]
    assert openclaw["lock"] == "exact"
    assert openclaw["automatic_update"] is False

    assert policy["runtime"]["required_version"] == LOCKED_OPENCLAW_VERSION
    assert policy["runtime"]["version_lock"] == "exact"
    assert policy["runtime"]["automatic_update_allowed"] is False

    parallel = openclaw["plugins"]["parallel"]
    parallel_policy = policy["plugins"]["parallel_search"]
    assert parallel["version"] == LOCKED_OPENCLAW_VERSION
    assert parallel["lock"] == "exact"
    assert parallel_policy["version"] == LOCKED_OPENCLAW_VERSION
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
    assert extract_openclaw_version("OpenClaw 2026.9.2") == "2026.9.2"
    assert extract_openclaw_version("OpenClaw 2026.9.20") == "2026.9.20"
    assert extract_openclaw_version("OpenClaw 2026.9.20") != LOCKED_OPENCLAW_VERSION

    with pytest.raises(ValueError, match="absente ou ambiguë"):
        extract_openclaw_version("OpenClaw version inconnue")
    with pytest.raises(ValueError, match="absente ou ambiguë"):
        extract_openclaw_version("OpenClaw 2026.9.2 puis 2026.9.20")


def test_shell_parser_extracts_the_whole_version_token() -> None:
    helper = ROOT / "scripts/linux/lib/runtime.sh"
    completed = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; claw_extract_openclaw_version "$2"',
            "bash",
            str(helper),
            "OpenClaw 2026.9.20",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert completed.stdout.strip() == "2026.9.20"
    assert completed.stdout.strip() != LOCKED_OPENCLAW_VERSION


def test_install_and_config_scripts_use_exact_openclaw_equality() -> None:
    install = (ROOT / "scripts/linux/10_install_full.sh").read_text(encoding="utf-8")
    configure = (ROOT / "scripts/linux/04_configure_openclaw.sh").read_text(encoding="utf-8")

    assert 'OPENCLAW_PIN="2026.9.2"' in install
    assert '--install-method npm --version "$OPENCLAW_PIN"' in install
    assert '[[ "$OPENCLAW_VERSION" == "$OPENCLAW_PIN" ]]' in install
    assert '[[ "$OPENCLAW_VERSION" == *"$OPENCLAW_PIN"* ]]' not in install

    assert 'OPENCLAW_PIN="2026.9.2"' in configure
    assert '[[ "$OPENCLAW_VERSION" == "$OPENCLAW_PIN" ]]' in configure
    assert '[[ "$OPENCLAW_VERSION" == *"$OPENCLAW_PIN"* ]]' not in configure


def test_l4_refuses_neighbor_openclaw_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(openclaw_e2e.shutil, "which", lambda _name: "/usr/bin/openclaw")
    monkeypatch.setattr(
        openclaw_e2e.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout="OpenClaw 2026.9.20\n",
            stderr="",
        ),
    )

    code, evidence = openclaw_e2e.run_e2e(
        ROOT,
        backend="ollama-vulkan",
        runtime_root=tmp_path,
    )
    assert (code, evidence) == (2, None)


def test_l8_refuses_neighbor_openclaw_version() -> None:
    cfg = {
        "required_verdict": "PASS",
        "required_backend": "ollama-vulkan",
        "required_agent_smokes": 8,
        "required_stability_runs": 3,
    }
    payload = {
        "schema_version": "1.0.0",
        "gate": "L4",
        "verdict": "PASS",
        "backend": "ollama-vulkan",
        "cloud_enabled": False,
        "transport": "gateway",
        "agent_smokes": [{"agent": agent} for agent in openclaw_e2e.AGENT_IDS],
        "tool_call": {},
        "repair": {},
        "stability": [{"run": index} for index in range(1, 4)],
        "openclaw_version": "2026.9.20",
    }

    failures = release_readiness._validate_l4(ROOT, payload, cfg)
    assert any("version OpenClaw" in failure for failure in failures)
