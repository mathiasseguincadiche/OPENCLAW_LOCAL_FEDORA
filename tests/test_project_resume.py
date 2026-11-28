"""Project continuation is read-only, per-project and grounded in canonical records."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest
from test_daily_worker import planned as planned

from clawfedora import (
    atelier_chat,
    chat_projects,
    chat_proposals,
    milestone_evidence,
    project_engine,
    project_resume,
)
from clawfedora.project_cli import add_project_parser, run_project_command
from clawfedora.project_common import read_json, sha256_file, write_json
from clawfedora.project_roadmap import change, initialize
from clawfedora.project_worker import run_project_tasks

ROOT = Path(__file__).resolve().parents[1]


def make_project(runtime: Path, name: str) -> Path:
    root = runtime / "projects" / name
    root.mkdir(parents=True)
    write_json(root / "project.json", {
        "project_id": name, "title": "Projet " + name, "status": "IN_PROGRESS",
    })
    return root


def milestones() -> dict[str, Any]:
    return {"milestones": [
        {"id": "m1-roadmap", "title": "Concevoir la topologie", "depends_on": []},
        {"id": "m2-terraform", "title": "Déployer Terraform", "depends_on": ["m1-roadmap"]},
        {"id": "m3-ansible", "title": "Configurer Ansible", "depends_on": ["m2-terraform"]},
        {"id": "m4-docs", "title": "Documenter", "depends_on": ["m1-roadmap"]},
    ]}


def test_continuity_selects_ready_and_active_without_claiming_verification(tmp_path: Path) -> None:
    project = make_project(tmp_path, "opsdesk")
    initialize(project, milestones(), apply=True)
    change(project, "m1-roadmap", "IMPLEMENTED", "Déclaré terminé", apply=True)
    change(project, "m2-terraform", "IN_PROGRESS", "Travail de laboratoire", apply=True)
    change(project, "m3-ansible", "BLOCKED", "Dépendance en cours", apply=True)
    report = project_resume.overview(tmp_path, project)
    assert report["project_id"] == "opsdesk"
    assert report["roadmap"]["status"] == "AVAILABLE"
    assert report["roadmap"]["counts"] == {
        "PLANNED": 1, "IN_PROGRESS": 1, "BLOCKED": 1, "IMPLEMENTED": 1,
    }
    assert [item["id"] for item in report["roadmap"]["active"]] == [
        "m2-terraform", "m3-ansible",
    ]
    assert [item["id"] for item in report["roadmap"]["ready"]] == ["m4-docs"]
    assert all(item["verification"] == "NOT_VERIFIED"
               for item in report["roadmap"]["ready"] + report["roadmap"]["active"])
    assert "Dépendance en cours" not in json.dumps(report)
    assert report["milestone_evidence"] == {"status": "NOT_CHECKED_IN_CHAT"}


def test_no_project_data_crosses_boundaries_or_uses_other_chat_history(
    tmp_path: Path,
) -> None:
    first = make_project(tmp_path, "opsdesk")
    second = make_project(tmp_path, "bankflow")
    initialize(first, milestones(), apply=True)
    initialize(second, {"milestones": [
        {"id": "only-bankflow", "title": "Secret propre au second projet", "depends_on": []},
    ]}, apply=True)
    report = project_resume.overview(tmp_path, first)
    assert "only-bankflow" not in json.dumps(report)
    assert "Secret propre au second projet" not in json.dumps(report)
    assert "messages" not in report


def test_evidence_is_checked_only_for_explicit_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = make_project(tmp_path, "opsdesk")
    initialize(project, milestones(), apply=True)
    calls: list[Path] = []
    receipt = {
        "id": "c" * 32, "milestone_id": "m2-terraform", "kind": "public-ci",
        "captured_at": "2026-11-27T16:00:00+00:00", "commit": "a" * 40,
        "record_sha256": "b" * 64, "verification": "REQUALIFY",
    }

    def fake_evidence(target: Path) -> dict[str, Any]:
        calls.append(target)
        return {"total": 3, "milestones": [
            {"to_requalify": 2, "recorded": [
                {**receipt, "output": "contenu interne à la preuve"},
            ]}, {"to_requalify": 0},
        ]}

    monkeypatch.setattr(milestone_evidence, "report", fake_evidence)
    assert project_resume.overview(tmp_path, project)["milestone_evidence"]["status"] == (
        "NOT_CHECKED_IN_CHAT"
    )
    assert calls == []
    checked = project_resume.overview(tmp_path, project, check_evidence=True)
    assert calls == [project]
    assert checked["milestone_evidence"]["total"] == 3
    assert checked["milestone_evidence"]["to_requalify"] == 2
    source = f"context/milestone-evidence/m2-terraform/{receipt['id']}/record.json"
    assert checked["milestone_evidence"]["references"] == [{**receipt, "source": source}]
    brief = project_resume.render(checked)
    assert "non certifiés" in brief and "REQUALIFY" in brief
    assert "contenu interne" not in json.dumps(checked)

    def invalid(_target: Path) -> dict[str, Any]:
        raise ValueError("Hash mismatch")

    monkeypatch.setattr(milestone_evidence, "report", invalid)
    assert project_resume.overview(
        tmp_path, project, check_evidence=True,
    )["milestone_evidence"] == {"status": "UNVERIFIED"}


def test_absent_corrupt_and_linked_roadmap_is_not_trusted(tmp_path: Path) -> None:
    project = make_project(tmp_path, "opsdesk")
    assert project_resume.overview(tmp_path, project)["roadmap"]["status"] == "ABSENT"
    path = project / "context/continuous_roadmap.json"
    path.parent.mkdir()
    path.write_text('{"schema_version": -1}', encoding="utf-8")
    assert project_resume.overview(tmp_path, project)["roadmap"]["status"] == "UNVERIFIED"
    path.unlink()
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    path.symlink_to(outside)
    with pytest.raises(ValueError, match="symbolique"):
        project_resume.overview(tmp_path, project)


def test_identity_is_checked_and_no_state_is_mutated(tmp_path: Path) -> None:
    project = make_project(tmp_path, "opsdesk")
    content = read_json(project / "project.json")
    content["project_id"] = "bankflow"
    write_json(project / "project.json", content)
    with pytest.raises(ValueError, match="identité"):
        project_resume.overview(tmp_path, project)


def test_new_native_threads_share_only_canonical_project_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = make_project(tmp_path, "opsdesk")
    initialize(project, milestones(), apply=True)
    first = atelier_chat.create(tmp_path, "opsdesk", "chef-operations")
    second = atelier_chat.create(tmp_path, "opsdesk", "ingenieur-devops")
    make_project(tmp_path, "bankflow")
    third = atelier_chat.create(tmp_path, "bankflow", "chef-operations")

    def no_model(*_args: Any) -> str:
        pytest.fail("La commande de reprise ne doit pas invoquer Ollama/OpenClaw")

    monkeypatch.setattr(atelier_chat, "_policy_answer", no_model)
    initial = atelier_chat.send(tmp_path, tmp_path, first["id"], "!continuer")
    assert "m1-roadmap" in initial["messages"][-1]["content"]
    change(project, "m1-roadmap", "IMPLEMENTED", "Validé manuellement", apply=True)
    renewed = atelier_chat.send(tmp_path, tmp_path, second["id"], "!continuer")
    assert "m2-terraform" in renewed["messages"][-1]["content"]
    assert "m1-roadmap" not in renewed["messages"][-1]["content"].split(
        "Jalons possibles ensuite",
    )[-1]
    assert "m2-terraform" in chat_projects.project_context(
        tmp_path, tmp_path, project, "Quelle est la suite ?",
    )
    denied = atelier_chat.send(tmp_path, tmp_path, third["id"], "!continuer")
    assert "m2-terraform" not in denied["messages"][-1]["content"]
    assert "Aucun" in denied["messages"][-1]["content"]
    invalid_args = atelier_chat.send(tmp_path, tmp_path, second["id"], "!continuer opsdesk")
    assert "sans argument" in invalid_args["messages"][-1]["content"]


def test_invalid_project_or_missing_project_is_not_resumed(tmp_path: Path) -> None:
    assert "Aucun projet" in chat_projects.run_command(
        tmp_path, tmp_path, "continuer", "", None,
    )


def _mission(runtime: Path, project: Path) -> dict[str, Any]:
    report = project_resume.overview(runtime, project, check_evidence=True, repo_root=ROOT)
    return report["mission"]


def test_continuity_reads_the_approved_mission_in_a_new_discussion_and_cli(
    planned: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    runtime, project = planned
    initial = _mission(runtime, project)
    assert initial["next_action"] == "ASSIGNED"
    assert initial["counts"] == {"READY": 1, "AWAITING_DEPENDENCIES": 1}
    assert "mission" not in project_resume.overview(runtime, project, repo_root=ROOT)
    project_engine.transition_project(
        ROOT, project, "IN_PROGRESS", actor="chef-operations", reason="fixture",
    )
    before = {path.relative_to(project): path.read_bytes()
              for path in project.rglob("*") if path.is_file()}
    thread = atelier_chat.create(runtime, project.name, "chef-operations")

    def no_model(*_args: Any) -> str:
        pytest.fail("la lecture de la mission ne doit pas lancer de modèle")

    monkeypatch.setattr(atelier_chat, "_policy_answer", no_model)
    message = atelier_chat.send(ROOT, runtime, thread["id"], "!continuer")["messages"][-1]["content"]
    assert "Mission courante" in message and "`design-choice`" in message
    assert "dépendances en attente" in message
    parser = argparse.ArgumentParser()
    add_project_parser(parser.add_subparsers())
    args = parser.parse_args([
        "project", "continuity", "--runtime-root", str(runtime), "--project-id", project.name,
    ])
    monkeypatch.setattr("clawfedora.project_cli.require_storage", lambda *_args: None)
    assert run_project_command(ROOT, args) == 0
    mission = json.loads(capsys.readouterr().out)["mission"]
    assert mission["next_action"] == "READY"
    assert mission["tasks"][0]["objective"] == "Documenter"
    assert len(mission["sources"]["assignments_sha256"]) == 64
    assert {path.relative_to(project): path.read_bytes()
            for path in project.rglob("*") if path.is_file()} == before


def test_continuity_surfaces_its_own_interrupted_publication(
    planned: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, project = planned
    normal = project_engine.write_json

    def interrupt(path: Path, value: dict[str, Any]) -> None:
        if path.name == "task_assignments.json":
            raise KeyboardInterrupt
        normal(path, value)

    def produce(_role: str, prompt: str, _session: str) -> dict[str, Any]:
        task = json.loads(prompt.split("\n", 1)[1])
        return {"files": {task["expected_outputs"][0]: "Version privée de test"},
                "summary": "Message producteur privé"}

    with monkeypatch.context() as patch:
        patch.setattr(project_engine, "write_json", interrupt)
        with pytest.raises(KeyboardInterrupt):
            run_project_tasks(ROOT, runtime, project, runner=produce)
    journal_path = project / project_engine.TASK_PROMOTION_PATH
    before = journal_path.read_bytes()
    report = _mission(runtime, project)
    assert report["next_action"] == "PUBLICATION_PENDING"
    assert report["pending_publication"] == {"task_id": "design-choice", "attempt": 1}
    text = json.dumps(report, ensure_ascii=False)
    assert "Version privée" not in text and "Message producteur privé" not in text
    assert journal_path.read_bytes() == before
    second = make_project(runtime, "bankflow")
    assert _mission(runtime, second)["status"] == "UNVERIFIED"
    assert "design-choice" not in json.dumps(_mission(runtime, second))
    invalid = read_json(journal_path)
    invalid["project_id"] = "bankflow"
    write_json(journal_path, invalid)
    assert _mission(runtime, project)["status"] == "UNVERIFIED"


def test_continuity_explains_a_stalled_task_and_checks_plan_assignment_agreement(
    planned: tuple[Path, Path],
) -> None:
    runtime, project = planned
    project_engine.transition_project(
        ROOT, project, "IN_PROGRESS", actor="chef-operations", reason="fixture",
    )
    path = project / "context/task_assignments.json"
    assignments = read_json(path)
    assignments["tasks"][0].update(status="FAIL", attempts=1, failure_code="no_progress")
    write_json(path, assignments)
    assert project_engine.ready_tasks(ROOT, project) == []
    mission = _mission(runtime, project)
    assert mission["next_action"] == "BLOCKED"
    assert mission["counts"] == {"STOPPED_NO_PROGRESS": 1, "AWAITING_DEPENDENCIES": 1}
    assignments["tasks"][1]["depends_on"] = []
    write_json(path, assignments)
    assert _mission(runtime, project)["status"] == "UNVERIFIED"


def test_continuity_cites_only_bounded_objectives_from_the_recorded_analysis(
    planned: tuple[Path, Path],
) -> None:
    runtime, project = planned
    source = project / "context/project_analysis.json"
    analysis = read_json(source)
    analysis.update(
        objectives=["Concevoir le déploiement", {"description": "Documenter"}, None]
        + [f"Objectif {index}" for index in range(4, 8)],
        ambiguities=["Hypothèse à examiner"],
    )
    write_json(source, analysis)
    write_json(project / "context/ui_draft.json", {"objectives": ["Brouillon de discussion"]})

    ordinary = project_resume.overview(runtime, project, repo_root=ROOT)
    assert "objectives" not in ordinary and "audit_references" not in ordinary
    report = project_resume.overview(runtime, project, repo_root=ROOT, check_evidence=True)
    objectives = report["objectives"]
    assert objectives["status"] == "RECORDED" and objectives["truncated"] is True
    assert objectives["source"] == "context/project_analysis.json"
    assert objectives["source_sha256"] == sha256_file(source)
    assert objectives["recorded_at"][:10] == analysis["generated_at"][:10]
    assert objectives["items"][:2] == [
        {"position": 1, "objective": "Concevoir le déploiement"},
        {"position": 2, "objective": "Documenter"},
    ]
    assert [item["position"] for item in objectives["items"]] == [1, 2, 4, 5, 6]
    rendered = project_resume.render(report)
    assert "Concevoir le déploiement" in rendered
    assert "Objectif 7" not in rendered and "Brouillon" not in rendered
    assert "Hypothèse" not in json.dumps(report, ensure_ascii=False)


def test_continuity_traces_accepted_notes_within_the_selected_project(tmp_path: Path) -> None:
    project = make_project(tmp_path, "opsdesk")
    other = make_project(tmp_path, "bankflow")
    saved = chat_proposals.save(
        tmp_path, project, "Détail intérieur à la note", "Architecture retenue", "local", "Qwen",
    )
    accepted = chat_proposals.accept(tmp_path, project, saved["number"], saved["sha256"])
    chat_proposals.save(tmp_path, project, "En attente", "Note en attente", "local", "Qwen")
    elsewhere = chat_proposals.save(
        tmp_path, other, "Décision ailleurs", "Titre d'un autre projet", "local", "Qwen",
    )
    chat_proposals.accept(tmp_path, other, elsewhere["number"], elsewhere["sha256"])

    report = project_resume.overview(tmp_path, project, check_evidence=True)
    decisions = report["accepted_decisions"]
    assert decisions["unverified"] == 0
    assert len(decisions["items"]) == 1
    item = decisions["items"][0]
    assert item["title"] == "Architecture retenue"
    assert item["accepted_at"][:10] == accepted["decided_at"][:10]
    assert item["note_path"] == accepted["note"]
    assert item["proposal_path"] == "context/chat/proposals/proposition-001.json"
    assert item["proposal_sha256"] == sha256_file(project / item["proposal_path"])
    assert item["note_sha256"] == sha256_file(project / item["note_path"])
    serialized = json.dumps(report, ensure_ascii=False)
    for excluded in ("Détail intérieur", "Note en attente", "Titre d'un autre projet"):
        assert excluded not in serialized

    note = project / accepted["note"]
    note.write_text("Note changée depuis l'acceptation", encoding="utf-8")
    altered = project_resume.overview(tmp_path, project, check_evidence=True)
    assert altered["accepted_decisions"]["items"] == []
    assert altered["accepted_decisions"]["unverified"] == 1
    assert "restent à vérifier" in project_resume.render(altered)


def test_continuity_distinguishes_current_audit_and_stale_deliverable(
    planned: tuple[Path, Path],
) -> None:
    runtime, project = planned

    def produce(_role: str, prompt: str, _session: str) -> dict[str, Any]:
        task = json.loads(prompt.split("\n", 1)[1])
        return {"files": {task["expected_outputs"][0]: "Deux options et un choix justifié"},
                "summary": "Livrable collecté"}

    results = run_project_tasks(ROOT, runtime, project, runner=produce)
    assert [item["status"] for item in results] == ["PASS", "PASS"]
    source = project_engine.store_verdict(
        ROOT, project, "validation", "PASS", [{"detail": "Commentaire interne de validation"}],
        reviewer="auditeur-qualite",
    )
    report = project_resume.overview(runtime, project, check_evidence=True, repo_root=ROOT)
    assert len(report["audit_references"]) == 1
    audit = report["audit_references"][0]
    assert audit["kind"] == "validation" and audit["status"] == "CURRENT"
    assert audit["verdict"] == "PASS" and audit["origin"] == "RECORDED_VERDICT"
    assert audit["source"] == source.relative_to(project).as_posix()
    assert audit["source_sha256"] == sha256_file(source)
    assert audit["recorded_at"][:10] == read_json(source)["generated_at"][:10]
    assert "Commentaire interne" not in json.dumps(report)

    (project / "deliverables/design-choice/report.md").write_text("Nouvelle version")
    later = project_resume.overview(runtime, project, check_evidence=True, repo_root=ROOT)
    assert later["audit_references"] == [{**audit, "status": "STALE"}]
    assert "à renouveler" in project_resume.render(later)
    assert sha256_file(source) == audit["source_sha256"]
