"""Project continuation is read-only, per-project and grounded in canonical records."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from clawfedora import atelier_chat, chat_projects, milestone_evidence, project_resume
from clawfedora.project_common import read_json, write_json
from clawfedora.project_roadmap import change, initialize


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

    def fake_evidence(target: Path) -> dict[str, Any]:
        calls.append(target)
        return {"total": 3, "milestones": [
            {"to_requalify": 2}, {"to_requalify": 0},
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
    assert "non certifiés" in project_resume.render(checked)

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
