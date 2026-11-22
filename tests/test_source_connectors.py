"""Synthetic, offline security and behavioral tests for the two read-only connectors."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pytest

from clawfedora import project_cloud, source_connectors
from clawfedora.project_intake import create_project, validate_input_integrity

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "a" * 40
TREE = "b" * 40
BLOB = "c" * 40
NOTION_ROOT = "d" * 32
NOTION_CHILD = "e" * 32
NOTION_BLOCK = "f" * 32


def _project(tmp_path: Path) -> tuple[Path, Path]:
    runtime = tmp_path / "runtime"
    brief = tmp_path / "brief.md"
    brief.write_text("Rédiger un projet de laboratoire.", encoding="utf-8")
    project = create_project(
        ROOT, runtime, "connector-test", "Essai",
        intake_items=[brief],
    )
    return runtime, project


def test_github_snapshot_is_pinned_read_only_and_integrated_in_immutable_intake(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, project = _project(tmp_path)
    readme = b"# OpsDesk fictif\n"
    terraform = b'resource "terraform_data" "example" {}\n'
    tree = [
        {"type": "blob", "mode": "100644", "path": "README.md",
         "sha": BLOB, "size": len(readme)},
        {"type": "blob", "mode": "100644", "path": "infra/main.tf",
         "sha": "d" * 40, "size": len(terraform)},
        {"type": "blob", "mode": "100644", "path": ".env",
         "sha": "e" * 40, "size": 5},
        {"type": "blob", "mode": "100644", "path": "screen.png",
         "sha": "f" * 40, "size": 99},
    ]
    called: list[str] = []

    def github(path: str) -> dict[str, Any]:
        called.append(path)
        if "/commits/" in path:
            return {"sha": COMMIT, "commit": {"tree": {"sha": TREE}}}
        if "/git/trees/" in path:
            return {"truncated": False, "tree": tree}
        if path.endswith(BLOB):
            return {"encoding": "base64", "content": base64.b64encode(readme).decode()}
        if path.endswith("d" * 40):
            return {"encoding": "base64", "content": base64.b64encode(terraform).decode()}
        raise AssertionError(f"Unexpected request: {path}")

    monkeypatch.setattr(source_connectors, "_github", github)
    result = source_connectors.import_snapshot(
        ROOT, runtime, "connector-test", github="example/OpsDesk", commit=COMMIT,
    )
    assert result["status"] == "IMPORTED" and result["local_only"] is False
    assert result["source"]["file_count"] == 2 and result["source"]["skipped"] == 2
    directory = project / "intake" / ("GitHub-example-OpsDesk-" + COMMIT[:12])
    assert (directory / "README.md").read_bytes() == readme
    assert (directory / "infra/main.tf").read_bytes() == terraform
    assert validate_input_integrity(project) == []
    assert len(called) == 4
    assert project_cloud.consent_state(ROOT, runtime, project)["state"] == "none"
    with pytest.raises(ValueError, match="déjà présent"):
        source_connectors.import_snapshot(
            ROOT, runtime, "connector-test", github="example/OpsDesk", commit=COMMIT,
        )


def test_notion_training_notes_are_imported_as_local_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, project = _project(tmp_path)

    def notion(path: str) -> dict[str, Any]:
        if path.endswith("/pages/" + NOTION_ROOT):
            return {"id": NOTION_ROOT, "properties": {
                "title": {"type": "title", "title": [
                    {"plain_text": "Formation InfraOps"}
                ], "rich_text": [{"plain_text": "Formation InfraOps"}]}
            }}
        if path.endswith("/pages/" + NOTION_CHILD):
            return {"id": NOTION_CHILD, "properties": {}}
        if "/blocks/" + NOTION_ROOT + "/children" in path:
            return {"has_more": False, "results": [
                {"id": NOTION_BLOCK, "type": "paragraph",
                 "paragraph": {"rich_text": [{"plain_text": "Cours Terraform"}]},
                 "has_children": False},
                {"id": NOTION_CHILD, "type": "child_page",
                 "child_page": {"title": "Exercice 04"}, "has_children": True},
            ]}
        if "/blocks/" + NOTION_CHILD + "/children" in path:
            return {"has_more": False, "results": [
                {"id": "1" * 32, "type": "paragraph",
                 "paragraph": {"rich_text": [{"plain_text": "Exercice personnel"}]},
                 "has_children": False},
            ]}
        raise AssertionError(path)

    monkeypatch.setattr(source_connectors, "_notion", notion)
    imported = source_connectors.import_snapshot(
        ROOT, runtime, "connector-test", notion_page=NOTION_ROOT,
        include_children=True,
    )
    assert imported["local_only"] is True
    assert imported["source"]["page_count"] == 2
    assert (project / "intake" / ("Notion-" + NOTION_ROOT) /
            f"page-{NOTION_CHILD}.md").is_file()
    assert validate_input_integrity(project) == []
    assert project_cloud.consent_state(ROOT, runtime, project)["state"] == "none"
    with pytest.raises(ValueError, match="notes Notion privées"):
        project_cloud.grant(ROOT, runtime, project, acknowledged=True)

    # Even a legacy consent file cannot turn an imported personal notebook into cloud data.
    path = project_cloud.consent_path(runtime, project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"project_id": "connector-test",
                                "sources_digest": project_cloud.sources_digest(project)}))
    assert project_cloud.consent_state(ROOT, runtime, project)["state"] == "none"
    # An older consent record is ignored in local-only mode.


def test_a_notion_page_without_children_does_not_fetch_the_children_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, project = _project(tmp_path)
    requests: list[str] = []

    def notion(path: str) -> dict[str, Any]:
        requests.append(path)
        if path.endswith("/pages/" + NOTION_ROOT):
            return {"id": NOTION_ROOT, "properties": {}}
        if "/blocks/" + NOTION_ROOT + "/children" in path:
            return {"has_more": False, "results": [
                {"id": NOTION_CHILD, "type": "child_page",
                 "child_page": {"title": "Enfant"}, "has_children": True}
            ]}
        raise AssertionError(path)

    monkeypatch.setattr(source_connectors, "_notion", notion)
    source_connectors.import_snapshot(
        ROOT, runtime, "connector-test", notion_page=NOTION_ROOT,
    )
    assert not any("/pages/" + NOTION_CHILD in item for item in requests)
    assert not (project / "intake" / ("Notion-" + NOTION_ROOT) /
                f"page-{NOTION_CHILD}.md").exists()


def test_remote_path_traversal_credentials_and_incomplete_tree_are_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, project = _project(tmp_path)
    for item in ("../escape.txt", "/etc/passwd", "src/../../secret", r"src\secret.py"):
        with pytest.raises(source_connectors.SourceImportError, match="chemin"):
            source_connectors._safe_path(item)
    for item in ("gh/../repo", "gh/not/another", "invalid"):
        with pytest.raises(source_connectors.SourceImportError):
            source_connectors._safe_repo(item)
    with pytest.raises(source_connectors.SourceImportError):
        source_connectors._safe_sha("main")
    with pytest.raises(source_connectors.SourceImportError):
        source_connectors._safe_page("https://evil.example/page")

    def github(path: str) -> dict[str, Any]:
        if "/commits/" in path:
            return {"sha": COMMIT, "commit": {"tree": {"sha": TREE}}}
        return {"truncated": True, "tree": []}

    monkeypatch.setattr(source_connectors, "_github", github)
    with pytest.raises(source_connectors.SourceImportError, match="incomplet"):
        source_connectors.import_snapshot(
            ROOT, runtime, "connector-test", github="example/OpsDesk", commit=COMMIT,
        )
    assert validate_input_integrity(project) == []
    assert sorted(x.name for x in (project / "intake").iterdir()) == ["brief.md"]


def test_dry_run_never_contacts_remote_api(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_network(_path: str) -> dict[str, Any]:
        raise AssertionError("No network permitted")

    monkeypatch.setattr(source_connectors, "_github", no_network)
    monkeypatch.setattr(source_connectors, "_notion", no_network)
    assert source_connectors.main([
        "--project-id", "connector-test", "--github", "example/OpsDesk",
        "--commit", COMMIT,
    ]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["status"] == "PLAN_ONLY" and plan["remote_writes"] is False
    assert source_connectors.main([
        "--project-id", "connector-test", "--notion-page", NOTION_ROOT,
    ]) == 0
    plan2 = json.loads(capsys.readouterr().out)
    assert plan2["notion_local_only"] is True
