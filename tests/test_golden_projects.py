from __future__ import annotations

import json
from pathlib import Path

import pytest

from clawfedora import golden_projects

ROOT = Path(__file__).resolve().parents[1]


def test_l7_dry_run_describes_complete_suite() -> None:
    payload = golden_projects.dry_run(ROOT)
    assert payload["gate"] == "L7"
    assert payload["verdict"] == "READY"
    assert payload["project_count"] == 6
    assert payload["task_count"] == 17
    assert len(payload["golden_projects"]) == 5
    assert payload["representative_project"] == "representative-devops-delivery"
    assert payload["cloud_calls_allowed"] is False
    assert payload["remote_publication_allowed"] is False
    assert payload["final_human_completion_allowed"] is False


def test_l7_full_suite_runs_real_project_engine_locally(tmp_path: Path) -> None:
    code, report_path = golden_projects.run_golden_suite(ROOT, tmp_path)
    assert code == 0
    assert report_path.is_file()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["gate"] == "L7"
    assert report["verdict"] == "PASS"
    assert report["golden_projects_pass"] == 5
    assert report["representative_projects_pass"] == 1
    assert len(report["projects"]) == 6
    assert sum(project["task_count"] for project in report["projects"]) == 17
    assert all(project["terminal_status"] == "PACKAGING" for project in report["projects"])
    assert all(project["validation"] == "PASS" for project in report["projects"])
    assert all(project["review"] == "PASS" for project in report["projects"])
    assert all(project["package_integrity"] is True for project in report["projects"])
    assert all(project["human_gate_preserved"] is True for project in report["projects"])
    assert report["telemetry"]["events"] == 6
    assert report["telemetry"]["local_only"] is True
    assert report["telemetry"]["raw_prompt_or_response_persisted"] is False
    assert report["finops"]["events"] == 12
    assert report["finops"]["net_exposure_eur"] == 0.0
    assert report["cloud_calls_allowed"] is False
    assert report["remote_publication_allowed"] is False
    assert report["automatic_human_approval"] is False
    assert report["final_human_completion"] is False
    assert report["failures"] == []
    assert len(report["limitations"]) >= 3

    representative = next(
        project for project in report["projects"] if project["kind"] == "representative"
    )
    project_path = Path(representative["project_path"])
    project_manifest = json.loads(
        (project_path / "project.json").read_text(encoding="utf-8")
    )
    assert project_manifest["status"] == "PACKAGING"
    final_report = json.loads(
        (project_path / "evidence/final_report.json").read_text(encoding="utf-8")
    )
    assert final_report["human_approval_required"] is True
    exchange_index = json.loads(
        (project_path / "context/exchange/index.json").read_text(encoding="utf-8")
    )
    assert len(exchange_index["records"]) > 8


def test_l7_suite_fails_closed_when_one_project_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = golden_projects._run_project
    calls = 0

    def fail_first(
        repo_root: Path,
        run_root: Path,
        spec: dict[str, object],
        *,
        kind: str,
    ) -> golden_projects.GoldenProjectResult:
        nonlocal calls
        calls += 1
        if calls == 1:
            return golden_projects.GoldenProjectResult(
                project_id=str(spec["id"]),
                kind=kind,
                verdict="FAIL",
                terminal_status="IN_PROGRESS",
                task_count=1,
                validation="",
                review="",
                package_integrity=False,
                human_gate_preserved=False,
                duration_ms=1,
                project_path="",
                failure="synthetic failure",
            )
        return original(repo_root, run_root, spec, kind=kind)

    monkeypatch.setattr(golden_projects, "_run_project", fail_first)
    code, report_path = golden_projects.run_golden_suite(ROOT, tmp_path)
    assert code == 2
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["verdict"] == "FAIL"
    assert report["golden_projects_pass"] == 4
    assert any("synthetic failure" in failure for failure in report["failures"])
    assert any("final human gate" in failure for failure in report["failures"])


def test_l7_dry_run_rejects_invalid_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        golden_projects,
        "validate_golden_contracts",
        lambda _root: (("invalid contract",), ()),
    )
    with pytest.raises(ValueError, match="invalid contract"):
        golden_projects.dry_run(ROOT)
