from __future__ import annotations

import json
from pathlib import Path

import pytest

from clawfedora import golden_cli

ROOT = Path(__file__).resolve().parents[1]


def test_root_resolution_explicit_env_and_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert golden_cli._root(str(tmp_path)) == tmp_path.resolve()
    monkeypatch.setenv("OPENCLAW_LOCAL_FEDORA_REPO", str(tmp_path / "repo"))
    assert golden_cli._root(None) == (tmp_path / "repo").resolve()
    monkeypatch.delenv("OPENCLAW_LOCAL_FEDORA_REPO")
    assert golden_cli._root(None) == ROOT


def test_dry_run_text_and_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload = {
        "project_count": 6,
        "task_count": 17,
        "verdict": "READY",
    }
    monkeypatch.setattr(golden_cli, "dry_run", lambda _root: payload)
    assert golden_cli.main(["--root", str(ROOT), "--dry-run"]) == 0
    output = capsys.readouterr().out
    assert "L7_DRY_RUN=PASS projects=6 tasks=17" in output
    assert "cloud=false" in output
    assert "human_completion=false" in output

    assert golden_cli.main(["--root", str(ROOT), "--dry-run", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["verdict"] == "READY"


def test_full_run_text_and_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report_path = tmp_path / "L7_REPORT.json"
    report = {
        "verdict": "PASS",
        "golden_projects_pass": 5,
        "representative_projects_pass": 1,
        "telemetry": {"events": 6},
        "finops": {"net_exposure_eur": 0.0},
    }
    report_path.write_text(json.dumps(report), encoding="utf-8")
    monkeypatch.setattr(golden_cli, "resolve_runtime_root", lambda _value: tmp_path)
    monkeypatch.setattr(
        golden_cli,
        "run_golden_suite",
        lambda _repo, _runtime: (0, report_path),
    )

    assert golden_cli.main(["--root", str(ROOT), "--runtime-root", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert f"L7_REPORT={report_path}" in output
    assert "L7_RESULT=PASS golden=5/5 representative=1/1" in output
    assert "finops_exposure_eur=0.0" in output

    assert golden_cli.main(
        ["--root", str(ROOT), "--runtime-root", str(tmp_path), "--json"]
    ) == 0
    assert json.loads(capsys.readouterr().out)["verdict"] == "PASS"


def test_cli_reports_failures_in_text_and_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        golden_cli,
        "dry_run",
        lambda _root: (_ for _ in ()).throw(ValueError("invalid L7 contract")),
    )
    assert golden_cli.main(["--root", str(ROOT), "--dry-run"]) == 2
    assert "L7_RESULT=FAIL error=invalid L7 contract" in capsys.readouterr().out

    assert golden_cli.main(["--root", str(ROOT), "--dry-run", "--json"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"verdict": "FAIL", "error": "invalid L7 contract"}
