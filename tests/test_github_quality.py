"""Offline security and scope tests for local GitHub documentation audits."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from clawfedora.github_quality import audit_repository, main


def _repo(path: Path) -> Path:
    root = path / "project"
    (root / "docs/diagrams").mkdir(parents=True)
    (root / ".github/ISSUE_TEMPLATE").mkdir(parents=True)
    (root / ".github/workflows").mkdir(parents=True)
    (root / "evidence").mkdir()
    (root / "README.md").write_text(
        "# Demo\n\n## Architecture\n\n## Démarrage\n\n"
        "[Guide](docs/README.md) [Schéma](docs/diagrams/architecture.svg)\n",
        encoding="utf-8",
    )
    (root / "docs/README.md").write_text("# Documentation\n", encoding="utf-8")
    (root / "docs/architecture.md").write_text("# Architecture\n", encoding="utf-8")
    (root / "docs/demarrage.md").write_text("# Démarrage\n", encoding="utf-8")
    (root / "STATUS.md").write_text("# Prévu, non vérifié\n", encoding="utf-8")
    (root / "docs/diagrams/architecture.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"><rect width="4" height="4"/></svg>',
        encoding="utf-8",
    )
    (root / "docs/diagrams/architecture.drawio").write_text(
        '<mxfile><diagram>example</diagram></mxfile>', encoding="utf-8",
    )
    return root


def test_static_inventory_finds_documents_without_claiming_runtime(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    result = audit_repository(root)
    assert result["assessment"] == "READ_ONLY_DOCUMENTARY_INVENTORY_NOT_A_RUNTIME_PROOF"
    assert result["source"]["kind"] == "LOCAL_DIRECTORY"
    assert result["readme_signals"]["readme_has_architecture_section"] is True
    assert result["links"]["missing_total"] == 0
    assert result["graphics"]["svg_checked"] == 1
    assert result["graphics"]["missing_sources"] == []
    assert {item["id"] for item in result["structure"] if item["state"] == "FOUND"} >= {
        "readme", "documentation_index", "architecture_reference", "project_status",
        "workflow_definitions", "diagrams_directory",
    }
    assert "No CI status" in result["limitations"][1]


def test_imported_snapshot_does_not_report_excluded_image_as_broken(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    with (root / "README.md").open("a", encoding="utf-8") as handle:
        handle.write("\n![Aperçu réel](docs/screenshots/app.png)\n")
    (root / ".source-provenance.json").write_text(
        json.dumps({
            "provider": "github", "repository": "example/repo",
            "commit": "a" * 40, "skipped": 2, "file_count": 12,
        }),
        encoding="utf-8",
    )
    result = audit_repository(root)
    assert result["source"]["kind"] == "GITHUB_SOURCE_SNAPSHOT"
    assert result["source"]["coverage"] == "PARTIAL_ALLOWED_FILES_ONLY"
    assert result["source"]["commit"] == "a" * 40
    assert result["links"]["missing_total"] == 0
    assert result["links"]["not_checked_total"] == 1
    assert "app.png" in result["links"]["not_checked"][0]


def test_missing_local_files_are_reported_and_no_code_runs(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "docs/diagrams/architecture.drawio").unlink()
    (root / "README.md").write_text(
        "# Demo\n\n[Missing](docs/not-created.md)\n", encoding="utf-8",
    )
    result = audit_repository(root)
    assert result["links"]["missing_total"] == 1
    assert "architecture.svg: draw.io source missing" in result["graphics"]["missing_sources"]
    assert result["readme_signals"]["readme_mentions_quick_start"] is False


def test_unsafe_symlink_and_outside_paths_are_not_read(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    secret = tmp_path / "secret.md"
    secret.write_text("PERSONAL SECRET\n", encoding="utf-8")
    (root / "docs/unsafe.md").symlink_to(secret)
    (root / "README.md").write_text(
        "# Demo\n\n[Leak](docs/unsafe.md)\n[Traversal](../../secret.md)\n",
        encoding="utf-8",
    )
    result = audit_repository(root)
    assert result["links"]["missing_total"] == 2
    assert "PERSONAL SECRET" not in json.dumps(result)


def test_privacy_reports_names_only_not_secret_bytes(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / ".env").write_text("REAL_PASSWORD=NEVER_SHOW_THIS\n", encoding="utf-8")
    result = audit_repository(root)
    assert result["potentially_sensitive_root_filenames"] == [".env"]
    assert "NEVER_SHOW_THIS" not in json.dumps(result)


def test_cli_only_reports_and_refuses_non_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    root = _repo(tmp_path)
    assert main(["--path", str(root)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["assessment"].startswith("READ_ONLY_")
    assert main(["--path", str(tmp_path / "missing")]) == 2
    assert json.loads(capsys.readouterr().out)["assessment"] == "REFUSED"


def test_invalid_svg_is_an_audit_finding_not_a_runtime_proof(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "docs/diagrams/architecture.svg").write_text("<svg", encoding="utf-8")
    result = audit_repository(root)
    assert result["graphics"]["svg_checked"] == 0
    assert result["graphics"]["invalid_xml"]
