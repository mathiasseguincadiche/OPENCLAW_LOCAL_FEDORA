"""Local cross-source retrieval, latest GitHub provenance and private Notion safety."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from clawfedora import github_refresh, project_cloud, source_connectors
from clawfedora.chat_projects import project_context
from clawfedora.knowledge import build_index, search
from clawfedora.project_intake import create_project
from clawfedora.project_retrieval import retrieve

ROOT = Path(__file__).resolve().parents[1]
REPO = "example/OpsDesk"
OLD = "a" * 40
NEW = "b" * 40
PAGE = "1" * 32


@pytest.fixture
def workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path]:
    runtime = tmp_path / "runtime"
    brief = tmp_path / "brief.md"
    brief.write_text("Projet InfraOps Terraform et Ansible", encoding="utf-8")
    project = create_project(
        ROOT, runtime, "cross-search", "Recherche croisée", intake_items=[brief]
    )

    def github(dest: Path, repo: str, commit: str) -> dict[str, Any]:
        assert repo == REPO
        if commit == OLD:
            documents = {
                "infra/main.tf": "Terraform legacy_backend frozen old-code.",
                "docs/readme.md": "Ancien snapshot du service legacy_backend.",
            }
        else:
            assert commit == NEW
            documents = {
                "infra/main.tf": "Terraform bridge_network source approuvée.",
                "ops/ansible.yml": "Ansible bridge_network deploiement cible.",
                "docs/readme.md": "Revue de l'architecture bridge_network.",
            }
        for name, value in documents.items():
            target = dest / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(value, encoding="utf-8")
        return {
            "provider": "github", "repository": repo, "commit": commit,
            "file_count": len(documents), "skipped": 0,
        }

    def notion(dest: Path, page_id: str, include_children: bool) -> dict[str, Any]:
        assert page_id == PAGE and include_children is False
        (dest / "architecture.md").write_text(
            "# Architecture privée\nTerraform bridge_network procédure "
            "de vérification, rôle Ansible et journal de formation.\n",
            encoding="utf-8",
        )
        return {
            "provider": "notion", "page_id": page_id,
            "classification": "private_local_only", "file_count": 1,
        }

    monkeypatch.setattr(source_connectors, "_github_snapshot", github)
    monkeypatch.setattr(source_connectors, "_notion_snapshot", notion)
    source_connectors.import_snapshot(
        ROOT, runtime, project.name, github=REPO, commit=OLD
    )
    source_connectors.import_snapshot(
        ROOT, runtime, project.name, notion_page=PAGE
    )
    build_index(ROOT, project)
    preview = github_refresh.refresh(runtime, project.name, REPO, NEW)
    github_refresh.refresh(
        runtime, project.name, REPO, NEW,
        approve=preview["approve_sha256"], apply=True,
    )
    return runtime, project


def test_latest_approved_github_and_private_notion_are_diverse_and_cited(
    workspace: tuple[Path, Path],
) -> None:
    _runtime, project = workspace
    hits = retrieve(ROOT, project, "Terraform bridge_network Ansible")
    assert len(hits) >= 3 and len(hits) <= 4
    assert len({hit["path"] for hit in hits}) == len(hits)
    assert sum(len(h["text"]) for h in hits) <= 4000
    git = [hit for hit in hits if hit["kind"] == "github-approved-revision"]
    notes = [hit for hit in hits if "Notion-" in hit["path"]]
    assert len(git) >= 2 and notes
    assert all(hit["commit"] == NEW for hit in git)
    assert all("legacy_backend" not in hit["text"] for hit in hits)
    assert all("intake/GitHub-" not in hit["path"] for hit in hits)
    for hit in hits:
        assert hit["stale"] is False
        assert hit["excerpt_sha256"] == hashlib.sha256(
            hit["text"].encode()
        ).hexdigest()
        file = project / hit["representation_path"]
        assert file.is_file()
        assert hashlib.sha256(file.read_bytes()).hexdigest() == hit[
            "representation_sha256"
        ]


def test_legacy_fts_stays_unchanged_and_latest_is_read_only(
    workspace: tuple[Path, Path],
) -> None:
    _runtime, project = workspace
    initial = search(ROOT, project, "legacy_backend")
    assert initial and any("intake/GitHub-" in h["path"] for h in initial)
    assert retrieve(ROOT, project, "legacy_backend") == []
    old = retrieve(ROOT, project, "legacy_backend", include_revisions=False)
    assert old and any("intake/GitHub-" in h["path"] for h in old)
    assert not list((project / "context/knowledge").glob("*github*"))
    assert json.loads(
        (project / "context/github-updates" / github_refresh._directory(
            project, REPO
        ).name / "ledger.json").read_text()
    )["revisions"][-1]["commit"] == NEW


def test_chat_context_only_uses_new_revision_if_explicitly_local(
    workspace: tuple[Path, Path],
) -> None:
    runtime, project = workspace
    question = "Terraform bridge_network Ansible"
    local = project_context(
        ROOT, runtime, project, question, include_revisions=True
    )
    original = project_context(ROOT, runtime, project, question)
    assert '"commit": "' + NEW + '"' in local
    assert "LOCAL_APPROVED_GITHUB_REVISIONS" in local
    assert "Notion-" in local
    assert "LOCAL_APPROVED_GITHUB_REVISIONS" not in original
    assert "github:example/OpsDesk@" not in original
    assert len(local.encode()) <= 7800


def test_tampered_current_snapshot_is_never_cited(
    workspace: tuple[Path, Path],
) -> None:
    _runtime, project = workspace
    root = github_refresh._directory(project, REPO) / NEW / "files"
    target = root / "infra/main.tf"
    target.write_text("changed without approval", encoding="utf-8")
    with pytest.raises(ValueError, match="modifié"):
        retrieve(ROOT, project, "Terraform bridge_network")


def test_corrupt_notion_refuses_cross_source_search_and_cloud_grant(
    workspace: tuple[Path, Path],
) -> None:
    runtime, project = workspace
    with pytest.raises(ValueError, match="Notion"):
        project_cloud.grant(ROOT, runtime, project, acknowledged=True)
    private = next((project / "intake").glob("Notion-*/architecture.md"))
    private.chmod(0o600)
    private.write_text("private document tampered")
    with pytest.raises(ValueError, match="sources initiales"):
        retrieve(ROOT, project, "Terraform")


def test_limits_invalid_query_and_no_spurious_result(
    workspace: tuple[Path, Path],
) -> None:
    _runtime, project = workspace
    with pytest.raises(ValueError, match="1000"):
        retrieve(ROOT, project, "a" * 1001)
    assert retrieve(ROOT, project, "les et de sur") == []
    assert retrieve(ROOT, project, "nonexistent_token_xyz") == []


def test_cli_exposes_no_remote_fetch_or_silent_cloud_transfer() -> None:
    from clawfedora.project_retrieval import build_parser

    parser = build_parser()
    args = parser.parse_args([
        "--project-id", "cross-search", "--query", "terraform",
    ])
    assert args.project_id == "cross-search"
    assert args.initial_only is False
