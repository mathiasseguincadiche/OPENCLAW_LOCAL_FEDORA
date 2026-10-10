from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from clawfedora import chat_run
from clawfedora.project_common import write_json


def _project(tmp_path: Path, status: str) -> tuple[Path, Path]:
    runtime = tmp_path / "runtime"
    project = runtime / "projects/demo-project"
    project.mkdir(parents=True)
    write_json(
        project / "project.json",
        {
            "project_id": "demo-project",
            "title": "Démo",
            "status": status,
            "orchestration": {"history": []},
        },
    )
    return runtime, project


def test_run_pause_and_audit_commands_use_existing_project_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, project = _project(tmp_path, "ASSIGNED")
    started: list[str] = []
    paused: list[str] = []

    monkeypatch.setattr(chat_run, "current_status", lambda _project: "ASSIGNED")
    monkeypatch.setattr(
        chat_run,
        "_start",
        lambda _runtime, _project, kind, _action: started.append(kind) or "lancé",
    )
    assert chat_run.run_command(tmp_path, runtime, project, "lancer", "") == "lancé"
    assert started == ["run"]

    monkeypatch.setattr(
        chat_run, "request_pause", lambda _runtime, _project: paused.append("pause")
    )
    assert "Pause demandée" in chat_run.run_command(
        tmp_path, runtime, project, "pause", ""
    )
    assert paused == ["pause"]

    monkeypatch.setattr(chat_run, "current_status", lambda _project: "VALIDATING")
    assert chat_run.run_command(tmp_path, runtime, project, "auditer", "") == "lancé"
    assert started[-1] == "validation"


def test_guided_submission_uses_uploads_then_background_feedback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, project = _project(tmp_path, "IN_PROGRESS")
    monkeypatch.setattr(
        chat_run.chat_files,
        "practice_files",
        lambda *_args: {"deliverables/task/result.md": "# résultat\n"},
    )
    submitted: list[dict[str, Any]] = []

    def fake_submit(
        _repo: Path,
        _runtime: Path,
        _project: Path,
        task_id: str,
        data: dict[str, Any],
    ) -> dict[str, str]:
        submitted.append(data)
        return {"task_id": task_id, "status": "AWAITING_FEEDBACK"}

    monkeypatch.setattr(chat_run, "submit", fake_submit)
    monkeypatch.setattr(chat_run, "_start", lambda *_args, **_kwargs: "feedback")
    reply = chat_run.run_command(
        tmp_path,
        runtime,
        project,
        "soumettre",
        "task J'ai complété la configuration et vérifié le lint.",
        attachments=[{"id": "x"}],
    )
    assert "Soumission reçue" in reply
    assert submitted[0]["human_approved"] is True
    assert submitted[0]["files"]["deliverables/task/result.md"].startswith("# résultat")


def test_revision_and_final_delivery_require_single_use_human_phrases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, project = _project(tmp_path, "IN_PROGRESS")
    monkeypatch.setattr(chat_run, "impact", lambda _project, _task: ["task", "docs"])
    revised: list[tuple[str, str]] = []

    def fake_revise(
        _project: Path, task_id: str, reason: str, *, human_approved: bool = False
    ) -> dict[str, Any]:
        assert human_approved is True
        revised.append((task_id, reason))
        return {"affected_tasks": ["task", "docs"]}

    monkeypatch.setattr(chat_run, "revise", fake_revise)
    reply = chat_run.run_command(
        tmp_path, runtime, project, "modifier", "task corriger la stratégie de rollback"
    )
    code = re.search(r"approuver revision ([A-Z0-9]{4})", reply)
    assert code
    approved = chat_run.apply_approval(
        tmp_path, runtime, project, "revision", code.group(1)
    )
    assert "Révision approuvée" in approved and revised
    second = chat_run.apply_approval(
        tmp_path, runtime, project, "revision", code.group(1)
    )
    assert "Code inconnu" in second

    payload = {
        "project_id": "demo-project",
        "title": "Démo",
        "status": "PACKAGING",
        "orchestration": {"history": []},
    }
    write_json(project / "project.json", payload)
    monkeypatch.setattr(chat_run, "current_status", lambda _project: "PACKAGING")
    completed: list[str] = []
    def fake_complete_locked(_repo: Path, _project: Path) -> None:
        # The finalizer must still hold the same lock that validated the human phrase.
        assert chat_run.worker_active(runtime)
        completed.append("complete")

    monkeypatch.setattr(chat_run, "_complete_locked", fake_complete_locked)
    reply = chat_run.run_command(tmp_path, runtime, project, "livrer", "")
    code = re.search(r"approuver livraison ([A-Z0-9]{4})", reply)
    assert code
    approved = chat_run.apply_approval(
        tmp_path, runtime, project, "livraison", code.group(1)
    )
    assert "Livraison finale approuvée" in approved
    assert completed == ["complete"]
