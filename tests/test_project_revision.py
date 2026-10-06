from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from test_daily_worker import planned as planned

from clawfedora import project_revision
from clawfedora.artifact_exchange import validate_exchange_completeness
from clawfedora.project_common import read_json, sha256_file
from clawfedora.project_engine import (
    _validate_plan,
    package_project,
    ready_tasks,
    store_verdict,
    transition_project,
)
from clawfedora.project_revision import impact, revise
from clawfedora.project_worker import run_project_tasks

ROOT = Path(__file__).resolve().parents[1]


def test_writer_depends_on_all_technical_work_transitively() -> None:
    def task(ident: str, role: str, deps: list[str]) -> dict[str, Any]:
        return {
            "id": ident,
            "role": role,
            "title": ident,
            "objective": ident,
            "depends_on": deps,
            "expected_outputs": [f"deliverables/{ident}/report.md"],
            "acceptance_criteria": ["Choix et preuves"],
        }

    tasks = [
        task("design", "architecte-solutions", []),
        task("ops", "ingenieur-devops", ["design"]),
        task("writing", "redacteur-pedagogique", ["ops"]),
    ]
    _validate_plan(tasks)
    tasks[-1]["depends_on"] = ["design"]
    with pytest.raises(ValueError, match="dépendances techniques manquantes"):
        _validate_plan(tasks)
    tasks[-1]["writing_scope"] = "intermediate"
    _validate_plan(tasks)
    tasks[-1]["learning_mode"] = "arbitrary"
    with pytest.raises(ValueError, match="learning_mode"):
        _validate_plan(tasks)
    tasks[-1]["learning_mode"] = "direct"
    tasks[-1]["writing_scope"] = "arbitrary"
    with pytest.raises(ValueError, match="writing_scope"):
        _validate_plan(tasks)


def result(_role: str, prompt: str, _session: str) -> dict[str, Any]:
    task = json.loads(prompt.split("\n", 1)[1])
    return {
        "files": {p: "Version actuelle, choix et preuves." for p in task["expected_outputs"]},
        "summary": "collecté",
    }


def test_revision_reopens_complete_project_and_invalidates_transitive_outputs_and_audits(
    planned: tuple[Path, Path],
) -> None:
    runtime, project = planned
    run_project_tasks(ROOT, runtime, project, runner=result)
    store_verdict(ROOT, project, "validation", "PASS", [], reviewer="auditeur-qualite")
    transition_project(ROOT, project, "REVIEW", actor="auditeur-qualite", reason="audit")
    store_verdict(ROOT, project, "review", "PASS", [], reviewer="auditeur-qualite")
    package_project(ROOT, project, actor="human")
    transition_project(
        ROOT, project, "COMPLETE", actor="human", reason="delivery", human_approved=True
    )
    assert impact(project, "design-choice") == ["design-choice", "research-check"]
    with pytest.raises(PermissionError):
        revise(project, "design-choice", "Changer le choix")
    entry = revise(project, "design-choice", "Changer le choix", human_approved=True)
    assert entry["affected_tasks"] == ["design-choice", "research-check"]
    assert read_json(project / "project.json")["status"] == "IN_PROGRESS"
    for scope in (
        "deliverables/design-choice",
        "deliverables/research-check",
        "evidence/validation_report.json",
        "evidence/review_report.json",
        "deliverables/package_manifest.json",
    ):
        assert not (project / scope).exists()
        assert (project / "history/revisions/revision-001" / scope).exists()
    assert [t["task_id"] for t in ready_tasks(ROOT, project)] == ["design-choice"]
    assert not (
        project / "context/exchange/research-check/dependencies/design-choice/run-001"
    ).exists()
    results = run_project_tasks(ROOT, runtime, project, runner=result)
    assert [r["attempt"] for r in results] == [2, 2]
    assert read_json(project / "project.json")["status"] == "VALIDATING"
    assert validate_exchange_completeness(ROOT, project) == []
    assert not (project / "evidence/validation_report.json").exists()


def test_partial_revision_keeps_current_unaffected_dependency_bundles(
    planned: tuple[Path, Path],
) -> None:
    runtime, project = planned
    run_project_tasks(ROOT, runtime, project, runner=result)
    old = sha256_file(project / "deliverables/design-choice/report.md")
    assert impact(project, "research-check") == ["research-check"]
    revise(project, "research-check", "Clarifier la synthèse", human_approved=True)
    assert sha256_file(project / "deliverables/design-choice/report.md") == old
    assert (
        project / "context/exchange/research-check/dependencies/design-choice/run-001/manifest.json"
    ).is_file()
    results = run_project_tasks(ROOT, runtime, project, runner=result)
    assert [r["task_id"] for r in results] == ["research-check"]
    assert validate_exchange_completeness(ROOT, project) == []


def test_failed_revision_rolls_back_project_and_artifact_moves(
    planned: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, project = planned
    run_project_tasks(ROOT, runtime, project, runner=result)
    before = {
        p.relative_to(project).as_posix(): sha256_file(p) for p in project.rglob("*") if p.is_file()
    }
    original_write = project_revision.write_json

    def fail_final(path: Path, value: dict[str, Any]) -> None:
        if path.name == "project.json":
            raise OSError("simulated storage failure")
        original_write(path, value)

    monkeypatch.setattr(project_revision, "write_json", fail_final)
    with pytest.raises(OSError):
        revise(project, "research-check", "Correction", human_approved=True)
    after = {
        p.relative_to(project).as_posix(): sha256_file(p) for p in project.rglob("*") if p.is_file()
    }
    assert after == before


def test_revision_refuses_unknown_task_or_symlink_before_mutating(
    planned: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    runtime, project = planned
    run_project_tasks(ROOT, runtime, project, runner=result)
    with pytest.raises(ValueError, match="inconnue"):
        revise(project, "unknown-task", "Correction", human_approved=True)
    (project / "deliverables/link").symlink_to(tmp_path)
    with pytest.raises(ValueError, match="symbolique"):
        revise(project, "design-choice", "Correction", human_approved=True)
    assert read_json(project / "project.json")["status"] == "VALIDATING"
