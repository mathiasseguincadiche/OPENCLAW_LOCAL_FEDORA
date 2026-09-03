from __future__ import annotations

import json
from pathlib import Path

from clawfedora.cli import main

ROOT = Path(__file__).resolve().parents[1]


def test_validate_cli_passes() -> None:
    assert main(["--root", str(ROOT), "validate"]) == 0


def test_audit_non_strict_is_portable() -> None:
    assert main(["--root", str(ROOT), "audit", "--json"]) == 0


def test_qualification_dry_run_cli_passes() -> None:
    assert main(["--root", str(ROOT), "qualification", "--dry-run", "--json"]) == 0


def test_l4_dry_run_cli_passes() -> None:
    assert (
        main(
            [
                "--root",
                str(ROOT),
                "e2e",
                "--backend",
                "ollama-vulkan",
                "--dry-run",
                "--json",
            ]
        )
        == 0
    )


def test_agents_validate_cli_passes() -> None:
    assert main(["--root", str(ROOT), "agents", "validate", "--json"]) == 0


def test_agents_deploy_cli_uses_explicit_runtime(tmp_path: Path) -> None:
    assert (
        main(
            [
                "--root",
                str(ROOT),
                "agents",
                "deploy",
                "--runtime-root",
                str(tmp_path),
                "--json",
            ]
        )
        == 0
    )
    assert (tmp_path / "workspaces" / "chef-operations" / "AGENTS.md").is_file()


def test_openclaw_render_cli_writes_patch(tmp_path: Path) -> None:
    output = tmp_path / "openclaw.patch.json"
    assert (
        main(
            [
                "--root",
                str(ROOT),
                "openclaw",
                "render",
                "--runtime-root",
                str(tmp_path),
                "--backend",
                "ollama-vulkan",
                "--output",
                str(output),
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["gateway"]["bind"] == "loopback"
    assert len(payload["agents"]["list"]) == 8
