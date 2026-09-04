from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from clawfedora import optimization_cli

ROOT = Path(__file__).resolve().parents[1]


def test_provision_challenger_dry_run_stays_off_routing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        optimization_cli,
        "provision_challenger_plan",
        lambda _root: {
            "runtime_id": "ministral-3:14b-instruct-2512-q4_K_M",
            "routed": False,
        },
    )
    code = optimization_cli.main(
        [
            "--root",
            str(ROOT),
            "--runtime-root",
            str(tmp_path),
            "provision-challenger",
        ]
    )
    assert code == 0
    output = capsys.readouterr().out
    assert '"routed": false' in output
    assert "apply=false routed=false" in output


def test_provision_challenger_apply_is_explicit_ollama_pull(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    model = "ministral-3:14b-instruct-2512-q4_K_M"
    monkeypatch.setattr(
        optimization_cli,
        "provision_challenger_plan",
        lambda _root: {"runtime_id": model, "routed": False},
    )
    commands: list[list[str]] = []

    def run(command: list[str], *, check: bool) -> SimpleNamespace:
        assert check is False
        commands.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(optimization_cli.subprocess, "run", run)
    code = optimization_cli.main(
        [
            "--root",
            str(ROOT),
            "--runtime-root",
            str(tmp_path),
            "provision-challenger",
            "--apply",
        ]
    )
    assert code == 0
    assert commands == [["ollama", "pull", model]]
    assert "apply=true routed=false" in capsys.readouterr().out


def test_provision_challenger_failed_pull_is_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        optimization_cli,
        "provision_challenger_plan",
        lambda _root: {"runtime_id": "ministral", "routed": False},
    )
    monkeypatch.setattr(
        optimization_cli.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1),
    )
    assert (
        optimization_cli.main(
            [
                "--root",
                str(ROOT),
                "--runtime-root",
                str(tmp_path),
                "provision-challenger",
                "--apply",
            ]
        )
        == 2
    )


def test_snapshot_challenger_dispatches_variant(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    evidence = tmp_path / "ministral.json"
    observed: dict[str, object] = {}

    def snapshot(
        _root: Path,
        *,
        variant: str,
        endpoint: str,
        output: Path,
    ) -> Path:
        observed.update(variant=variant, endpoint=endpoint, output=output)
        return evidence

    monkeypatch.setattr(optimization_cli, "run_challenger_snapshot", snapshot)
    code = optimization_cli.main(
        [
            "--root",
            str(ROOT),
            "--runtime-root",
            str(tmp_path),
            "snapshot-challenger",
            "--variant",
            "challenger",
            "--output",
            str(evidence),
        ]
    )
    assert code == 0
    assert observed == {
        "variant": "challenger",
        "endpoint": "http://127.0.0.1:11434",
        "output": evidence.resolve(),
    }
    assert "L6_CHALLENGER_SNAPSHOT_RESULT=PASS" in capsys.readouterr().out
