from __future__ import annotations

import os
import zipfile
from pathlib import Path

import pytest

from clawfedora.project_common import read_json
from clawfedora.project_intake import create_project

ROOT = Path(__file__).resolve().parents[1]


def test_create_project_inventories_and_ingests_text_pdf_and_zip(tmp_path: Path) -> None:
    request = tmp_path / "request.md"
    request.write_text("# Projet\nConstruire le livrable.\n", encoding="utf-8")
    pdf = tmp_path / "spec.pdf"
    pdf.write_bytes(b"%PDF-1.7\nsynthetic-test\n")
    archive = tmp_path / "sources.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("src/main.py", "print('ok')\n")

    project = create_project(
        ROOT,
        tmp_path / "runtime",
        "demo-project",
        "Démo",
        intake_items=[request, pdf, archive],
    )
    manifest = read_json(project / "project.json")
    assert manifest["status"] == "INTAKE_READY"
    inventory = read_json(project / "evidence" / "intake" / "inventory.json")
    assert inventory["file_count"] == 3
    assert len(str(inventory["aggregate_sha256"])) == 64

    index = read_json(project / "context" / "ingestion" / "index.json")
    documents = index["documents"]
    assert isinstance(documents, list)
    by_name = {Path(str(item["path"])).name: item for item in documents}
    assert by_name["request.md"]["status"] == "READ"
    assert by_name["request.md"]["method"] == "local_text_extract"
    assert by_name["spec.pdf"]["status"] == "TOOL_REQUIRED"
    assert by_name["spec.pdf"]["method"] == "pdf"
    assert by_name["sources.zip"]["status"] == "READ"
    archive_id = by_name["sources.zip"]["document_id"]
    extracted = project / "context" / "ingestion" / str(archive_id) / "archive_members" / "src" / "main.py"
    assert extracted.read_text(encoding="utf-8") == "print('ok')\n"


def test_secret_like_file_is_rejected_transactionally(tmp_path: Path) -> None:
    secret = tmp_path / ".env"
    secret.write_text("TOKEN=not-even-needed\n", encoding="utf-8")
    runtime = tmp_path / "runtime"
    with pytest.raises(ValueError, match="secret potentiel"):
        create_project(ROOT, runtime, "secret-project", "Secret", intake_items=[secret])
    assert not (runtime / "projects" / "secret-project").exists()


def test_symlink_is_rejected(tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip("test POSIX")
    real = tmp_path / "real.txt"
    real.write_text("ok", encoding="utf-8")
    linked = tmp_path / "linked.txt"
    linked.symlink_to(real)
    with pytest.raises(ValueError, match="symbolique"):
        create_project(ROOT, tmp_path / "runtime", "link-project", "Link", intake_items=[linked])


def test_unsafe_zip_is_kept_untrusted_but_marked_unreadable(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("../escape.txt", "nope")
    project = create_project(
        ROOT,
        tmp_path / "runtime",
        "unsafe-project",
        "Unsafe",
        intake_items=[archive],
    )
    index = read_json(project / "context" / "ingestion" / "index.json")
    document = index["documents"][0]
    assert document["status"] == "UNREADABLE"
    assert "chemin membre interdit" in document["reason"]
    assert not (project.parent / "escape.txt").exists()
