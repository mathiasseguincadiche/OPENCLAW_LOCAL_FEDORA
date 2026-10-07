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


def test_models_dry_run_lists_the_single_daily_model(capsys: pytest.CaptureFixture[str]) -> None:
    code = ops_cli.main(["--root", str(ROOT), "models"])
    assert code == 0
    output = capsys.readouterr().out
    assert '"verdict": "PLAN"' in output
    assert "qwen3.5:9b-q4_K_M" in output
    assert output.count("runtime_id") == 1


def test_cleanup_dry_run_never_deletes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    project = tmp_path / "projects/p"
    project.mkdir(parents=True)
    code = ops_cli.main(["--root", str(ROOT), "--runtime-root", str(tmp_path), "cleanup"])
    assert code == 0
    assert project.exists()
    assert "CLEANUP_PLAN=" in capsys.readouterr().out
