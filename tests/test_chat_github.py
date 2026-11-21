"""The Open WebUI bridge routes typed GitHub commands, never model text."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from clawfedora import chat_github, chat_projects
from clawfedora.project_common import read_json, write_json

PROJECT_ID = "github-project"
REPO = "example/infraops"
BASE_SHA = "a" * 40


def _setup(tmp_path: Path, *, status: str = "COMPLETE") -> tuple[Path, Path]:
    runtime = tmp_path / "runtime"
    project = runtime / "projects" / PROJECT_ID
    (project / "context").mkdir(parents=True)
    (project / "intake").mkdir()
    (project / "deliverables" / "documentation").mkdir(parents=True)
    (project / "deliverables" / "documentation" / "README.md").write_text(
        "# Documentation réellement proposée\n", encoding="utf-8",
    )
    write_json(project / "project.json", {
        "project_id": PROJECT_ID, "status": status,
        "title": "Projet GitHub",
    })
    return runtime, project


def test_command_parser_recognizes_github_but_never_model_tool_calls() -> None:
    name, args = chat_projects.parse_command(
        "!github pr example/infraops " + BASE_SHA + " atelier/readme deliverables/documentation"
    ) or ("", "")
    assert name == "github" and "atelier/readme" in args
    assert chat_projects.parse_command("/github aide") == ("github", "aide")
    assert chat_projects.parse_command("publie cette PR GitHub") is None


def test_help_needs_no_project_and_does_not_contact_network(tmp_path: Path) -> None:
    assert "GITHUB_TOKEN" in chat_github.run(tmp_path, None, "aide", local=True)
    result = chat_github.run(tmp_path, None, "depot Demo", local=True)
    assert "sélectionner un projet" in result


def test_repo_preview_then_single_approved_private_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, project = _setup(tmp_path)
    plan = chat_github.run(runtime, PROJECT_ID, "depot BankFlow", local=True)
    assert "privé" in plan
    pending = read_json(project / "context/github-repo-pending.json")
    assert pending["state"] == "PREVIEWED"
    calls: list[dict[str, Any]] = []

    def fake(name: str, **kwargs: Any) -> dict[str, Any]:
        calls.append({"name": name, **kwargs})
        return {"url": "https://github.com/example/BankFlow"}

    monkeypatch.setattr(chat_github, "create_repository", fake)
    digest = pending["manifest_sha256"]
    assert "choisir un rôle local" in chat_github.run(
        runtime, PROJECT_ID, f"creer BankFlow {digest}", local=False,
    )
    assert calls == []
    assert "créé" in chat_github.run(
        runtime, PROJECT_ID, f"creer BankFlow {digest}", local=True,
    )
    assert calls == [{
        "name": "BankFlow", "approve_name": "BankFlow", "approve_manifest": digest,
    }]
    assert read_json(project / "context/github-repo-pending.json")["state"] == "CREATED"
    assert "déjà tenté" in chat_github.run(
        runtime, PROJECT_ID, f"creer BankFlow {digest}", local=True,
    )


def test_pr_plan_requires_completed_project(tmp_path: Path) -> None:
    runtime, _project = _setup(tmp_path, status="IN_PROGRESS")
    report = chat_github.run(
        runtime, PROJECT_ID,
        f"pr {REPO} {BASE_SHA} atelier/readme deliverables/documentation",
        local=True,
    )
    assert "projet non terminé" in report


def test_draft_pr_can_only_be_published_by_exact_user_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, project = _setup(tmp_path)
    report = chat_github.run(
        runtime, PROJECT_ID,
        f"pr {REPO} {BASE_SHA} atelier/readme deliverables/documentation",
        local=True,
    )
    assert "PR brouillon prévue" in report
    pending = read_json(project / "context/github-pr-pending.json")
    digest = pending["manifest_sha256"]
    called: list[dict[str, Any]] = []

    def fake(**kwargs: Any) -> dict[str, Any]:
        called.append(kwargs)
        return {"url": "https://github.com/example/infraops/pull/42"}

    monkeypatch.setattr(chat_github, "publish_draft", fake)
    assert "choisir un rôle local" in chat_github.run(
        runtime, PROJECT_ID, f"publier {REPO} {digest}", local=False,
    )
    assert called == []
    assert "approbation différente" in chat_github.run(
        runtime, PROJECT_ID, f"publier {REPO} {'b' * 64}", local=True,
    )
    assert called == []
    approved = chat_github.run(
        runtime, PROJECT_ID, f"publier {REPO} {digest}", local=True,
    )
    assert "brouillon créée" in approved
    assert called[0]["approve_manifest"] == digest
    assert called[0]["repo"] == REPO
    assert called[0]["base_sha"] == BASE_SHA
    assert called[0]["changes"] == project / "deliverables/documentation"
    assert read_json(project / "context/github-pr-pending.json")["state"] == "CREATED"
    assert "déjà tenté" in chat_github.run(
        runtime, PROJECT_ID, f"publier {REPO} {digest}", local=True,
    )


def test_snapshot_audit_never_contacts_github(tmp_path: Path) -> None:
    runtime, project = _setup(tmp_path)
    source = project / "intake/GitHub-example-infraops-aaaa"
    source.mkdir()
    write_json(source / ".source-provenance.json", {
        "provider": "github", "repository": REPO,
        "commit": BASE_SHA, "skipped": 2, "file_count": 1,
    })
    (source / "README.md").write_text("# Example\n", encoding="utf-8")
    result = chat_github.run(runtime, PROJECT_ID, "audit", local=True)
    assert "Audit local" in result and "GitHub-example" in result
    assert "CI" in result and "pas vérifiés" in result or "ne sont pas vérifiés" in result


def test_no_silent_retry_after_remote_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, project = _setup(tmp_path)
    chat_github.run(runtime, PROJECT_ID, "depot BankFlow", local=True)
    digest = read_json(project / "context/github-repo-pending.json")["manifest_sha256"]

    def refused(*_args: Any, **_kw: Any) -> dict[str, Any]:
        raise ValueError("API fail")

    monkeypatch.setattr(chat_github, "create_repository", refused)
    first = chat_github.run(runtime, PROJECT_ID, f"creer BankFlow {digest}", local=True)
    assert "incomplète" in first
    assert read_json(project / "context/github-repo-pending.json")["state"] == "ATTEMPTED"
    again = chat_github.run(runtime, PROJECT_ID, f"creer BankFlow {digest}", local=True)
    assert "déjà tenté" in again
