"""Offline tests for explicit, versioned GitHub refreshes; no real GitHub calls."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from clawfedora import github_refresh, source_connectors
from clawfedora.project_cloud import consent_path, sources_digest
from clawfedora.project_common import read_json, sha256_file
from clawfedora.project_intake import create_project, validate_input_integrity
from clawfedora.project_roadmap import initialize

ROOT = Path(__file__).resolve().parents[1]
FIRST, SECOND, THIRD = "a" * 40, "b" * 40, "c" * 40
REPO = "example/OpsDesk"


def versions() -> dict[str, dict[str, str]]:
    return {
        FIRST: {"README.md": "v1\n", "infra/main.tf": "terraform v1\n"},
        SECOND: {"README.md": "v2\n", "infra/main.tf": "terraform v1\n",
                 "infra/new.tf": "resource new\n"},
        THIRD: {"README.md": "v3\n", "infra/new.tf": "resource new\n"},
    }


def fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, dict[str, dict[str, str]]]:
    runtime = tmp_path / "runtime"
    request = tmp_path / "brief.md"
    request.write_text("Étudier un projet InfraOps.", encoding="utf-8")
    project = create_project(
        ROOT, runtime, "refresh-test", "Projet long", intake_items=[request]
    )
    content = versions()

    def fake_snapshot(path: Path, repository: str, commit: str) -> dict[str, Any]:
        assert repository == REPO
        for name, value in content[commit].items():
            target = path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(value, encoding="utf-8")
        return {
            "provider": "github", "repository": repository, "commit": commit,
            "file_count": len(content[commit]), "skipped": 0, "read_only": True,
        }

    monkeypatch.setattr(source_connectors, "_github_snapshot", fake_snapshot)
    imported = source_connectors.import_snapshot(
        ROOT, runtime, "refresh-test", github=REPO, commit=FIRST
    )
    assert imported["status"] == "IMPORTED"
    return runtime, project, content


def test_preview_and_apply_keep_intake_plan_and_proofs_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, project, _ = fixture(tmp_path, monkeypatch)
    original = read_json(project / "project.json")
    initial = (project / "intake" / ("GitHub-example-OpsDesk-" + FIRST[:12]))
    old_hash = sha256_file(initial / "README.md")
    initialize(project, {"milestones": [
        {"id": "step-01", "title": "Comprendre", "depends_on": []},
        {"id": "step-02", "title": "Provisionner", "depends_on": ["step-01"]},
    ]}, apply=True)
    (project / "context" / "operator-proofs").mkdir(parents=True)
    proof = project / "context/operator-proofs" / "manual.txt"
    proof.write_text("declared, not certified")
    (project / "context/project_plan.json").write_text('{"tasks":[]}')
    first_consent_fingerprint = sources_digest(project)

    preview = github_refresh.refresh(runtime, "refresh-test", REPO, SECOND)
    assert preview["status"] == "PREVIEW"
    assert preview["agent_context"] == "INITIAL_INTAKE_UNCHANGED"
    assert [(e["path"], e["change"]) for e in preview["changes"]] == [
        ("README.md", "modified"), ("infra/new.tf", "added")
    ]
    assert preview["needs_requalification"]["milestones_to_review"] == [
        "step-01", "step-02"
    ]
    assert preview["needs_requalification"]["plan_to_review"] is True
    assert preview["needs_requalification"]["operator_proofs_to_review"] is True
    assert github_refresh.inspect(project) == []
    assert sources_digest(project) == first_consent_fingerprint

    with pytest.raises(ValueError, match="empreinte"):
        github_refresh.refresh(
            runtime, "refresh-test", REPO, SECOND, approve="0" * 64, apply=True
        )
    assert github_refresh.inspect(project) == []

    applied = github_refresh.refresh(
        runtime, "refresh-test", REPO, SECOND,
        approve=preview["approve_sha256"], apply=True,
    )
    assert applied["status"] == "RECORDED"
    assert applied["remote_writes"] is False
    status = github_refresh.inspect(project)[0]
    assert status["initial_commit"] == FIRST and status["current_commit"] == SECOND
    assert status["revision_count"] == 1
    assert status["needs_requalification"]["verification"] == "NOT_VERIFIED"
    assert sources_digest(project) != first_consent_fingerprint
    assert read_json(project / "project.json") == original
    assert validate_input_integrity(project) == []
    assert sha256_file(initial / "README.md") == old_hash
    assert proof.read_text() == "declared, not certified"
    assert (project / "context/project_plan.json").read_text() == '{"tasks":[]}'


def test_second_revision_and_deletion_are_versioned_without_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, project, _ = fixture(tmp_path, monkeypatch)
    for commit in (SECOND, THIRD):
        preview = github_refresh.refresh(runtime, "refresh-test", REPO, commit)
        github_refresh.refresh(
            runtime, "refresh-test", REPO, commit,
            approve=preview["approve_sha256"], apply=True,
        )
    status = github_refresh.inspect(project)[0]
    assert status["revision_count"] == 2
    assert status["previous_commit"] == SECOND
    assert status["current_commit"] == THIRD
    assert {"path": "infra/main.tf", "change": "removed"} in status["changes"]
    assert (
        project / github_refresh.STORE
        / github_refresh._directory(project, REPO).name / SECOND / "files/README.md"
    ).read_text() == "v2\n"
    with pytest.raises(ValueError, match="déjà enregistré"):
        github_refresh.refresh(runtime, "refresh-test", REPO, SECOND)


def test_cloud_consent_and_tampering_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, project, _ = fixture(tmp_path, monkeypatch)
    preview = github_refresh.refresh(runtime, "refresh-test", REPO, SECOND)
    path = consent_path(runtime, project)
    path.parent.mkdir(parents=True)
    path.write_text('{"authorization":"operator"}')
    with pytest.raises(ValueError, match="révoquer l'accord cloud"):
        github_refresh.refresh(
            runtime, "refresh-test", REPO, SECOND,
            approve=preview["approve_sha256"], apply=True,
        )
    path.unlink()
    github_refresh.refresh(
        runtime, "refresh-test", REPO, SECOND,
        approve=preview["approve_sha256"], apply=True,
    )
    stored = github_refresh._directory(project, REPO) / SECOND / "files/README.md"
    stored.write_text("tampered\n")
    with pytest.raises(ValueError, match="modifié"):
        github_refresh.inspect(project)
    with pytest.raises(ValueError, match="modifié"):
        github_refresh.refresh(runtime, "refresh-test", REPO, THIRD)


def test_secret_in_new_commit_is_refused_without_partial_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, project, content = fixture(tmp_path, monkeypatch)
    content[SECOND]["README.md"] = "token ghp_" + "X" * 40
    with pytest.raises(ValueError, match="secret|sensible"):
        github_refresh.refresh(runtime, "refresh-test", REPO, SECOND)
    assert github_refresh.inspect(project) == []
    assert validate_input_integrity(project) == []


def test_other_repository_mismatched_sha_and_bad_preview_are_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, project, _ = fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="non lié"):
        github_refresh.refresh(runtime, "refresh-test", "else/Repo", SECOND)
    with pytest.raises(ValueError, match="SHA Git"):
        github_refresh.refresh(runtime, "refresh-test", REPO, "main")
    with pytest.raises(ValueError, match="empreinte"):
        github_refresh.refresh(runtime, "refresh-test", REPO, SECOND, apply=True)
    preview = github_refresh.refresh(runtime, "refresh-test", REPO, SECOND)
    with pytest.raises(ValueError, match="empreinte"):
        github_refresh.refresh(
            runtime, "refresh-test", REPO, THIRD,
            approve=preview["approve_sha256"], apply=True,
        )
    assert github_refresh.inspect(project) == []


def test_truncated_tree_and_symlink_are_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, project, _ = fixture(tmp_path, monkeypatch)

    def incomplete(*_args: Any) -> Any:
        raise source_connectors.SourceImportError("arbre incomplet : importation refusée")

    monkeypatch.setattr(source_connectors, "_github_snapshot", incomplete)
    with pytest.raises(source_connectors.SourceImportError, match="incomplet"):
        github_refresh.refresh(runtime, "refresh-test", REPO, SECOND)
    assert github_refresh.inspect(project) == []
    path = github_refresh._directory(project, REPO)
    path.mkdir(parents=True)
    (path / "ledger.json").symlink_to(tmp_path / "foreign-ledger.json")
    with pytest.raises(ValueError, match="symbolique"):
        github_refresh.refresh(runtime, "refresh-test", REPO, SECOND)


def test_cli_preview_does_not_write_without_apply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    runtime, project, _ = fixture(tmp_path, monkeypatch)
    args = [
        "--runtime-root", str(runtime), "--project-id", "refresh-test",
        "--github", REPO, "--commit", SECOND,
    ]
    assert github_refresh.main(args) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "PREVIEW"
    assert github_refresh.inspect(project) == []
    assert github_refresh.main(args + ["--apply"]) == 2
    assert "REFUSED" in capsys.readouterr().out
