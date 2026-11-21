"""Offline tests for opt-in draft-only GitHub publication: no network credentials."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from clawfedora import github_pr

REPO = "example/infraops"
BASE_SHA = "a" * 40
BRANCH = "atelier/doc-quality"


def _stage(tmp_path: Path) -> Path:
    root = tmp_path / "proposal"
    (root / "docs").mkdir(parents=True)
    (root / "README.md").write_text("# InfraOps\n\nDescription\n", encoding="utf-8")
    (root / "docs/architecture.md").write_text("# Architecture\n", encoding="utf-8")
    return root


def _kwargs(root: Path) -> dict[str, Any]:
    return {
        "repo": REPO, "base": "main", "base_sha": BASE_SHA,
        "branch": BRANCH, "changes": root, "allow_workflows": False,
    }


def test_plan_is_offline_json_and_never_shows_content(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    result = github_pr.make_plan(**_kwargs(root))
    assert result["mode"] == "OFFLINE_DRY_RUN"
    assert len(result["files"]) == 2
    assert result["files"][0]["sha256"]
    assert "# InfraOps" not in json.dumps(result)
    assert result["draft_only"] is True
    assert "GITHUB_TOKEN" not in json.dumps(result)


@pytest.mark.parametrize("repo,sha,branch", [
    ("bad", BASE_SHA, BRANCH),
    ("example/infraops", "bad", BRANCH),
    ("example/infraops", BASE_SHA, "main"),
    ("example/infraops", BASE_SHA, "atelier/../unsafe"),
])
def test_invalid_target_refused(
    tmp_path: Path, repo: str, sha: str, branch: str,
) -> None:
    root = _stage(tmp_path)
    with pytest.raises(github_pr.PublicationError):
        github_pr.make_plan(repo=repo, base="main", base_sha=sha, branch=branch,
                            changes=root, allow_workflows=False)


@pytest.mark.parametrize("bad_path", [
    ".env", "nested/.env.production", "data/private.key", "terraform.tfstate",
    "notes/.source-provenance.json", "secrets/token.txt",
])
def test_secret_filenames_refused(tmp_path: Path, bad_path: str) -> None:
    root = _stage(tmp_path)
    path = root / bad_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("fake", encoding="utf-8")
    with pytest.raises(github_pr.PublicationError):
        github_pr.collect_files(root)


def test_private_key_or_token_content_refused(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    (root / "docs/architecture.md").write_text(
        "-----BEGIN OPENSSH PRIVATE KEY-----\n", encoding="utf-8",
    )
    with pytest.raises(github_pr.PublicationError):
        github_pr.collect_files(root)


def test_workflow_requires_additional_flag(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    folder = root / ".github/workflows"
    folder.mkdir(parents=True)
    (folder / "docs.yml").write_text("name: Check\n", encoding="utf-8")
    with pytest.raises(github_pr.PublicationError, match="allow-workflows"):
        github_pr.collect_files(root)
    assert len(github_pr.collect_files(root, allow_workflows=True)) == 3


def test_symlink_refused_before_any_publication(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    external = tmp_path / "private.txt"
    external.write_text("private stuff", encoding="utf-8")
    (root / "docs/leak.txt").symlink_to(external)
    with pytest.raises(github_pr.PublicationError, match="symbolique"):
        github_pr.collect_files(root)


def test_snapshots_cannot_be_written_directly(tmp_path: Path) -> None:
    root = _stage(tmp_path)
    (root / ".source-provenance.json").write_text('{"provider":"github"}', encoding="utf-8")
    with pytest.raises(github_pr.PublicationError):
        github_pr.collect_files(root)


def test_publish_needs_explicit_repository_and_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _stage(tmp_path)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    def never(**_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("No remote request permitted")
    monkeypatch.setattr(github_pr, "_api_request", never)
    with pytest.raises(github_pr.PublicationError, match="approbation"):
        github_pr.publish_draft(**_kwargs(root), title="Example proposal",
                                body="Description adequate", approve_repo="wrong/repo")
    with pytest.raises(github_pr.PublicationError, match="GITHUB_TOKEN"):
        github_pr.publish_draft(**_kwargs(root), title="Example proposal",
                                body="Description adequate", approve_repo=REPO)


def test_remote_sha_mismatch_is_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _stage(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "dummy-not-real-token")
    calls: list[tuple[str, str]] = []

    def fake(path: str, *, method: str, token: str,
             payload: dict[str, Any] | None = None) -> dict[str, Any]:
        calls.append((method, path))
        assert token == "dummy-not-real-token"
        if path.endswith("/git/ref/heads/main"):
            return {"object": {"sha": "b" * 40}}
        return {"default_branch": "main", "archived": False}

    monkeypatch.setattr(github_pr, "_api_request", fake)
    with pytest.raises(github_pr.PublicationError, match="modifiée"):
        github_pr.publish_draft(**_kwargs(root), title="Example proposal",
                                body="Description adequate", approve_repo=REPO)
    assert calls == [
        ("GET", "/repos/example/infraops"),
        ("GET", "/repos/example/infraops/git/ref/heads/main"),
    ]


def test_full_publication_is_single_commit_and_draft_pr_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _stage(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "dummy-not-real-token")
    calls: list[tuple[str, str, dict[str, Any] | None]] = []
    def fake(path: str, *, method: str, token: str,
             payload: dict[str, Any] | None = None) -> dict[str, Any]:
        assert token == "dummy-not-real-token"
        calls.append((method, path, payload))
        if method == "GET" and path == "/repos/example/infraops":
            return {"default_branch": "main", "archived": False}
        if path.endswith("git/ref/heads/main"):
            return {"object": {"sha": BASE_SHA}}
        if path.endswith("/git/commits/" + BASE_SHA):
            return {"tree": {"sha": "b" * 40}}
        if path.endswith("/git/blobs"):
            return {"sha": "c" * 40}
        if path.endswith("/git/trees"):
            return {"sha": "d" * 40}
        if path.endswith("/git/commits"):
            return {"sha": "e" * 40}
        if path.endswith("/git/refs"):
            assert payload == {"ref": "refs/heads/" + BRANCH, "sha": "e" * 40}
            return {"ref": "refs/heads/" + BRANCH}
        if path.endswith("/pulls"):
            return {
                "html_url": "https://github.com/example/infraops/pull/12",
                "draft": True,
            }
        raise AssertionError(f"unexpected API: {path}")

    monkeypatch.setattr(github_pr, "_api_request", fake)
    result = github_pr.publish_draft(
        **_kwargs(root), title="Create documentation",
        body="New detailed documentation", approve_repo=REPO,
    )
    assert result["draft"] is True
    assert result["mode"] == "DRAFT_PR_CREATED"
    writes = [row for row in calls if row[0] == "POST"]
    assert len(writes) == 6  # two blobs, one tree, commit, reference, draft PR
    pr_body = writes[-1][2]
    assert pr_body is not None
    assert pr_body["draft"] is True
    assert pr_body["base"] == "main"
    assert not any(call[0] in ("PATCH", "PUT", "DELETE") for call in calls)
    assert "dummy-not-real-token" not in json.dumps(result)


def test_dry_run_cli_needs_no_title_body_approval_or_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _stage(tmp_path)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert github_pr.main([
        "--repo", REPO, "--base-sha", BASE_SHA,
        "--branch", BRANCH, "--changes", str(root),
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["mode"] == "OFFLINE_DRY_RUN"


def test_pr_must_be_confirmed_draft_not_normal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _stage(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "dummy-not-real-token")
    def fake(path: str, *, method: str, token: str,
             payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if path == "/repos/example/infraops":
            return {"default_branch": "main", "archived": False}
        if path.endswith("git/ref/heads/main"):
            return {"object": {"sha": BASE_SHA}}
        if path.endswith("/git/commits/" + BASE_SHA):
            return {"tree": {"sha": "b" * 40}}
        if path.endswith("/git/blobs"):
            return {"sha": "c" * 40}
        if path.endswith("/git/trees"):
            return {"sha": "d" * 40}
        if path.endswith("/git/commits"):
            return {"sha": "e" * 40}
        if path.endswith("/pulls"):
            return {"html_url": "https://github.com/example/infraops/pull/12",
                    "draft": False}
        return {"ref": "refs/heads/" + BRANCH}
    monkeypatch.setattr(github_pr, "_api_request", fake)
    with pytest.raises(github_pr.PublicationError, match="brouillon"):
        github_pr.publish_draft(**_kwargs(root), title="Example proposal",
                                body="Description adequate", approve_repo=REPO)
