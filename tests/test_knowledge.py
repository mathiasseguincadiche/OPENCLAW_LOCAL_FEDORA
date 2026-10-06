from __future__ import annotations

import json
import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path

import pytest

from clawfedora import knowledge
from clawfedora.knowledge import build_index, search, store_note
from clawfedora.project_common import read_json
from clawfedora.project_intake import create_project

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def project(tmp_path: Path) -> Path:
    source = tmp_path / "configuration.md"
    source.write_text("# Configuration\nIntel Arc B580 avec Vulkan.\nMémoire DDR5.\n" * 100)
    return create_project(
        ROOT, tmp_path / "runtime", "knowledge-test", "Documents", intake_items=[source]
    )


def test_search_is_bounded_cited_and_incremental(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = build_index(ROOT, project)
    hits = search(ROOT, project, 'Vulkan OR " ; DROP TABLE chunks; --')
    assert first["changed"] == 1 and hits
    assert len(hits) <= 4 and sum(len(hit["text"]) for hit in hits) <= 4000
    assert hits[0]["path"] == "intake/configuration.md" and hits[0]["page"] == 1
    monkeypatch.setattr(
        knowledge, "_extract", lambda *_args: pytest.fail("unchanged source extracted twice")
    )
    assert build_index(ROOT, project)["changed"] == 0
    assert search(ROOT, project, "B580")


def test_decisions_and_dated_research_keep_provenance(project: Path) -> None:
    decision = store_note(
        ROOT, project, "Décision retenue", "Une seule inférence pour préserver les jeux."
    )
    research = store_note(
        ROOT,
        project,
        "Recherche ancienne",
        "La recherche périmée doit être actualisée.",
        kind="research",
        sources=[{"url": "https://example.org/source", "accessed_at": "2020-01-01T12:00:00+00:00"}],
    )
    build_index(ROOT, project)
    assert read_json(decision)["origin"] == "human"
    assert read_json(research)["origin"] == "untrusted"
    assert search(ROOT, project, "périmée")[0]["stale"] is True
    assert search(ROOT, project, "périmée")[0]["sources"][0]["url"].startswith("https://")
    decision.unlink()
    build_index(ROOT, project)
    assert not search(ROOT, project, "inférence")


@pytest.mark.parametrize(
    "sources",
    [
        [],
        [{"url": "file:///etc/passwd", "accessed_at": "2020-01-01T00:00:00+00:00"}],
        [{"url": "https://example.org", "accessed_at": "2020-01-01"}],
    ],
)
def test_research_requires_real_dated_url_metadata(
    project: Path, sources: list[dict[str, str]]
) -> None:
    with pytest.raises(ValueError):
        store_note(ROOT, project, "Recherche", "texte", kind="research", sources=sources)


def test_corrupted_sources_cannot_be_indexed(project: Path) -> None:
    source = project / "intake/configuration.md"
    source.chmod(0o600)
    source.write_text("Autre contenu")
    with pytest.raises(ValueError, match="intégrité"):
        build_index(ROOT, project)


def test_pdf_text_retrieval_keeps_page_numbers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "report.pdf"
    source.write_bytes(b"%PDF-1.4 placeholder")
    project = create_project(ROOT, tmp_path / "runtime", "pdf-project", "PDF", intake_items=[source])
    monkeypatch.setattr(knowledge.shutil, "which", lambda _name: "/usr/bin/pdftotext")

    def convert(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        assert args[1:5] == ["-f", "1", "-l", "20"]
        return subprocess.CompletedProcess(args, 0, "Première page\fRésultat Vulkan page deux", "")

    monkeypatch.setattr(knowledge.subprocess, "run", convert)
    assert build_index(ROOT, project)["documents"] == 1
    assert search(ROOT, project, "Vulkan")[0]["page"] == 2
    # Text indexing never claims that a PDF's visual content was read.
    assert (
        read_json(project / "context/ingestion/index.json")["documents"][0]["status"]
        == "TOOL_REQUIRED"
    )


def test_pdf_without_converter_is_reported_not_silently_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "report.pdf"
    source.write_bytes(b"%PDF-1.4 placeholder")
    project = create_project(ROOT, tmp_path / "runtime", "pdf-project", "PDF", intake_items=[source])
    monkeypatch.setattr(knowledge.shutil, "which", lambda _name: None)
    result = build_index(ROOT, project)
    assert result["documents"] == 0 and "poppler-utils" in result["skipped"][0]["reason"]


def test_symlinked_database_refused(project: Path, tmp_path: Path) -> None:
    root = project / "context/knowledge"
    root.mkdir()
    (root / "search.sqlite").symlink_to(tmp_path / "outside.sqlite")
    with pytest.raises(ValueError, match="symbolique"):
        search(ROOT, project, "secret")


def test_index_records_no_duplicate_note_text_per_chunk(project: Path) -> None:
    store_note(ROOT, project, "Décision", "payload " * 1000)
    build_index(ROOT, project)
    with closing(sqlite3.connect(project / "context/knowledge/search.sqlite")) as db:
        raw = db.execute("SELECT metadata FROM chunks WHERE path LIKE '%notes%' LIMIT 1").fetchone()[
            0
        ]
    assert "text" not in json.loads(raw)
