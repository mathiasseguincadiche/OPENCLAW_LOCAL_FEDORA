from __future__ import annotations

import json
from pathlib import Path

import pytest

from clawfedora import release_readiness_cli

ROOT = Path(__file__).resolve().parents[1]


def test_root_resolution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert release_readiness_cli._root(str(tmp_path)) == tmp_path.resolve()
    monkeypatch.setenv("OPENCLAW_LOCAL_FEDORA_REPO", str(tmp_path / "repo"))
    assert release_readiness_cli._root(None) == (tmp_path / "repo").resolve()
    monkeypatch.delenv("OPENCLAW_LOCAL_FEDORA_REPO")
    assert release_readiness_cli._root(None) == ROOT


def test_validate_text_and_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        release_readiness_cli,
        "validate_release_readiness_contracts",
        lambda _root: ((), ("warning",)),
    )
    code = release_readiness_cli.main(
        ["--root", str(ROOT), "--runtime-root", str(tmp_path), "validate"]
    )
    assert code == 0
    output = capsys.readouterr().out
    assert "WARN warning" in output
    assert "L8_CONTRACT_RESULT=PASS" in output

    monkeypatch.setattr(
        release_readiness_cli,
        "validate_release_readiness_contracts",
        lambda _root: (("failure",), ()),
    )
    code = release_readiness_cli.main(
        ["--root", str(ROOT), "--runtime-root", str(tmp_path), "validate", "--json"]
    )
    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["verdict"] == "FAIL"


def test_dry_run_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        release_readiness_cli,
        "dry_run",
        lambda _root: {
            "required_gates": ["L0", "L1"],
            "required_l6_decisions": [{"kind": "runtime"}],
        },
    )
    code = release_readiness_cli.main(
        ["--root", str(ROOT), "--runtime-root", str(tmp_path), "dry-run"]
    )
    assert code == 0
    assert "L8_DRY_RUN_RESULT=PASS" in capsys.readouterr().out


def test_check_cli_returns_runner_status_and_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = tmp_path / "proofs/l8/runs/run/RELEASE_READINESS_REPORT.json"
    report.parent.mkdir(parents=True)
    report.write_text(
        json.dumps({"verdict": "READY_FOR_HUMAN_REVIEW", "failures": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        release_readiness_cli,
        "write_readiness_report",
        lambda _repo, _runtime: (0, report),
    )
    code = release_readiness_cli.main(
        ["--root", str(ROOT), "--runtime-root", str(tmp_path), "check"]
    )
    assert code == 0
    output = capsys.readouterr().out
    assert f"REPORT={report}" in output
    assert "L8_READINESS=READY_FOR_HUMAN_REVIEW" in output


def test_approve_cli_requires_and_passes_explicit_acknowledgement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = tmp_path / "report.json"
    approval = tmp_path / "approval.json"
    approval.write_text(
        json.dumps({"verdict": "APPROVED_FOR_V1_PREPARATION"}),
        encoding="utf-8",
    )
    observed: dict[str, object] = {}

    def approve(
        _repo: Path,
        _runtime: Path,
        _report: Path,
        *,
        approver: str,
        acknowledge: bool,
    ) -> Path:
        observed["approver"] = approver
        observed["acknowledge"] = acknowledge
        return approval

    monkeypatch.setattr(release_readiness_cli, "approve_release", approve)
    code = release_readiness_cli.main(
        [
            "--root",
            str(ROOT),
            "--runtime-root",
            str(tmp_path),
            "approve",
            "--report",
            str(report),
            "--approver",
            "Mathias",
            "--acknowledge-v1",
        ]
    )
    assert code == 0
    assert observed == {"approver": "Mathias", "acknowledge": True}
    assert "L8_APPROVAL=APPROVED_FOR_V1_PREPARATION" in capsys.readouterr().out


def test_approve_cli_reports_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        release_readiness_cli,
        "approve_release",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(PermissionError("not ready")),
    )
    code = release_readiness_cli.main(
        [
            "--root",
            str(ROOT),
            "--runtime-root",
            str(tmp_path),
            "approve",
            "--report",
            str(tmp_path / "report.json"),
            "--approver",
            "Mathias",
            "--acknowledge-v1",
        ]
    )
    assert code == 2
    assert "L8_APPROVAL=BLOCKED" in capsys.readouterr().out
