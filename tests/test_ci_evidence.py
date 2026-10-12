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



def test_github_jobs_are_scoped_to_exact_verified_run(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def get(url: str) -> object:
        seen.append(url)
        if url.endswith("/jobs?per_page=100"):
            return {
                "total_count": 2,
                "jobs": [
                    {"id": 8, "name": "Lint", "run_id": 123, "status": "completed",
                     "conclusion": "success", "secret": "not-for-display"},
                    {"id": 4, "name": "Tests", "run_id": 123, "status": "completed",
                     "conclusion": "failure", "steps": [{"logs": "private"}]},
                ],
            }
        return {"id": 123, "head_sha": SHA, "status": "completed", "conclusion": "success"}

    monkeypatch.setattr(ci, "_json_get", get)
    proof = ci.verify_public_run_with_jobs("github", "octo/repo", 123, SHA)
    assert proof["jobs_count"] == 2
    assert [j["id"] for j in proof["jobs"]] == [4, 8]
    assert proof["jobs_scope"] == "public_job_metadata_only"
    assert "not-for-display" not in str(proof) and "private" not in str(proof)
    assert seen == [
        "https://api.github.com/repos/octo/repo/actions/runs/123",
        "https://api.github.com/repos/octo/repo/actions/runs/123/jobs?per_page=100",
    ]


def test_gitlab_jobs_metadata_is_bounded_and_has_parent_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def get(url: str) -> object:
        if url.endswith("/jobs?per_page=100"):
            return [{"id": 47, "name": "build", "status": "success",
                     "pipeline": {"id": 42, "sha": SHA}}]
        return {"id": 42, "sha": SHA, "status": "success"}

    monkeypatch.setattr(ci, "_json_get", get)
    proof = ci.verify_public_run_with_jobs("gitlab", "team/repo", 42, SHA)
    assert proof["jobs"] == [
        {"id": 47, "name": "build", "status": "success", "conclusion": None}
    ]


@pytest.mark.parametrize("provider,reply", [
    ("github", {"total_count": 101, "jobs": []}),
    ("github", {"total_count": 2, "jobs": [{"id": 1}]}),
    ("github", {"total_count": 0, "jobs": [None]}),
    ("github", {"total_count": 1, "jobs": [
        {"id": 1, "name": "bad", "run_id": 2, "status": "completed"},
    ]}),
    ("gitlab", [{"id": 2, "name": "job", "status": "success",
                 "pipeline": {"id": 99}}]),
    ("gitlab", [{"id": 2, "name": "job", "status": "success"}]),
])
def test_jobs_fail_closed_on_mismatch_or_partial_response(
    monkeypatch: pytest.MonkeyPatch, provider: str, reply: object,
) -> None:
    def get(url: str) -> object:
        if url.endswith("/jobs?per_page=100"):
            return reply
        if provider == "github":
            return {"id": 1, "head_sha": SHA, "status": "completed",
                    "conclusion": "success"}
        return {"id": 1, "sha": SHA, "status": "success"}

    monkeypatch.setattr(ci, "_json_get", get)
    with pytest.raises(ci.ProofRefused):
        ci.verify_public_run_with_jobs(provider, "octo/repo", 1, SHA)


def test_never_fetch_jobs_when_parent_run_sha_is_wrong(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []

    def get(url: str) -> object:
        seen.append(url)
        return {"id": 123, "head_sha": "b" * 40,
                "status": "completed", "conclusion": "success"}

    monkeypatch.setattr(ci, "_json_get", get)
    with pytest.raises(ci.ProofRefused, match="SHA"):
        ci.verify_public_run_with_jobs("github", "octo/repo", 123, SHA)
    assert len(seen) == 1
