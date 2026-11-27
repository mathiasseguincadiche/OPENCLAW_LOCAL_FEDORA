"""Relate workflow definitions and official run metadata without following links."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

import pytest

from clawfedora import github_document_ci as audit
from clawfedora import github_document_links as links
from clawfedora import source_connectors as sources

COMMIT = "a" * 40
OLDER = "c" * 40
TREE = "b" * 40
REPO = "example/atlas"
API = f"/repos/{REPO}/actions/runs"
CI = ".github/workflows/ci.yml"


def _run(
    ident: int, *, sha: str = COMMIT, path: str = CI, status: str = "completed",
    conclusion: str | None = "success",
) -> dict[str, Any]:
    return {"id": ident, "head_sha": sha, "repository": {"full_name": REPO},
            "path": path, "workflow_id": 7, "event": "push", "run_attempt": 2,
            "status": status, "conclusion": conclusion}


def _files(monkeypatch: pytest.MonkeyPatch) -> None:
    documents = {
        CI: b"name: CI\non: ['push', 'pull_request']\njobs:\n  smoke: {}\n",
        ".github/workflows/manual.yaml": b"on: workflow_dispatch\njobs:\n  manual: {}\n",
        ".github/workflows/broken.yml": b"on: workflow_dispatch\njobs: [wrong]\n",
        "README.md": (
            b"[Current](https://github.com/example/atlas/actions/runs/1)\n\n"
            b"[Past](https://github.com/example/atlas/actions/runs/9/job/55?redact=token-test)\n\n"
            b"[Foreign](https://github.com/foreign/atlas/actions/runs/1)\n\n"
            b"[Missing](https://github.com/example/atlas/actions/runs/8)\n"
        ),
    }
    blobs = {
        hashlib.sha1(f"blob {len(raw)}\0".encode() + raw, usedforsecurity=False).hexdigest(): raw
        for raw in documents.values()
    }
    reverse = {raw: sha for sha, raw in blobs.items()}
    entries = [{"path": path, "mode": "100644", "type": "blob", "sha": reverse[raw]}
               for path, raw in documents.items()]
    monkeypatch.setattr(sources, "_github_tree", lambda *_: (TREE, {"sha": TREE, "tree": entries}))
    monkeypatch.setattr(links, "_github_blob", lambda _, sha: blobs[sha])


def test_workflows_runs_and_documented_proofs_are_distinct(monkeypatch: pytest.MonkeyPatch) -> None:
    _files(monkeypatch)
    calls = []

    def get(path: str) -> dict[str, Any]:
        calls.append(path)
        if path.startswith(f"{API}?head_sha={COMMIT}"):
            return {"total_count": 3, "workflow_runs": [
                _run(1), _run(2, status="in_progress", conclusion=None),
                _run(3, path=".github/workflows/no-longer-in-tree.yml", conclusion="failure"),
            ]}
        if path == f"{API}/9":
            return _run(9, sha=OLDER)
        if path == f"{API}/8":
            raise sources.SourceImportError("indisponible")
        raise AssertionError(path)

    monkeypatch.setattr(sources, "_github", get)
    report = audit.audit_github(REPO, COMMIT, [])
    assert report["commit"] == COMMIT
    assert report["run_counts"] == {
        "observed_success": 1, "observed_pending": 1, "observed_non_success": 1,
    }
    assert report["reference_counts"] == {
        "observed_success": 1, "different_revision": 1,
        "other_repository_not_checked": 1, "run_not_verified": 1,
    }
    assert report["unmatched_run_ids"] == [3]
    definitions = {item["path"]: item for item in report["workflow_definitions"]}
    assert definitions[CI]["observed_run_ids"] == [1, 2]
    assert definitions[CI]["triggers"] == ["pull_request", "push"]
    assert definitions[CI]["job_ids"] == ["smoke"]
    assert definitions[".github/workflows/manual.yaml"]["run_coverage"] == "no_run_observed"
    broken = definitions[".github/workflows/broken.yml"]
    assert broken["definition_status"] == "invalid_or_unsupported"
    assert report["documents_missing"] == ["STATUS.md"]
    assert report["documents_inspected"] == ["README.md"]
    assert "token-test" not in repr(report)
    assert len(calls) == 3


@pytest.mark.parametrize("fault", ["other_sha", "other_repo", "duplicates", "incomplete", "too_many"])
def test_run_list_fails_closed_on_unreliable_coverage(
    monkeypatch: pytest.MonkeyPatch, fault: str,
) -> None:
    rows = [_run(1)]
    count = 1
    if fault == "other_sha":
        rows = [_run(1, sha=OLDER)]
    elif fault == "other_repo":
        rows[0]["repository"] = {"full_name": "foreign/atlas"}
    elif fault == "duplicates":
        rows = [_run(1), _run(1)]
        count = 2
    elif fault == "incomplete":
        count = 2
    else:
        count = audit.MAX_RUNS + 1
    monkeypatch.setattr(sources, "_github", lambda _: {"total_count": count, "workflow_runs": rows})
    with pytest.raises(ValueError):
        audit._runs(REPO, COMMIT)


def test_exact_sha_pagination_does_not_stop_at_the_first_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def get(path: str) -> dict[str, Any]:
        assert f"?head_sha={COMMIT}&per_page=100" in path
        rows = [_run(n) for n in range(1, 101)] if path.endswith("page=1") else [_run(101)]
        return {"total_count": 101, "workflow_runs": rows}

    monkeypatch.setattr(sources, "_github", get)
    assert len(audit._runs(REPO, COMMIT)) == 101


@pytest.mark.skipif(os.name != "posix", reason="mode privé POSIX requis")
def test_cli_saves_only_to_a_new_private_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    tmp_path.chmod(0o700)
    monkeypatch.setattr(audit, "audit_github", lambda *_, **__: {"runs": []})
    output = tmp_path / "ci.json"
    args = ["--github", REPO, "--commit", COMMIT, "--output", str(output)]
    assert audit.main(args) == 0
    assert output.stat().st_mode & 0o777 == 0o600
    assert audit.main(args) == 2
