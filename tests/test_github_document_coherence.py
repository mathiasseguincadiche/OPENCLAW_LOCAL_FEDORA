"""Check pinned documentary declarations against Git blobs and files."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from clawfedora import github_document_coherence as coherence
from clawfedora import github_document_links as links
from clawfedora import source_connectors as sources

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "a" * 40
TREE = "b" * 40
REPOSITORY = "example/atlas"


def _selector(path: str, mode: str, *keys: str) -> dict[str, Any]:
    return {"path": path, "format": mode, "select": list(keys)}


def _contract() -> str:
    return json.dumps({"schema": 1, "checks": [
        {"id": "product", "kind": "version", "authority": _selector("VERSION", "text"),
         "declarations": [_selector("pyproject.toml", "toml", "project", "version"),
                          _selector("README.md", "markdown_table", "Active", "Plateforme")]},
        {"id": "launcher", "kind": "path", "document": "README.md", "target": "scripts/setup.sh"},
    ]})


@pytest.mark.skipif(shutil.which("git") is None, reason="Git requis pour la recette locale")
def test_local_report_distinguishes_document_drift_and_missing_script(tmp_path: Path) -> None:
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(tmp_path), "-c", "user.name=Atlas",
             "-c", "user.email=atlas@example.invalid", "-c", "commit.gpgsign=false", *args],
            check=True, capture_output=True, text=True,
        ).stdout.strip()

    git("init", "-q")
    (tmp_path / ".github").mkdir()
    (tmp_path / coherence.DEFAULT_CONTRACT).write_text(_contract(), encoding="utf-8")
    (tmp_path / "VERSION").write_text("1.2.3\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "1.2.3"\n', encoding="utf-8")
    readme = tmp_path / "README.md"
    readme.write_text(
        "# Atlas\n\n## Historique\n\n"
        "| Nom | Valeur |\n| --- | --- |\n| Plateforme | \x601.0.0\x60 |\n"
        "\n## Active\n\n| Nom | Valeur |\n| --- | --- |\n| Plateforme | \x601.2.2\x60 |\n"
        "\n\x60\x60\x60bash\n./scripts/setup.sh --plan\n\x60\x60\x60\n",
        encoding="utf-8",
    )
    git("add", ".")
    git("commit", "-qm", "Atlas")
    commit = git("rev-parse", "HEAD")
    result = coherence.audit_local(tmp_path, commit)
    assert result["commit"] == commit
    assert result["counts_by_status"] == {"missing_technical_path": 1, "version_drift": 1}
    checks = {row["id"]: row for row in result["checks"]}
    assert checks["product"]["declarations"][0]["comparison"] == "match"
    assert checks["product"]["declarations"][1]["value"] == "1.2.2"
    assert checks["product"]["declarations"][1]["line"] == 13
    assert checks["launcher"]["lines"] == [16]
    readme.unlink()
    assert coherence.audit_local(tmp_path, commit) == result
    with pytest.raises(ValueError, match="empreinte"):
        coherence.audit_local(tmp_path, commit, expected_inventory="0" * 64)


def _remote_fixture(monkeypatch: pytest.MonkeyPatch, documents: dict[str, bytes]) -> list[str]:
    blobs = {
        hashlib.sha1(f"blob {len(raw)}\0".encode() + raw, usedforsecurity=False).hexdigest(): raw
        for raw in documents.values()
    }
    reverse = {raw: sha for sha, raw in blobs.items()}
    entries = [{"path": name, "mode": "100644", "type": "blob", "sha": reverse[raw]}
               for name, raw in documents.items()]
    monkeypatch.setattr(sources, "_github_tree",
                        lambda *_: (TREE, {"sha": TREE, "tree": entries}))
    reads = []

    def read(repository: str, sha: str) -> bytes:
        assert repository == REPOSITORY
        reads.append(sha)
        return blobs[sha]

    monkeypatch.setattr(links, "_github_blob", read)
    return reads


def test_current_project_contract_matches_its_documentary_and_technical_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = json.loads((ROOT / coherence.DEFAULT_CONTRACT).read_text(encoding="utf-8"))
    paths = {coherence.DEFAULT_CONTRACT}
    for check in spec["checks"]:
        if check["kind"] == "version":
            paths.update(selector["path"] for selector in
                         [check["authority"], *check["declarations"]])
        else:
            paths.update([check["document"], check["target"]])
    documents = {path: (ROOT / path).read_bytes() for path in paths}
    reads = _remote_fixture(monkeypatch, documents)
    report = coherence.audit_github(REPOSITORY, COMMIT)
    assert report["counts_by_status"] == {"match": 7}
    assert len(reads) == len(set(reads)) == len(paths) - 1
    assert report == coherence.audit_github(REPOSITORY, COMMIT)


def test_audit_distinguishes_an_ambiguous_source_from_a_version_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = {"schema": 1, "checks": [{
        "id": "runtime", "kind": "version", "authority": _selector("versions.yaml", "yaml", "pin"),
        "declarations": [_selector("package.json", "json", "version")],
    }]}
    documents = {coherence.DEFAULT_CONTRACT: json.dumps(spec).encode(),
                 "versions.yaml": b'pin: "1.0"\npin: "1.2"\n', "package.json": b'{"version":"1.2"}'}
    _remote_fixture(monkeypatch, documents)
    report = coherence.audit_github(REPOSITORY, COMMIT)
    assert report["counts_by_status"] == {"not_verified": 1}
    assert report["checks"][0]["authority"]["status"] == "ambiguous_or_invalid"
    assert "value" not in report["checks"][0]["authority"]


@pytest.mark.skipif(os.name != "posix", reason="mode privé POSIX requis")
def test_cli_keeps_a_private_report_when_a_check_needs_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    tmp_path.chmod(0o700)
    monkeypatch.setattr(coherence, "audit_github", lambda *_, **__: {
        "counts_by_status": {"version_drift": 1}, "checks": [{}],
    })
    output = tmp_path / "audit.json"
    args = ["--github", REPOSITORY, "--commit", COMMIT, "--output", str(output)]
    assert coherence.main(args) == 1
    assert output.stat().st_mode & 0o777 == 0o600
    assert coherence.main(args) == 2
