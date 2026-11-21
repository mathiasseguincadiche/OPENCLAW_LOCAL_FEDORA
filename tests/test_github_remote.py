"""Offline GitHub governance tests: network is always mocked and never authorized."""

from __future__ import annotations

import json
from typing import Any

import pytest

from clawfedora import github_remote as remote

REPO = "example/infraops"


def test_create_default_is_private_and_dry_run_is_offline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(remote, "_request", lambda *_args, **_kw: pytest.fail("network"))
    plan = remote.create_plan("InfraOps", "Laboratoire")
    assert plan["mode"] == "OFFLINE_REPOSITORY_PLAN"
    assert plan["payload"]["private"] is True
    assert plan["payload"]["auto_init"] is True
    assert plan["remote_created"] is False
    assert len(plan["manifest_sha256"]) == 64


def test_create_rejects_missing_approval_before_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(remote, "_request", lambda *_args, **_kw: pytest.fail("network"))
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    with pytest.raises(remote.GitHubRemoteError, match="approbation"):
        remote.create_repository("InfraOps", approve_name="InfraOps",
                                 approve_manifest="invalid")
    public = remote.create_plan("InfraOps", visibility="public")
    with pytest.raises(remote.GitHubRemoteError, match="accord"):
        remote.create_repository(
            "InfraOps", visibility="public", approve_name="InfraOps",
            approve_manifest=public["manifest_sha256"],
        )


def test_create_private_repository_requires_current_owner_and_verified_privacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    calls: list[tuple[str, str]] = []
    def fake(path: str, *, method: str, token: str,
             data: dict[str, Any] | None = None) -> object:
        assert token == "test-token"
        calls.append((method, path))
        if path == "/user":
            return {"login": "example"}
        assert data is not None and data["private"] is True
        return {
            "full_name": "example/InfraOps", "private": True,
            "html_url": "https://github.com/example/InfraOps",
            "default_branch": "main",
        }
    monkeypatch.setattr(remote, "_request", fake)
    plan = remote.create_plan("InfraOps", "Laboratoire")
    result = remote.create_repository(
        "InfraOps", "Laboratoire", approve_name="InfraOps",
        approve_manifest=plan["manifest_sha256"],
    )
    assert result["mode"] == "REPOSITORY_CREATED"
    assert result["visibility"] == "private"
    assert calls == [("GET", "/user"), ("POST", "/user/repos")]
    assert "test-token" not in json.dumps(result)


def test_visibility_mismatch_fails_closed_after_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    def fake(path: str, *, method: str, token: str,
             data: dict[str, Any] | None = None) -> object:
        if path == "/user":
            return {"login": "example"}
        return {"full_name": "example/InfraOps", "private": False}
    monkeypatch.setattr(remote, "_request", fake)
    plan = remote.create_plan("InfraOps")
    with pytest.raises(remote.GitHubRemoteError, match="potentiellement créé"):
        remote.create_repository(
            "InfraOps", approve_name="InfraOps",
            approve_manifest=plan["manifest_sha256"],
        )


@pytest.mark.parametrize("bad", [
    "../repo", "a/b", "a", ".hidden", "hello world", "name\nnext",
])
def test_unsafe_names_rejected(bad: str) -> None:
    with pytest.raises(remote.GitHubRemoteError):
        remote.create_plan(bad)


def test_read_only_settings_audit_distinguishes_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    methods: list[str] = []
    def fake(path: str, *, method: str, token: str,
             data: dict[str, Any] | None = None) -> object:
        methods.append(method)
        if path == "/repos/example/infraops":
            return {"full_name": REPO, "private": True, "default_branch": "main"}
        if path.endswith("/rulesets"):
            raise remote.GitHubRemoteError("forbidden", status=403)
        return {"default_workflow_permissions": "read",
                "can_approve_pull_request_reviews": False}
    monkeypatch.setattr(remote, "_request", fake)
    result = remote.settings_audit(REPO)
    assert all(method == "GET" for method in methods)
    assert result["rulesets"]["state"] == "NOT_EVALUATED"
    assert result["rulesets"]["http_status"] == 403
    assert result["workflow_permissions"]["state"] == "OBSERVED"
    assert not any("RULESET_ACTIVE_VERIFIED" in str(v) for v in result.values())


def test_ruleset_plan_has_no_bypasses_and_requires_pr() -> None:
    plan = remote.policy_plan(REPO, "main", "pr-ruleset")
    assert plan["mode"] == "OFFLINE_POLICY_PLAN"
    assert plan["payload"]["enforcement"] == "active"
    assert plan["payload"]["bypass_actors"] == []
    rules = {item["type"] for item in plan["payload"]["rules"]}
    assert {"pull_request", "non_fast_forward", "deletion"} <= rules
    assert plan["payload"]["conditions"]["ref_name"]["include"] == ["refs/heads/main"]


def test_ruleset_requires_approval_and_does_not_duplicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    plan = remote.policy_plan(REPO, "main")
    with pytest.raises(remote.GitHubRemoteError, match="approuvé"):
        remote.apply_policy(REPO, "main", "pr-ruleset", approve_repo=REPO,
                            approve_manifest="other")
    requests: list[tuple[str, str]] = []
    def fake(path: str, *, method: str, token: str,
             data: dict[str, Any] | None = None) -> object:
        requests.append((method, path))
        if path == "/repos/example/infraops":
            return {"full_name": REPO, "default_branch": "main"}
        return [{"name": remote.RULESET, "enforcement": "active"}]
    monkeypatch.setattr(remote, "_request", fake)
    with pytest.raises(remote.GitHubRemoteError, match="déjà présent"):
        remote.apply_policy(
            REPO, "main", "pr-ruleset", approve_repo=REPO,
            approve_manifest=plan["manifest_sha256"],
        )
    assert all(method == "GET" for method, _ in requests)


def test_ruleset_provisioning_only_creates_new_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    calls: list[str] = []
    def fake(path: str, *, method: str, token: str,
             data: dict[str, Any] | None = None) -> object:
        calls.append(method)
        if path == "/repos/example/infraops":
            return {"full_name": REPO, "default_branch": "main"}
        if method == "GET":
            return []
        assert data is not None and data["enforcement"] == "active"
        return {"name": remote.RULESET, "enforcement": "active", "id": 19}
    monkeypatch.setattr(remote, "_request", fake)
    plan = remote.policy_plan(REPO, "main")
    result = remote.apply_policy(
        REPO, "main", "pr-ruleset", approve_repo=REPO,
        approve_manifest=plan["manifest_sha256"],
    )
    assert result["mode"] == "RULESET_CREATED_UNVERIFIED_ENFORCEMENT"
    assert calls == ["GET", "GET", "POST"]


def test_workflow_permissions_are_verified_after_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    calls: list[str] = []
    def fake(path: str, *, method: str, token: str,
             data: dict[str, Any] | None = None) -> object:
        calls.append(method)
        if path == "/repos/example/infraops":
            return {"full_name": REPO, "default_branch": "main"}
        if method == "PUT":
            assert data == {
                "default_workflow_permissions": "read",
                "can_approve_pull_request_reviews": False,
            }
            return None
        return {
            "default_workflow_permissions": "read",
            "can_approve_pull_request_reviews": False,
        }
    monkeypatch.setattr(remote, "_request", fake)
    plan = remote.policy_plan(REPO, "main", "workflow-readonly")
    result = remote.apply_policy(
        REPO, "main", "workflow-readonly", approve_repo=REPO,
        approve_manifest=plan["manifest_sha256"],
    )
    assert result["mode"] == "WORKFLOW_READONLY_VERIFIED"
    assert calls == ["GET", "PUT", "GET"]


def test_cli_preview_never_reads_token_or_connects(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(remote, "_request", lambda *_args, **_kw: pytest.fail("network"))
    assert remote.main(["create", "--name", "BankFlow"]) == 0
    assert json.loads(capsys.readouterr().out)["visibility"] == "private"
    assert remote.main(["policy", "--repo", REPO]) == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "OFFLINE_POLICY_PLAN"
