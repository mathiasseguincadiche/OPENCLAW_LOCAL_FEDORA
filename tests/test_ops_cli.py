from __future__ import annotations

from pathlib import Path

import pytest

from clawfedora import ops_cli

ROOT = Path(__file__).resolve().parents[1]


def test_validate_lifecycle_command(capsys: pytest.CaptureFixture[str]) -> None:
    code = ops_cli.main(["--root", str(ROOT), "validate-lifecycle"])
    assert code == 0
    assert "LIFECYCLE_CONTRACT_RESULT=PASS" in capsys.readouterr().out


def test_root_uses_repository_environment_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENCLAW_LOCAL_FEDORA_REPO", str(ROOT))
    assert ops_cli._root(None) == ROOT.resolve()


def test_explicit_root_wins_over_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("OPENCLAW_LOCAL_FEDORA_REPO", str(tmp_path / "wrong"))
    assert ops_cli._root(str(ROOT)) == ROOT.resolve()


def test_models_dry_run_lists_three_models(capsys: pytest.CaptureFixture[str]) -> None:
    code = ops_cli.main(["--root", str(ROOT), "models"])
    assert code == 0
    output = capsys.readouterr().out
    assert '"verdict": "PLAN"' in output
    assert "qwen3.5:9b-q4_K_M" in output
    assert "gemma3:12b-it-q4_K_M" in output
    assert "qwen2.5-coder:14b-instruct-q4_K_M" in output


def test_cleanup_dry_run_never_deletes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    project = tmp_path / "projects/p"
    project.mkdir(parents=True)
    code = ops_cli.main(
        ["--root", str(ROOT), "--runtime-root", str(tmp_path), "cleanup"]
    )
    assert code == 0
    assert project.exists()
    assert "CLEANUP_PLAN=" in capsys.readouterr().out


def test_telemetry_cli_roundtrip(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = ops_cli.main(
        [
            "--root",
            str(ROOT),
            "--runtime-root",
            str(tmp_path),
            "telemetry",
            "--event",
            "project.status",
            "--project-id",
            "p1",
            "--status",
            "PASS",
        ]
    )
    assert code == 0
    assert "TELEMETRY_RESULT=PASS" in capsys.readouterr().out
    code = ops_cli.main(
        ["--root", str(ROOT), "--runtime-root", str(tmp_path), "telemetry", "--show"]
    )
    assert code == 0
    assert '"event": "project.status"' in capsys.readouterr().out


def test_finops_cli_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = ops_cli.main(
        [
            "--root",
            str(ROOT),
            "--runtime-root",
            str(tmp_path),
            "finops",
            "--event",
            "reservation",
            "--amount-eur",
            "0.25",
            "--reason",
            "explicit",
            "--provider",
            "example",
        ]
    )
    assert code == 0
    capsys.readouterr()
    code = ops_cli.main(
        ["--root", str(ROOT), "--runtime-root", str(tmp_path), "finops", "--show"]
    )
    assert code == 0
    assert '"reservations_eur": 0.25' in capsys.readouterr().out
