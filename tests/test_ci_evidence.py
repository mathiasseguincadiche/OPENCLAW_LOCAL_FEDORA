"""Official public CI evidence: pin repository, run ID and SHA; no token, no logs."""

from __future__ import annotations

import pytest

from clawfedora import ci_evidence as ci

SHA = "a" * 40


def test_github_success_is_bound_to_expected_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def get(url: str) -> dict[str, object]:
        seen.append(url)
        return {
            "id": 123,
            "head_sha": SHA,
            "status": "completed",
            "conclusion": "success",
            "secrets": "do not repeat me",
        }

    monkeypatch.setattr(ci, "_json_get", get)
    report = ci.verify_public_run("github", "octo/repo", 123, SHA)
    assert seen == ["https://api.github.com/repos/octo/repo/actions/runs/123"]
    assert report["verdict"] == "VERIFIED_RUN_SUCCESS"
    assert report["commit"] == SHA
    assert report["official_url"] == "https://github.com/octo/repo/actions/runs/123"
    assert report["scope"] == "pipeline_result_only"
    assert "do not repeat me" not in str(report)


def test_gitlab_project_path_is_encoded(monkeypatch: pytest.MonkeyPatch) -> None:
    urls: list[str] = []

    def get(url: str) -> dict[str, object]:
        urls.append(url)
        return {"id": 42, "sha": SHA, "status": "success"}

    monkeypatch.setattr(ci, "_json_get", get)
    report = ci.verify_public_run("gitlab", "group/subgroup/project", 42, SHA)
    assert urls == [
        "https://gitlab.com/api/v4/projects/group%2Fsubgroup%2Fproject/pipelines/42"
    ]
    assert report["verdict"] == "VERIFIED_RUN_SUCCESS"
    assert report["official_url"].endswith("/group/subgroup/project/-/pipelines/42")


@pytest.mark.parametrize(
    ("status", "conclusion", "verdict"),
    [
        ("completed", "failure", "RUN_NOT_SUCCESSFUL"),
        ("completed", "cancelled", "RUN_NOT_SUCCESSFUL"),
        ("in_progress", None, "PENDING"),
    ],
)
def test_github_does_not_invent_pass(
    monkeypatch: pytest.MonkeyPatch, status: str, conclusion: str | None,
    verdict: str
) -> None:
    monkeypatch.setattr(
        ci, "_json_get",
        lambda _: {"id": 12, "head_sha": SHA, "status": status, "conclusion": conclusion}
    )
    assert ci.verify_public_run("github", "octo/repo", 12, SHA)["verdict"] == verdict


@pytest.mark.parametrize(
    ("status", "verdict"),
    [
        ("running", "PENDING"),
        ("failed", "RUN_NOT_SUCCESSFUL"),
        ("canceled", "RUN_NOT_SUCCESSFUL"),
    ],
)
def test_gitlab_does_not_invent_pass(
    monkeypatch: pytest.MonkeyPatch, status: str, verdict: str
) -> None:
    monkeypatch.setattr(ci, "_json_get", lambda _: {"id": 8, "sha": SHA, "status": status})
    assert ci.verify_public_run("gitlab", "group/repo", 8, SHA)["verdict"] == verdict


@pytest.mark.parametrize(
    ("repo", "provider"),
    [
        ("octo/../secret", "github"),
        ("octo/repo/a", "github"),
        ("https://evil.com/repo", "github"),
        ("group/%2Fsecret/repo", "gitlab"),
        ("group//repo", "gitlab"),
        ("group/./repo", "gitlab"),
    ],
)
def test_bad_repository_cannot_change_the_egress_host(
    repo: str, provider: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        ci, "_json_get", lambda _: pytest.fail("Invalid repo must not trigger network")
    )
    with pytest.raises(ci.ProofRefused):
        ci.verify_public_run(provider, repo, 2, SHA)


def test_wrong_sha_or_run_identity_never_proves_success(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        ci, "_json_get",
        lambda _: {"id": 5, "head_sha": "b" * 40, "status": "completed",
                   "conclusion": "success"},
    )
    with pytest.raises(ci.ProofRefused, match="SHA"):
        ci.verify_public_run("github", "octo/repo", 5, SHA)
    monkeypatch.setattr(
        ci, "_json_get",
        lambda _: {"id": 6, "head_sha": SHA, "status": "completed", "conclusion": "success"}
    )
    with pytest.raises(ci.ProofRefused, match="Identifiant"):
        ci.verify_public_run("github", "octo/repo", 5, SHA)


def test_incomplete_sha_and_nonpositive_run_are_refused() -> None:
    for commit, run in [("a" * 7, 12), (SHA, 0), ("g" * 40, 12)]:
        with pytest.raises(ci.ProofRefused):
            ci.verify_public_run("github", "octo/repo", run, commit)


def test_no_arbitrary_external_fetch_and_no_credentials() -> None:
    with pytest.raises(ci.ProofRefused, match="Destination"):
        ci._json_get("https://evil.example/forward")
