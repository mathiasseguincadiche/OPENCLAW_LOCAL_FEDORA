from __future__ import annotations

import json
from pathlib import Path

import pytest

from clawfedora import cli

ROOT = Path(__file__).resolve().parents[1]


def test_validate_cli_passes() -> None:
    assert cli.main(["--root", str(ROOT), "validate"]) == 0


def test_audit_non_strict_is_portable() -> None:
    assert cli.main(["--root", str(ROOT), "audit", "--json"]) == 0


def test_qualification_dry_run_cli_passes() -> None:
    assert cli.main(["--root", str(ROOT), "qualification", "--dry-run", "--json"]) == 0


def test_l4_dry_run_cli_passes() -> None:
    assert (
        cli.main(
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


def test_real_long_gates_refuse_without_sleep_inhibitor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(cli.SLEEP_INHIBIT_MARKER, raising=False)
    assert cli.main(["--root", str(ROOT), "qualification"]) == 2
    assert cli.main(["--root", str(ROOT), "e2e"]) == 2


def test_real_qualification_validates_contracts_before_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(cli.SLEEP_INHIBIT_MARKER, "1")
    monkeypatch.setattr(
        cli,
        "validate_qualification_contracts",
        lambda _root: (("suite hors contrat",), ()),
    )

    def forbidden_runner(*_args: object, **_kwargs: object) -> tuple[int, None]:
        pytest.fail("run_qualification ne doit pas démarrer avec un contrat invalide")

    monkeypatch.setattr(cli, "run_qualification", forbidden_runner)
    assert (
        cli.main(
            [
                "--root",
                str(ROOT),
                "qualification",
                "--runtime-root",
                str(tmp_path),
            ]
        )
        == 2
    )


def test_agents_validate_cli_passes() -> None:
    assert cli.main(["--root", str(ROOT), "agents", "validate", "--json"]) == 0


def test_agents_deploy_cli_uses_explicit_runtime(tmp_path: Path) -> None:
    assert (
        cli.main(
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
        cli.main(
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
