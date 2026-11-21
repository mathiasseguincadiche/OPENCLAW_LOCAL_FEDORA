"""Behavioral tests of the in-progress GitHub PR workflow without remote writes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from clawfedora import chat_github, github_pr, project_work_pr, source_connectors
from clawfedora.project_common import read_json, write_json
from clawfedora.project_intake import create_project, validate_input_integrity
from clawfedora.project_roadmap import change, initialize

ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 40
REPO = "example/OpsDesk"
BRANCH = "atelier/milestone-04"


def _setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, dict[str, Any]]:
    runtime = tmp_path / "runtime"
    brief = tmp_path / "request.md"
    brief.write_text("Projet InfraOps évolutif", encoding="utf-8")
    project = create_project(
        ROOT, runtime, "opsdesk-lab", "OpsDesk", intake_items=[brief]
    )

    def snapshot(dest: Path, repo: str, commit: str) -> dict[str, Any]:
        assert (repo, commit) == (REPO, SHA)
        (dest / "infra").mkdir(parents=True)
        (dest / "infra/main.tf").write_text(
            'terraform { required_version = ">= 1.10" }\n', encoding="utf-8"
        )
        return {"provider": "github", "repository": repo, "commit": commit,
                "file_count": 1, "skipped": 0}

    monkeypatch.setattr(source_connectors, "_github_snapshot", snapshot)
    source_connectors.import_snapshot(
        ROOT, runtime, "opsdesk-lab", github=REPO, commit=SHA
    )
    initialize(project, {"milestones": [
        {"id": "step-03", "title": "Linux", "depends_on": []},
        {"id": "step-04", "title": "Terraform", "depends_on": ["step-03"]},
    ]}, apply=True)
    change(project, "step-04", "IN_PROGRESS", "Je prépare Terraform", apply=True)
    manifest = read_json(project / "project.json")
    manifest["status"] = "IN_PROGRESS"
    write_json(project / "project.json", manifest)
    stage = project / "work/github-pr/step-04/infra"
    stage.mkdir(parents=True)
    (stage / "main.tf").write_text(
        'terraform { required_version = ">= 1.12" }\n', encoding="utf-8"
    )
    params: dict[str, Any] = {
        "runtime": runtime, "project_id": "opsdesk-lab",
        "repo": REPO, "base_sha": SHA, "branch": BRANCH,
        "milestone_id": "step-04", "allowed": ["infra/main.tf"],
    }
    return runtime, project, params


def test_offline_preview_is_bounded_scoped_and_does_not_modify_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _runtime, project, params = _setup(tmp_path, monkeypatch)
    initial = (project / "intake" / ("GitHub-example-OpsDesk-" + SHA[:12])
               / "infra/main.tf").read_text()
    previews = project_work_pr.plan(**params)
    assert previews["mode"] == "OFFLINE_PREVIEW"
    assert previews["draft_only"] is True
    assert previews["verification"] == "NOT_VERIFIED"
    assert previews["files"][0]["change"] == "modified"
    assert "-terraform { required_version" in previews["diff"]
    assert "+terraform { required_version" in previews["diff"]
    assert not (project / "context/github-work-pr").exists()
    assert validate_input_integrity(project) == []
    assert (project / "intake" / ("GitHub-example-OpsDesk-" + SHA[:12])
            / "infra/main.tf").read_text() == initial
    assert read_json(project / "context/continuous_roadmap.json")["milestones"][1][
        "verification"
    ] == "NOT_VERIFIED"


def test_manifest_bound_to_base_jalon_and_exact_staged_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _runtime, project, p = _setup(tmp_path, monkeypatch)
    before = project_work_pr.plan(**p)["approval_sha256"]
    with pytest.raises(ValueError, match="SHA de base"):
        project_work_pr.plan(**{**p, "base_sha": "b" * 40})
    with pytest.raises(ValueError, match="fichiers proposés"):
        project_work_pr.plan(**{**p, "allowed": ["docs/guide.md"]})
    with pytest.raises(ValueError, match="chemin"):
        project_work_pr.plan(**{**p, "allowed": ["../secrets.txt"]})
    with pytest.raises(ValueError, match="jalon non actif"):
        project_work_pr.plan(**{**p, "milestone_id": "step-03"})
    staged = project / "work/github-pr/step-04/infra/main.tf"
    staged.write_text('terraform { required_version = ">= 1.13" }\n')
    assert before != project_work_pr.plan(**p)["approval_sha256"]


def test_secret_symlink_and_other_files_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _runtime, project, p = _setup(tmp_path, monkeypatch)
    staged = project / "work/github-pr/step-04/infra/main.tf"
    staged.write_text("ghp_" + "x" * 40)
    with pytest.raises(ValueError, match="secret|sensible"):
        project_work_pr.plan(**p)
    staged.write_text("normal\n")
    outside = tmp_path / "private.txt"
    outside.write_text("not for upload")
    (project / "work/github-pr/step-04/infra/link.tf").symlink_to(outside)
    with pytest.raises(ValueError, match="symbolique"):
        project_work_pr.plan(**p)


def test_one_time_publication_requires_human_manifest_and_local_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _runtime, project, p = _setup(tmp_path, monkeypatch)
    preview = project_work_pr.plan(**p)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with pytest.raises(ValueError, match="GITHUB_TOKEN"):
        project_work_pr.publish(
            **p, approve_repo=REPO, approve_sha256=preview["approval_sha256"],
            title="Terraform update", body="Checked proposal."
        )
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
    with pytest.raises(ValueError, match="approbation"):
        project_work_pr.publish(
            **p, approve_repo="other/repo", approve_sha256=preview["approval_sha256"],
            title="Terraform update", body="Checked proposal."
        )
    with pytest.raises(ValueError, match="modifié"):
        project_work_pr.publish(
            **p, approve_repo=REPO, approve_sha256="0" * 64,
            title="Terraform update", body="Checked proposal."
        )
    assert not (project / "context/github-work-pr").exists()


def test_remote_branch_duplicate_blocks_all_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _runtime, project, p = _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
    preview = project_work_pr.plan(**p)

    def existing(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"object": {"sha": SHA}}

    monkeypatch.setattr(github_pr, "_api_request", existing)
    with pytest.raises(ValueError, match="déjà présente"):
        project_work_pr.publish(
            **p, approve_repo=REPO, approve_sha256=preview["approval_sha256"],
            title="Terraform update", body="Checked proposal."
        )
    assert not (project / "context/github-work-pr").exists()


def test_draft_published_once_without_changing_milestone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _runtime, project, p = _setup(tmp_path, monkeypatch)
    preview = project_work_pr.plan(**p)
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
    calls: list[dict[str, Any]] = []

    def missing(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise github_pr.PublicationError("GitHub a refusé l'action HTTP 404")

    def publisher(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {"url": "https://github.com/example/OpsDesk/pull/42",
                "draft": True, "mode": "DRAFT_PR_CREATED"}

    monkeypatch.setattr(github_pr, "_api_request", missing)
    monkeypatch.setattr(github_pr, "publish_draft", publisher)
    result = project_work_pr.publish(
        **p, approve_repo=REPO, approve_sha256=preview["approval_sha256"],
        title="Terraform update", body="Checked proposal."
    )
    assert result["verification"] == "NOT_VERIFIED"
    assert result["draft"] is True
    assert len(calls) == 1
    assert calls[0]["approve_manifest"] == preview["publisher_manifest"]
    assert calls[0]["base_sha"] == SHA
    assert calls[0]["changes"] == project / "work/github-pr/step-04"
    assert calls[0]["allow_workflows"] is False
    assert read_json(project_work_pr._attempt(project, "step-04", BRANCH))["state"] == "CREATED"
    with pytest.raises(ValueError, match="déjà tentée"):
        project_work_pr.publish(
            **p, approve_repo=REPO, approve_sha256=preview["approval_sha256"],
            title="Terraform update", body="Checked proposal."
        )
    assert read_json(project / "context/continuous_roadmap.json")["milestones"][1][
        "verification"
    ] == "NOT_VERIFIED"


def test_ambiguous_remote_failure_fails_closed_and_does_not_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _runtime, project, p = _setup(tmp_path, monkeypatch)
    preview = project_work_pr.plan(**p)
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")

    def missing(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise github_pr.PublicationError("GitHub a refusé l'action HTTP 404")

    def failure(**_kwargs: Any) -> dict[str, Any]:
        raise github_pr.PublicationError("GitHub indisponible")

    monkeypatch.setattr(github_pr, "_api_request", missing)
    monkeypatch.setattr(github_pr, "publish_draft", failure)
    with pytest.raises(github_pr.PublicationError):
        project_work_pr.publish(
            **p, approve_repo=REPO, approve_sha256=preview["approval_sha256"],
            title="Terraform update", body="Checked proposal."
        )
    assert read_json(project_work_pr._attempt(project, "step-04", BRANCH))["state"] == (
        "ATTEMPTED"
    )
    with pytest.raises(ValueError, match="déjà tentée"):
        project_work_pr.publish(
            **p, approve_repo=REPO, approve_sha256=preview["approval_sha256"],
            title="Terraform update", body="Checked proposal."
        )


def test_chat_bridge_prepares_and_approves_active_work_without_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, project, p = _setup(tmp_path, monkeypatch)
    command = "travail-pr " + " ".join([
        REPO, SHA, BRANCH, "step-04", "infra/main.tf",
    ])
    preview = chat_github.run(runtime, "opsdesk-lab", command, local=True)
    assert "PR technique en cours" in preview
    pending = read_json(project / "context/github-work-pr-pending.json")
    assert pending["state"] == "PREVIEWED"
    digest = pending["approval_sha256"]
    calls: list[dict[str, Any]] = []

    def fake(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append({"args": args, **kwargs})
        return {"url": "https://github.com/example/OpsDesk/pull/99"}

    monkeypatch.setattr(project_work_pr, "publish", fake)
    assert "rôle local" in chat_github.run(
        runtime, "opsdesk-lab", f"publier-travail {REPO} {digest}", local=False
    )
    assert calls == []
    assert "approbation différente" in chat_github.run(
        runtime, "opsdesk-lab", f"publier-travail {REPO} {'0' * 64}", local=True
    )
    assert calls == []
    accepted = chat_github.run(
        runtime, "opsdesk-lab", f"publier-travail {REPO} {digest}", local=True
    )
    assert "brouillon" in accepted and "pull/99" in accepted
    assert calls[0]["approve_sha256"] == digest
    assert calls[0]["repo"] == REPO
    assert calls[0]["milestone_id"] == "step-04"
    assert read_json(project / "context/github-work-pr-pending.json")["state"] == "CREATED"
    assert "déjà tenté" in chat_github.run(
        runtime, "opsdesk-lab", f"publier-travail {REPO} {digest}", local=True
    )


def test_project_completion_gate_of_legacy_chat_pr_is_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, _project, _p = _setup(tmp_path, monkeypatch)
    command = f"pr {REPO} {SHA} atelier/traditional deliverables/docs"
    refused = chat_github.run(runtime, "opsdesk-lab", command, local=True)
    assert "projet non terminé" in refused
