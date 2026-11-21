"""Offline behavioral tests for long-running milestone evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from clawfedora import chat_projects, milestone_evidence, source_connectors
from clawfedora.project_common import read_json, write_json
from clawfedora.project_intake import create_project, validate_input_integrity
from clawfedora.project_roadmap import change, initialize, load
from clawfedora.project_ui import details

ROOT = Path(__file__).resolve().parents[1]
REPO = "example/OpsDesk"
OLD = "a" * 40
NEW = "b" * 40
ENV_SHA = "c" * 64


def setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, dict[str, Any]]:
    runtime = tmp_path / "runtime"
    brief = tmp_path / "brief.md"
    brief.write_text("Suivi InfraOps pour une mission longue.", encoding="utf-8")
    project = create_project(
        ROOT, runtime, "opsdesk-demo", "Projet OpsDesk démonstration", intake_items=[brief]
    )

    def github(dest: Path, repo: str, commit: str) -> dict[str, Any]:
        assert repo == REPO
        (dest / "README.md").write_text("# OpsDesk\n" + commit, encoding="utf-8")
        return {
            "provider": "github", "repository": repo, "commit": commit,
            "file_count": 1, "skipped": 0,
        }

    monkeypatch.setattr(source_connectors, "_github_snapshot", github)
    source_connectors.import_snapshot(
        ROOT, runtime, "opsdesk-demo", github=REPO, commit=OLD
    )
    initialize(project, {"milestones": [
        {"id": "exercice-01", "title": "Linux", "depends_on": []},
        {"id": "exercice-02", "title": "Terraform", "depends_on": ["exercice-01"]},
    ]}, apply=True)
    change(project, "exercice-02", "IN_PROGRESS", "Préparation", apply=True)
    params: dict[str, Any] = {
        "runtime": runtime, "project_id": "opsdesk-demo",
        "milestone_id": "exercice-02", "repository": REPO, "commit": OLD,
        "environment": "srv-admin", "environment_sha256": ENV_SHA,
        "kind": "operator", "procedure": "terraform plan",
        "expected": "Aucun changement de configuration imprévu",
        "observed": "Sortie obtenue dans le laboratoire",
        "outcome": "PASS",
    }
    return runtime, project, params


def test_operator_receipt_is_append_only_and_never_certifies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _runtime, project, params = setup(tmp_path, monkeypatch)
    old_project = read_json(project / "project.json")
    proof = tmp_path / "terraform-output.txt"
    proof.write_text("Plan: 0 to add, 0 to change, 0 to destroy.\n")
    params["output_file"] = proof
    preview = milestone_evidence.capture(**params)
    assert preview["status"] == "PREVIEW"
    assert preview["milestone_verification"] == "NOT_VERIFIED"
    assert milestone_evidence.report(project)["total"] == 0
    with pytest.raises(ValueError, match="prévisualisation"):
        milestone_evidence.capture(**params, apply=True, approve="0" * 64)
    recorded = milestone_evidence.capture(
        **params, apply=True, approve=preview["approval_sha256"]
    )
    assert recorded["status"] == "RECORDED"
    assert recorded["verification"] == "NOT_VERIFIED"
    path = project / recorded["record_path"]
    receipt = read_json(path)
    assert receipt["output_sha256"] == preview["output_sha256"]
    assert receipt["origin"] == "OPERATOR_SUPPLIED_NOT_IDENTITY_VERIFIED"
    assert (path.parent / "output.txt").read_text().startswith("Plan: 0")
    second = milestone_evidence.capture(**params)
    assert milestone_evidence.capture(
        **params, apply=True, approve=second["approval_sha256"]
    )["id"] != recorded["id"]
    shown = milestone_evidence.report(project)
    assert shown["total"] == 2
    assert shown["milestones"][1]["count"] == 2
    assert shown["milestones"][1]["recorded"][0]["verification"] == "NOT_VERIFIED"
    assert all("observed" not in item for item in shown["milestones"][1]["recorded"])
    assert validate_input_integrity(project) == []
    assert read_json(project / "project.json") == old_project
    assert load(project)["milestones"][1]["verification"] == "NOT_VERIFIED"


def test_github_refresh_marks_historical_proof_without_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from clawfedora.github_refresh import refresh

    runtime, project, params = setup(tmp_path, monkeypatch)
    preview = milestone_evidence.capture(**params)
    entry = milestone_evidence.capture(
        **params, apply=True, approve=preview["approval_sha256"]
    )
    proof = project / entry["record_path"]
    before = proof.read_bytes()
    next_version = refresh(runtime, "opsdesk-demo", REPO, NEW)
    refresh(
        runtime, "opsdesk-demo", REPO, NEW,
        approve=next_version["approve_sha256"], apply=True,
    )
    display = milestone_evidence.report(project)["milestones"][1]["recorded"][0]
    assert display["requalify_reasons"] == ["GIT_REVISION_CHANGED"]
    assert display["verification"] == "REQUALIFY"
    assert proof.read_bytes() == before
    with pytest.raises(ValueError, match="périmé"):
        milestone_evidence.capture(**params)


def test_environment_and_plan_drift_need_requalification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _runtime, project, params = setup(tmp_path, monkeypatch)
    task = project / "context/project_plan.json"
    write_json(task, {"tasks": [
        {"id": "first-task", "acceptance_criteria": ["Cible observable"]}
    ]})
    params.update({"task_id": "first-task", "criterion": 1})
    preview = milestone_evidence.capture(**params)
    milestone_evidence.capture(
        **params, apply=True, approve=preview["approval_sha256"]
    )
    same = milestone_evidence.report(
        project, environment="srv-admin", environment_sha256=ENV_SHA
    )["milestones"][1]["recorded"][0]
    assert same["environment_check"] == "MATCH"
    assert same["requalify_reasons"] == []
    other = milestone_evidence.report(
        project, environment="srv-app", environment_sha256="d" * 64
    )["milestones"][1]["recorded"][0]
    assert set(other["requalify_reasons"]) == {
        "TARGET_DIFFERENT", "ENVIRONMENT_REVISION_CHANGED"
    }
    write_json(task, {"tasks": [
        {"id": "first-task", "acceptance_criteria": ["Cible modifiée"]}
    ]})
    stale = milestone_evidence.report(project)["milestones"][1]["recorded"][0]
    assert stale["requalify_reasons"] == ["TASK_PLAN_CHANGED"]


def test_public_ci_verification_is_scope_limited_and_bound_to_exact_sha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _runtime, project, params = setup(tmp_path, monkeypatch)
    params.update({
        "kind": "public-ci", "environment": "ci-github",
        "environment_sha256": None,
        "procedure": "GitHub Actions run officiel", "expected": "Pipeline vert",
        "observed": "", "outcome": "UNKNOWN", "run_id": 12345,
    })
    calls: list[tuple[str, str, int, str]] = []
    timestamps = iter(["2026-11-21T10:00:00Z", "2026-11-21T10:00:05Z"])

    def verified(provider: str, repository: str, run_id: int, commit: str) -> dict[str, Any]:
        calls.append((provider, repository, run_id, commit))
        return {
            "provider": provider, "repository": repository,
            "run_id": run_id, "commit": commit,
            "verdict": "VERIFIED_RUN_SUCCESS",
            "observed_at_utc": next(timestamps), "scope": "pipeline_result_only",
        }

    monkeypatch.setattr(milestone_evidence, "verify_public_run", verified)
    initial = milestone_evidence.capture(**params)
    assert initial["verification"] == "CI_RUN_SUCCESS_ONLY"
    saved = milestone_evidence.capture(
        **params, apply=True, approve=initial["approval_sha256"]
    )
    assert saved["verification"] == "CI_RUN_SUCCESS_ONLY"
    assert calls == [
        ("github", REPO, 12345, OLD), ("github", REPO, 12345, OLD)
    ]
    display = milestone_evidence.report(project)["milestones"][1]["recorded"][0]
    assert display["verification"] == "CI_RUN_SUCCESS_ONLY"
    assert display["milestone_verification"] == "NOT_VERIFIED"
    assert display["environment_check"] == "UNPINNED"


def test_unknown_origin_and_unpinned_environment_never_claim_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _runtime, project, params = setup(tmp_path, monkeypatch)
    params["environment_sha256"] = None
    params["outcome"] = "UNKNOWN"
    params["kind"] = "simulation"
    preview = milestone_evidence.capture(**params)
    milestone_evidence.capture(**params, apply=True, approve=preview["approval_sha256"])
    display = milestone_evidence.report(project)["milestones"][1]["recorded"][0]
    assert display["verification"] == "NOT_VERIFIED"
    assert display["environment_check"] == "UNPINNED"


def test_secrets_symlinks_and_tampering_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _runtime, project, params = setup(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="secret"):
        milestone_evidence.capture(
            **{**params, "observed": "ghp_" + "X" * 40}
        )
    source = tmp_path / "raw.txt"
    source.write_text("Clear inspection result\n")
    linked = tmp_path / "link.txt"
    linked.symlink_to(source)
    with pytest.raises(ValueError, match="liée"):
        milestone_evidence.capture(**params, output_file=linked)
    initial = milestone_evidence.capture(**params, output_file=source)
    saved = milestone_evidence.capture(
        **params, output_file=source, apply=True,
        approve=initial["approval_sha256"],
    )
    receipt = project / saved["record_path"]
    value = read_json(receipt)
    value["operator_outcome"] = "FAIL"
    write_json(receipt, value)
    with pytest.raises(ValueError, match="modifiée|corrompue"):
        milestone_evidence.report(project)


def test_empty_source_or_invalid_linked_task_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _runtime, _project, params = setup(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="non lié"):
        milestone_evidence.capture(
            **{**params, "repository": "another/repo"}
        )
    with pytest.raises(ValueError, match="tâche|--task-id"):
        milestone_evidence.capture(**{**params, "task_id": "fake-task", "criterion": 1})
    with pytest.raises(ValueError, match="ensemble"):
        milestone_evidence.capture(**{**params, "criterion": 1})


def test_parser_requires_explicit_apply_and_uses_bounded_arguments() -> None:
    parser = milestone_evidence.build_parser()
    args = parser.parse_args([
        "--project-id", "opsdesk-demo", "capture",
        "--milestone-id", "exercice-02", "--repo", REPO, "--commit", OLD,
        "--environment", "srv-admin", "--procedure", "terraform plan",
        "--expected", "Plan vérifié",
    ])
    assert args.apply is False
    assert args.kind == "operator"
    assert args.command == "capture"


def test_dashboard_and_chat_report_metadata_without_raw_private_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _runtime, project, params = setup(tmp_path, monkeypatch)
    preview = milestone_evidence.capture(**params)
    milestone_evidence.capture(
        **params, apply=True, approve=preview["approval_sha256"]
    )
    dashboard = details(project)["milestone_evidence"]
    assert dashboard["total"] == 1
    assert dashboard["milestones"][1]["count"] == 1
    assert "Sortie obtenue dans le laboratoire" not in json.dumps(dashboard)
    summary = chat_projects.status_text(ROOT, _runtime, project)
    assert "Preuves des exercices : 1 reçus" in summary
    assert "Sortie obtenue dans le laboratoire" not in summary
