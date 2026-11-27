"""Document links are checked against immutable Git objects without following URLs."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from clawfedora import github_document_links as links
from clawfedora import source_connectors as sources

COMMIT = "a" * 40
TREE = "b" * 40
REPO = "example/atlas"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=Atlas",
         "-c", "user.email=atlas@example.invalid", "-c", "commit.gpgsign=false", *args],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def _sha(raw: bytes) -> str:
    return hashlib.sha1(f"blob {len(raw)}\0".encode() + raw, usedforsecurity=False).hexdigest()


@pytest.mark.skipif(shutil.which("git") is None, reason="Git local requis")
def test_local_audit_uses_committed_markdown_and_tree(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    guide = repo / "docs"
    guide.mkdir()
    (guide / "Guide local.md").write_text(
        "# Déploiement\n\n## Répétition\n\n## Répétition\n\n<a name=\"point-fixe\"></a>\n",
        encoding="utf-8",
    )
    (repo / "README.md").write_text(
        "# Atlas\n\n"
        "[Guide](docs/Guide%20local.md#d%C3%A9ploiement)\n\n"
        "[Section répétée][suite]\n\n"
        "[suite]: docs/Guide%20local.md#répétition-1\n\n"
        "<a href=\"/docs/Guide%20local.md#point-fixe\">Guide</a>\n\n"
        "[Local](#atlas)\n\n"
        "[Casse](docs/guide%20local.md)\n\n"
        "[Ancre manquante](docs/Guide%20local.md#absente)\n\n"
        "[Hors dépôt](../outside.md)\n\n"
        "[Fichier manquant](docs/absent.md)\n\n"
        "[Dossier](/docs/)\n\n"
        "[Externe](https://example.invalid/?token=NE-PAS-COPIER)\n\n"
        "\x60[Mauvais dans un exemple](fake.md)\x60\n",
        encoding="utf-8",
    )
    _git(repo, "add", "--", "README.md", "docs")
    _git(repo, "commit", "-qm", "Atlas")
    commit = _git(repo, "rev-parse", "HEAD")
    first = links.audit_local(repo, commit, ["README.md"])
    (repo / "README.md").write_text("# modifié", encoding="utf-8")
    (guide / "Guide local.md").unlink()
    assert links.audit_local(guide, commit, ["README.md"]) == first
    assert first["markdown_inspected"] == ["README.md"]
    assert first["counts_by_status"] == {
        "valid_anchor": 4, "valid_path": 1, "missing_path": 1, "missing_anchor": 1,
        "outside_repository": 1, "path_case_mismatch": 1, "external_not_checked": 1,
    }
    assert first["broken_count"] == 4
    assert all(item["path"] == "README.md" and item["line"] > 1 for item in first["findings"])
    assert "NE-PAS-COPIER" not in json.dumps(first)
    with pytest.raises(ValueError, match="empreinte"):
        links.audit_local(repo, commit, ["README.md"], expected_inventory="c" * 64)


def test_github_audit_downloads_only_pinned_markdown_blobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = (
        f"# Atlas\n\n[Fixe](https://github.com/{REPO}/blob/{COMMIT}/README.md#atlas)\n\n"
        f"[Autre](https://github.com/{REPO}/blob/main/README.md#atlas)\n\n"
        "[Confidentiel](docs/private/SECRET.md)\n\n"
        "[Sous-module](module/README.md)\n\n"
        "[Image](image.png#view)\n"
    ).encode()
    sha = _sha(raw)
    entries = [
        {"path": "README.md", "type": "blob", "mode": "100644", "sha": sha},
        {"path": "image.png", "type": "blob", "mode": "100644", "sha": "d" * 40},
        {"path": "module", "type": "commit", "mode": "160000", "sha": "e" * 40},
    ]
    calls = []

    def get(path: str) -> dict[str, Any]:
        calls.append(path)
        if path == f"/repos/{REPO}/commits/{COMMIT}":
            return {"sha": COMMIT, "commit": {"tree": {"sha": TREE}}}
        if path == f"/repos/{REPO}/git/trees/{TREE}?recursive=1":
            return {"sha": TREE, "truncated": False, "tree": entries}
        assert path == f"/repos/{REPO}/git/blobs/{sha}"
        return {"sha": sha, "size": len(raw), "encoding": "base64",
                "content": base64.b64encode(raw).decode()}

    monkeypatch.setattr(sources, "_github", get)
    report = links.audit_github(REPO, COMMIT, [])
    assert report["counts_by_status"] == {
        "valid_anchor": 1, "target_excluded": 2, "other_revision_not_checked": 1,
        "fragment_not_checked": 1,
    }
    assert report["broken_count"] == 0 and len(calls) == 3
    assert "SECRET" not in json.dumps(report)
    assert all(row["target"] is None for row in report["findings"]
               if row["status"] == "target_excluded")
    with pytest.raises(ValueError, match="identifiant du blob"):
        links._check_blob(b"modification", sha)


@pytest.mark.skipif(os.name != "posix", reason="mode POSIX privé requis")
def test_cli_keeps_a_private_report_when_a_broken_link_is_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    tmp_path.chmod(0o700)
    monkeypatch.setattr(links, "audit_github", lambda *_, **__: {"broken_count": 1})
    output = tmp_path / "audit.json"
    args = ["--github", REPO, "--commit", COMMIT, "--output", str(output)]
    assert links.main(args) == 1
    assert output.stat().st_mode & 0o777 == 0o600
    assert links.main(args) == 2
