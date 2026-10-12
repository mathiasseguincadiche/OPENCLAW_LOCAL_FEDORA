from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import pytest
from docx import Document
from pypdf import PdfReader

from clawfedora.document_bundle import assemble, build_bundle


def test_bundle_keeps_editable_source_and_exact_binary_provenance(tmp_path: Path) -> None:
    first = tmp_path / "intro.md"
    second = tmp_path / "suite.md"
    first.write_text("# Introduction\n\nUn objectif DevOps clair.", encoding="utf-8")
    second.write_text("## Procédure\n\n1. Préparer\n2. Vérifier", encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    before = build_bundle([first, second], out, "runbook")
    assert before["dry_run"] is True
    assert list(out.iterdir()) == []
    actual = build_bundle([first, second], out, "runbook", apply=True)
    assert actual["dry_run"] is False
    assert len(actual["files"]) == 4
    md = (out / "runbook.md").read_text()
    assert "# Introduction" in md and "## Procédure" in md
    assert "---" in md
    assert PdfReader(io.BytesIO((out / "runbook.pdf").read_bytes())).pages
    document = Document(io.BytesIO((out / "runbook.docx").read_bytes()))
    assert any(p.text == "Procédure" for p in document.paragraphs)
    manifest = json.loads((out / "runbook.manifest.json").read_text())
    for name, digest in manifest["exports"].items():
        assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest
    assert manifest["provenance"] == "offline-reviewed-markdown-sections"
    assert manifest["sources"][0]["sha256"] == hashlib.sha256(first.read_bytes()).hexdigest()
    assert all(f.stat().st_mode & 0o077 == 0 for f in out.iterdir())


def test_duplicate_and_oversized_sections_are_refused(tmp_path: Path) -> None:
    src = tmp_path / "part.md"
    src.write_text("## a")
    with pytest.raises(ValueError, match="répétée"):
        assemble([src, src])
    src.write_text("x" * 12001)
    with pytest.raises(ValueError, match="12 000"):
        assemble([src])
    src.write_bytes(b"abc\xff")
    with pytest.raises(ValueError, match="UTF-8"):
        assemble([src])


def test_export_is_all_or_nothing_when_target_exists(tmp_path: Path) -> None:
    src = tmp_path / "part.md"
    src.write_text("# Hello\n\ntext")
    out = tmp_path / "out"
    out.mkdir()
    existing = out / "guide.pdf"
    existing.write_bytes(b"original")
    with pytest.raises(ValueError, match="existe déjà"):
        build_bundle([src], out, "guide", apply=True)
    assert existing.read_bytes() == b"original"
    assert list(out.iterdir()) == [existing]


def test_reject_source_or_destination_symlinks(tmp_path: Path) -> None:
    section = tmp_path / "real.md"
    section.write_text("# Test")
    linked = tmp_path / "part.md"
    linked.symlink_to(section)
    with pytest.raises(ValueError, match="symbolique"):
        assemble([linked])
    out = tmp_path / "actual-out"
    out.mkdir()
    linked_out = tmp_path / "linked-out"
    linked_out.symlink_to(out)
    with pytest.raises(ValueError, match="liée"):
        build_bundle([section], linked_out, "guide")


def test_refuse_bad_names_and_empty_markdown(tmp_path: Path) -> None:
    section = tmp_path / "a.md"
    section.write_text("\n")
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(ValueError, match="vide"):
        build_bundle([section], out, "guide")
    section.write_text("# Correct")
    for name in ("../runbook", ".secrets", "name space", ""):
        with pytest.raises(ValueError, match="nom"):
            build_bundle([section], out, name)
