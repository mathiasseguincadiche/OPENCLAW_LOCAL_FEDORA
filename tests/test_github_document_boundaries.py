"""Audit a declared audience without loading protected Git blobs."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

from clawfedora import github_document_boundaries as boundaries
from clawfedora import github_document_links as links
from clawfedora import source_connectors as sources

COMMIT = "a" * 40
TREE = "b" * 40
REPO = "example/atlas"
SIGNAL = "carnet fictif diffusion restreinte"
PASSAGE = (
    "Prepare the local lab then describe the observed result, expected outcome and "
    "reason for the configuration change before sharing the reference with the team."
)


def _blob(raw: bytes) -> str:
    return hashlib.sha1(f"blob {len(raw)}\0".encode() + raw, usedforsecurity=False).hexdigest()


def test_public_duplicates_and_boundary_findings_keep_private_details_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docs = {
        "docs/a.md": f"# Guide\n\n{PASSAGE}\n".encode(),
        "docs/b.md": f"# Guide\n\n{PASSAGE}\n".encode(),
        "docs/archives/c.md": (
            f"# Archive\n\n{PASSAGE.upper()}\n\n"
            f"[Interne](../private/NE-PAS-AFFICHER.md)\n\n{SIGNAL}\n"
        ).encode(),
        "docs/copied.md": b"protected copy",
        "internal/do-not-show.md": b"protected copy",
        "docs/private/NE-PAS-AFFICHER.md": b"hidden",
    }
    entries = [
        {"path": path, "type": "tree", "mode": "040000", "sha": "d" * 40}
        for path in ("docs", "docs/archives", "docs/private", "internal")
    ] + [
        {"path": path, "type": "blob", "mode": "100644", "sha": _blob(raw), "size": len(raw)}
        for path, raw in docs.items()
    ]
    monkeypatch.setattr(sources, "_github_tree",
                        lambda *_: (TREE, {"sha": TREE, "tree": entries}))
    wanted = {_blob(raw): raw for path, raw in docs.items() if path in {
        "docs/a.md", "docs/b.md", "docs/archives/c.md",
    }}
    calls = []

    def read(repository: str, sha: str) -> bytes:
        assert repository == REPO
        calls.append(sha)
        return wanted[sha]

    monkeypatch.setattr(links, "_github_blob", read)
    policy = {"schema": 1, "private_paths": ["internal"], "literals": [SIGNAL]}
    result = boundaries.audit_github(REPO, COMMIT, ["docs"], policy=policy)
    assert result["counts_by_code"] == {
        "identical_documents": 1, "private_literal_in_public_document": 1,
        "public_blob_matches_private_path": 1, "repeated_normalized_passage": 1,
        "restricted_paths_in_public_scope": 1, "restricted_target_reference": 1,
    }
    assert result["coverage"]["documents_not_read"] == ["docs/copied.md"]
    assert len(calls) == len(wanted) == 2
    data = repr(result)
    for private in (SIGNAL, PASSAGE, "NE-PAS-AFFICHER", "do-not-show", "protected copy"):
        assert private not in data
    passages = next(row for row in result["findings"] if row["code"] == "repeated_normalized_passage")
    assert any(location["context"] == "archive_or_template" for location in passages["locations"])
    entries.reverse()
    assert boundaries.audit_github(REPO, COMMIT, ["docs"], policy=policy) == result


def test_private_policy_rejects_traversal_and_short_or_repeated_markers() -> None:
    for paths, literals in [
        (["../private"], []), ([], ["court"]), ([], [SIGNAL, SIGNAL.upper()]),
    ]:
        with pytest.raises(ValueError):
            boundaries._policy({"schema": 1, "private_paths": paths, "literals": literals})


def test_inventory_guard_runs_before_document_blobs_are_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sources, "_github_tree", lambda *_: (TREE, {"sha": TREE, "tree": []}))

    def fail(*args: Any) -> bytes:
        raise AssertionError("lecture inattendue de blob")

    monkeypatch.setattr(links, "_github_blob", fail)
    with pytest.raises(ValueError, match="empreinte"):
        boundaries.audit_github(REPO, COMMIT, [], expected_inventory="0" * 64)


@pytest.mark.skipif(os.name != "posix", reason="mode privé POSIX requis")
def test_cli_requires_declared_audience_and_keeps_findings_private(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    tmp_path.chmod(0o700)
    monkeypatch.setattr(boundaries, "audit_github", lambda *_, **__: {"findings": [{}]})
    output = tmp_path / "review.json"
    args = ["--github", REPO, "--commit", COMMIT, "--output", str(output)]
    with pytest.raises(SystemExit, match="2"):
        boundaries.main(args)
    assert boundaries.main([*args, "--public-tree"]) == 1
    assert output.stat().st_mode & 0o777 == 0o600
    assert json.loads(output.read_text()) == {"findings": [{}]}
    assert boundaries.main([*args, "--public-tree"]) == 2
