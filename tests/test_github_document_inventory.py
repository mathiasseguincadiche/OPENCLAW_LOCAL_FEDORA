"""Inventory GitHub metadata without relying on an imported content snapshot."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from clawfedora import github_document_inventory as inventory
from clawfedora import source_connectors as sources
from clawfedora.notion_write import _digest

COMMIT = "a" * 40
TREE = "b" * 40
BLOB = "c" * 40
REPO = "example/atlas"


def _row(path: str, kind: str = "blob", mode: str = "100644") -> dict[str, str]:
    return {"path": path, "type": kind, "mode": mode, "sha": BLOB}


def test_remote_inventory_uses_exact_commit_and_fetches_only_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        _row("docs", "tree", "040000"), _row("README.md"), _row("docs/architecture.md"),
        _row("docs/diagrams/topology.svg"), _row(".github/workflows/ci.yml"),
        _row("evidence/check.json"), _row("LICENSE"), _row(".ENV.PRIVATE"),
        _row("docs/privé/notes.md"), _row("docs/private/hidden.svg"),
        _row("docs/escaped.md", mode="120000"), _row("subproject", "commit", "160000"),
        *(_row(f"src/module_{i}.py") for i in range(sources.MAX_FILES + 1)),
    ]
    calls = []

    def get(path: str) -> dict[str, Any]:
        calls.append(path)
        if path == f"/repos/{REPO}/commits/{COMMIT}":
            return {"sha": COMMIT, "commit": {"tree": {"sha": TREE}}}
        assert path == f"/repos/{REPO}/git/trees/{TREE}?recursive=1"
        return {"sha": TREE, "tree": rows, "truncated": False}

    monkeypatch.setattr(sources, "_github", get)
    result = inventory.inventory_github(REPO, COMMIT)
    assert len(calls) == 2
    assert result["commit"] == COMMIT and result["git_tree"] == TREE
    assert result["repository"] == REPO
    assert result["counts_by_category"] == {
        "documentation": 2, "documentation_asset": 1, "evidence": 1, "governance": 1,
        "technical": sources.MAX_FILES + 1, "workflow": 1,
    }
    assert result["excluded_entries"] == {"confidential_path": 3, "submodule": 1, "symlink": 1}
    assert "privé/" not in json.dumps(result, ensure_ascii=False)
    assert ".ENV.PRIVATE" not in json.dumps(result)
    signals = {row["id"]: row["paths"] for row in result["signals"]}
    assert signals["architecture_reference"] == ["docs/architecture.md"]
    rows.reverse()
    assert inventory.inventory_github(REPO, COMMIT) == result
    assert result["inventory_sha256"] == _digest(
        {key: value for key, value in result.items() if key != "inventory_sha256"}
    )


@pytest.mark.parametrize("failure", ["truncated", "commit", "tree", "duplicate", "invalid_path"])
def test_remote_inventory_refuses_incomplete_or_invalid_identity(
    monkeypatch: pytest.MonkeyPatch, failure: str,
) -> None:
    def get(path: str) -> dict[str, Any]:
        if "/commits/" in path:
            return {"sha": TREE if failure == "commit" else COMMIT,
                    "commit": {"tree": {"sha": TREE}}}
        entries = [_row("README.md")]
        if failure == "duplicate":
            entries.append(entries[0])
        if failure == "invalid_path":
            entries.append(_row("../README.md"))
        return {"sha": COMMIT if failure == "tree" else TREE,
                "tree": entries, "truncated": failure == "truncated"}

    monkeypatch.setattr(sources, "_github", get)
    with pytest.raises(ValueError):
        inventory.inventory_github(REPO, COMMIT)


@pytest.mark.skipif(shutil.which("git") is None, reason="Git local requis")
def test_local_inventory_uses_tracked_tree_even_with_a_dirty_working_directory(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(repo), "-c", "user.email=atlas@example.invalid",
             "-c", "user.name=Atlas", "-c", "commit.gpgsign=false", *args],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        ).stdout.strip()

    git("init", "-q")
    (repo / "README.md").write_text("# Atlas\n", encoding="utf-8")
    dir_path = repo / "docs"
    dir_path.mkdir()
    (dir_path / "guide.md").write_text("# Guide\n", encoding="utf-8")
    git("add", "--", "README.md", "docs/guide.md")
    git("commit", "-qm", "Atlas")
    commit = git("rev-parse", "HEAD")
    first = inventory.inventory_local(repo, commit)
    assert [row["path"] for row in first["files"]] == ["README.md", "docs/guide.md"]
    assert first["git_tree"] == git("rev-parse", "HEAD^{tree}")
    git("tag", "-a", "-m", "Tag Atlas", "atlas")
    with pytest.raises(ValueError, match="commit demandé"):
        inventory.inventory_local(repo, git("rev-parse", "atlas"))
    with pytest.raises(ValueError, match="40 caractères"):
        inventory.inventory_local(repo, "HEAD")

    (repo / "README.md").unlink()
    (repo / "draft.md").write_text("# Brouillon\n", encoding="utf-8")
    (dir_path / "guide.md").write_text("# Modifié\n", encoding="utf-8")
    assert inventory.inventory_local(dir_path, commit) == first


@pytest.mark.skipif(os.name != "posix", reason="mode POSIX privé requis")
def test_cli_writes_private_report_outside_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    tmp_path.chmod(0o700)
    output = tmp_path / "report.json"
    monkeypatch.setattr(sources, "_github_tree",
                        lambda *_: (TREE, {"sha": TREE, "tree": [_row("README.md")]}))
    args = ["--github", REPO, "--commit", COMMIT, "--output", str(output)]
    assert inventory.main(args) == 0
    assert output.stat().st_mode & 0o777 == 0o600
    assert json.loads(output.read_text())["git_tree"] == TREE
    assert inventory.main(args) == 2
    output.unlink()
    (tmp_path / ".git").touch()
    assert inventory.main(args) == 2 and not output.exists()
