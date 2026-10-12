"""Private CI proof: exact official egress, fail-closed auth, no credential leaks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from clawfedora import ci_private_evidence as private
from clawfedora.ci_evidence import ProofRefused

SHA = "a" * 40
TOKEN = "ghp_" + "x" * 40


def _token(tmp_path: Path) -> Path:
    path = tmp_path / "forge.token"
    path.write_text(TOKEN + "\n", encoding="ascii")
    path.chmod(0o600)
    return path


def test_private_token_file_is_verified_without_leaking(tmp_path: Path) -> None:
    path = _token(tmp_path)
    assert private.read_operator_token(path) == TOKEN
    path.chmod(0o644)
    with pytest.raises(ProofRefused, match="0600"):
        private.read_operator_token(path)
    path.chmod(0o600)
    alias = tmp_path / "linked.token"
    alias.symlink_to(path)
    with pytest.raises(ProofRefused, match="lié"):
        private.read_operator_token(alias)
    path.write_text("abc\n", encoding="ascii")
    with pytest.raises(ProofRefused, match="malformé"):
        private.read_operator_token(path)


@pytest.mark.parametrize("provider,url,allowed", [
    ("github", "https://api.github.com/repos/org/private/actions/runs/12", True),
    ("github", "https://api.github.com/repos/org/private/actions/runs/12/jobs?per_page=100", True),
    ("gitlab", "https://gitlab.com/api/v4/projects/group%2Fprivate/pipelines/12", True),
    ("gitlab",
     "https://gitlab.com/api/v4/projects/group%2Fprivate/pipelines/12/jobs?per_page=100",
     True),
    ("github", "https://api.github.com.evil.test/repos/org/private/actions/runs/12", False),
    ("github", "http://api.github.com/repos/org/private/actions/runs/12", False),
    ("github", "https://api.github.com/repos/org/private/actions/runs/12/logs", False),
    ("github", "https://api.github.com/repos/org/private/actions/runs/12?access_token=abc", False),
    ("github", "https://api.github.com/repos/org/private/actions/runs/12/jobs?per_page=999", False),
    ("gitlab", "https://gitlab.com/api/v4/projects/org%2Frepo/pipelines/12/jobs/19/trace", False),
    ("gitlab",
     "https://gitlab.com/api/v4/projects/org%2Frepo/pipelines/12/jobs?per_page=100#secret",
     False),
])
def test_authenticated_egress_strict_allowlist(
    provider: str, url: str, allowed: bool,
) -> None:
    assert private._permitted(provider, url) is allowed


def test_private_proof_reuses_exact_commit_and_sanitizes_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[dict[str, Any]] = []

    class Reply:
        status = 200

        def __init__(self, payload: object):
            self.payload = json.dumps(payload).encode("utf-8")

        def __enter__(self) -> Reply:
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def read(self, size: int) -> bytes:
            return self.payload[:size]

    class Opener:
        def open(self, req: Any, timeout: int) -> Reply:
            headers = dict(req.header_items())
            captured.append({"url": req.full_url, "method": req.get_method(),
                             "headers": headers, "timeout": timeout})
            if "/jobs?" in req.full_url:
                return Reply({"total_count": 1, "jobs": [
                    {"id": 22, "name": "test", "status": "completed", "run_id": 42,
                     "conclusion": "success", "secret": TOKEN},
                ]})
            return Reply({"id": 42, "head_sha": SHA, "status": "completed",
                          "conclusion": "success", "sensitive": TOKEN})

    monkeypatch.setattr(private.urllib.request, "build_opener", lambda *_: Opener())
    report = private.verify_private_run(
        "github", "team/private", 42, SHA, token_file=_token(tmp_path), jobs=True
    )
    assert report["verdict"] == "VERIFIED_RUN_SUCCESS"
    assert report["jobs_count"] == 1
    assert report["provenance"] == "OFFICIAL_PRIVATE_FORGE_API_OPERATOR_AUTH"
    assert TOKEN not in json.dumps(report)
    assert all(x["method"] == "GET" and x["timeout"] == 12 for x in captured)
    assert len(captured) == 2
    assert all(dict(x["headers"]).get("Authorization") == "Bearer " + TOKEN
               for x in captured)


def test_private_api_refuses_wrong_sha_before_fetching_jobs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class Opener:
        def open(self, req: Any, timeout: int) -> Any:
            calls.append(req.full_url)

            class Reply:
                status = 200

                def __enter__(self) -> Reply:
                    return self

                def __exit__(self, *_args: object) -> None:
                    pass

                def read(self, _size: int) -> bytes:
                    return json.dumps({"id": 12, "head_sha": "b" * 40,
                                       "status": "completed",
                                       "conclusion": "success"}).encode()
            return Reply()

    monkeypatch.setattr(private.urllib.request, "build_opener", lambda *_: Opener())
    with pytest.raises(ProofRefused, match="SHA"):
        private.verify_private_run(
            "github", "org/private", 12, SHA, token_file=_token(tmp_path), jobs=True
        )
    assert calls == ["https://api.github.com/repos/org/private/actions/runs/12"]


def test_malformed_identity_refused_before_any_token_access(tmp_path: Path) -> None:
    with pytest.raises(ProofRefused, match="Dépôt"):
        private.verify_private_run(
            "github", "org/../internal", 1, SHA,
            token_file=tmp_path / "nonexistent.token",
        )


def test_cli_never_prints_private_token_even_on_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _token(tmp_path)

    def refuse(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise ProofRefused("Accès privé indisponible")

    monkeypatch.setattr(private, "verify_private_run", refuse)
    status = private.main([
        "--provider", "github", "--repo", "org/private",
        "--run-id", "1", "--commit", SHA, "--token-file", str(path),
    ])
    assert status == 2
    printed = capsys.readouterr().out
    assert "REFUSED" in printed and TOKEN not in printed


def test_gitlab_uses_private_token_not_github_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    got: list[dict[str, str]] = []

    class Opener:
        def open(self, req: Any, timeout: int) -> Any:
            got.append(dict(req.header_items()))

            class Reply:
                status = 200

                def __enter__(self) -> Reply:
                    return self

                def __exit__(self, *_args: object) -> None:
                    pass

                def read(self, size: int) -> bytes:
                    return b'{"id":42,"sha":"' + SHA.encode() + b'","status":"success"}'
            return Reply()

    monkeypatch.setattr(private.urllib.request, "build_opener", lambda *_: Opener())
    result = private._authenticated_reader("gitlab", TOKEN)(
        "https://gitlab.com/api/v4/projects/org%2Frepo/pipelines/42"
    )
    assert result["id"] == 42
    assert got[0].get("Private-token") == TOKEN
    assert not got[0].get("Authorization")
