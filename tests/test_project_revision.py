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
from clawfedora.project_revision import audit_corrections, impact, revise
from clawfedora.project_worker import review_project, run_project_tasks

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


def _audit_output(
    planned: tuple[Path, Path], *, failed: str | None, sessions: list[str],
) -> Path:
    runtime, project = planned

    def auditor(role: str, _prompt: str, session: str) -> dict[str, Any]:
        assert role == "auditeur-qualite" and session not in sessions
        sessions.append(session)
        root = runtime / "workspaces/auditeur-qualite/projects/reviews" / session
        assert not (root / "history").exists()
        assert not (root / "context/audit-correction.json").exists()
        return {
            "verdict": "FAIL" if failed else "PASS",
            "findings": [],
            "criteria": {
                task_id: [
                    {"passed": task_id != failed, "evidence": "Le choix manque de justification.",
                     "reference": f"deliverables/{task_id}/report.md"}
                ]
                for task_id in ("design-choice", "research-check")
            },
        }

    return review_project(ROOT, runtime, project, "validation", runner=auditor)


def test_audit_correction_targets_producer_then_requires_fresh_audit(
    planned: tuple[Path, Path],
) -> None:
    runtime, project = planned
    sessions: list[str] = []
    run_project_tasks(ROOT, runtime, project, runner=result)
    report = _audit_output(planned, failed="design-choice", sessions=sessions)
    candidate = audit_corrections(project)
    assert candidate is not None and candidate["sha256"] == sha256_file(report)
    assert [task["task_id"] for task in candidate["tasks"]] == ["design-choice"]
    assert candidate["tasks"][0]["findings"][0]["number"] == 1
    assert not (project / "history/revisions").exists()

    with pytest.raises(PermissionError):
        revise(project, "design-choice", "Justifier le choix", audit_sha256=candidate["sha256"])
    with pytest.raises(ValueError, match="aucun critère refusé"):
        revise(project, "research-check", "Relire", human_approved=True,
               audit_sha256=candidate["sha256"])
    baseline = project / "deliverables/design-choice/report.md"
    original = baseline.read_text(encoding="utf-8")
    revision = revise(
        project, "design-choice", "Justifier le choix", human_approved=True,
        audit_sha256=candidate["sha256"],
    )
    assert revision["audit"]["sha256"] == candidate["sha256"]
    assert revision["affected_tasks"] == ["design-choice", "research-check"]

    def producer(role: str, prompt: str, session: str) -> dict[str, Any]:
        task = json.loads(prompt.split("\n", 1)[1])
        task_root = runtime / "workspaces" / role / "projects" / project.name / task["id"]
        context = task_root / session / "context"
        if task["id"] == "design-choice":
            staged = read_json(context / "audit-correction.json")
            assert staged["audit"]["session_id"] == sessions[0]
            assert staged["findings"][0]["evidence"] == "Le choix manque de justification."
            old = context / "previous-outputs/deliverables/design-choice/report.md"
            assert old.read_text(encoding="utf-8") == original
            assert old.stat().st_mode & 0o222 == 0
            assert "context/audit-correction.json" in prompt
        else:
            assert not (context / "audit-correction.json").exists()
            assert not (context / "previous-outputs").exists()
            receipt = read_json(context / "dependency-inputs.json")
            assert receipt["inputs"][0]["attempt"] == 2
        return {"files": {task["expected_outputs"][0]: original + "\nJustification du choix."},
                "summary": "Correction collectée"}

    run_project_tasks(ROOT, runtime, project, runner=producer)
    assert read_json(project / "project.json")["status"] == "VALIDATING"
    assert not report.exists()
    passed = _audit_output(planned, failed=None, sessions=sessions)
    assert read_json(passed)["verdict"] == "PASS" and len(sessions) == 2
    assert audit_corrections(project) is None


@pytest.mark.parametrize("changed", ["report", "output"])
def test_linked_correction_refuses_stale_evidence(
    planned: tuple[Path, Path], changed: str,
) -> None:
    runtime, project = planned
    run_project_tasks(ROOT, runtime, project, runner=result)
    report = _audit_output(planned, failed="design-choice", sessions=[])
    digest = sha256_file(report)
    if changed == "report":
        report.write_bytes(report.read_bytes() + b"\n")
    else:
        output = project / "deliverables/design-choice/report.md"
        output.chmod(0o640)
        output.write_text("# Bytes modifiés", encoding="utf-8")
    with pytest.raises(ValueError, match="audit de correction"):
        revise(project, "design-choice", "Justifier le choix", human_approved=True,
               audit_sha256=digest)
    assert not (project / "history/revisions").exists()
    assert read_json(project / "project.json")["status"] == "VALIDATING"


def test_changed_archived_output_is_refused_before_model_call(planned: tuple[Path, Path]) -> None:
    runtime, project = planned
    run_project_tasks(ROOT, runtime, project, runner=result)
    report = _audit_output(planned, failed="design-choice", sessions=[])
    revise(project, "design-choice", "Justifier le choix", human_approved=True,
           audit_sha256=sha256_file(report))
    archive = project / "history/revisions/revision-001"
    prior = archive / "deliverables/design-choice/report.md"
    prior.chmod(0o640)
    prior.write_text("Contenu modifié", encoding="utf-8")
    attempts = read_json(project / "context/task_assignments.json")["tasks"][0]["attempts"]

    def never_called(*_args: Any) -> dict[str, Any]:
        pytest.fail("le producteur ne doit pas recevoir la sortie modifiée")

    with pytest.raises(ValueError, match="sortie historique modifiée"):
        run_project_tasks(ROOT, runtime, project, runner=never_called)
    assert read_json(project / "context/task_assignments.json")["tasks"][0]["attempts"] == attempts


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


def test_identical_audit_correction_stops_until_new_approval(planned: tuple[Path, Path]) -> None:
    runtime, project = planned
    producer = "design-choice"
    run_project_tasks(ROOT, runtime, project, runner=result)
    report = _audit_output(planned, failed=producer, sessions=[])
    revise(project, producer, "Préciser la justification", human_approved=True,
           audit_sha256=sha256_file(report))
    blocked = run_project_tasks(ROOT, runtime, project, runner=result)
    assert blocked[0]["status"] == "FAIL" and blocked[0]["failure_code"] == "no_progress"
    assert not (project / "deliverables/design-choice/report.md").exists()
    assert not (project / "deliverables/research-check/report.md").exists()
    assert ready_tasks(ROOT, project) == []
    assert run_project_tasks(ROOT, runtime, project, runner=result, resume=True) == []
    revise(project, producer, "Reconsidérer le choix", human_approved=True)
    assert [row["task_id"] for row in ready_tasks(ROOT, project)] == [producer]
