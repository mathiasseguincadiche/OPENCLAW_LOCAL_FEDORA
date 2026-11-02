"""A12: project Office imports use the same hardened XML reader as chat and ODT.

Before the fix, ``_office_extract`` parsed DOCX/PPTX/XLSX parts with the standard
ElementTree: a synthetic document with an internal entity was accepted and expanded.
All documents here are synthetic and harmless; nothing is fetched or executed.
"""

from __future__ import annotations

import io
import shutil
import zipfile
from pathlib import Path
from typing import Any

import pytest
import yaml

from clawfedora.core_config import core_contract
from clawfedora.core_contracts import validate_core_contracts
from clawfedora.project_common import read_json
from clawfedora.project_intake import _office_extract, build_ingestion_index

ROOT = Path(__file__).resolve().parents[1]
W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
PLAIN = (
    f'<?xml version="1.0"?><w:document {W}><w:body>'
    "<w:p><w:r><w:t>Plan réseau</w:t></w:r></w:p></w:body></w:document>"
)
ENTITY = (
    '<?xml version="1.0"?><!DOCTYPE d [<!ENTITY nom "INTERNE-DEVELOPPE">]>'
    f'<w:document {W}><w:body><w:p><w:r><w:t>&nom;</w:t></w:r></w:p></w:body></w:document>'
)
EXTERNAL = (
    '<?xml version="1.0"?><!DOCTYPE d [<!ENTITY ext SYSTEM "file:///etc/hostname">]>'
    f'<w:document {W}><w:body><w:p><w:r><w:t>&ext;</w:t></w:r></w:p></w:body></w:document>'
)


def _docx(document_xml: str, *, extra: dict[str, bytes] | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types/>')
        archive.writestr("word/document.xml", document_xml)
        for name, data in (extra or {}).items():
            archive.writestr(name, data)
    return buffer.getvalue()


def _limits(**override: int) -> dict[str, Any]:
    limits = dict(core_contract(ROOT, "document_ingestion_policy.yaml")["limits"])
    limits.update(override)
    return limits


def _extract(tmp_path: Path, data: bytes, **override: int) -> tuple[dict[str, Any], Path]:
    source = tmp_path / "source.docx"
    source.write_bytes(data)
    output = tmp_path / "extracted.txt"
    return _office_extract(source, output, 100_000, _limits(**override)), output


def test_plain_office_text_is_still_extracted(tmp_path: Path) -> None:
    detail, output = _extract(tmp_path, _docx(PLAIN))
    assert "Plan réseau" in output.read_text(encoding="utf-8")
    assert detail["truncated"] is False and "skipped_xml_members" not in detail


@pytest.mark.parametrize("document_xml", [ENTITY, EXTERNAL])
def test_dtd_and_entities_are_refused_before_any_expansion(
    tmp_path: Path, document_xml: str
) -> None:
    with pytest.raises(ValueError, match="DTD, entités"):
        _extract(tmp_path, _docx(document_xml))
    assert not (tmp_path / "extracted.txt").exists()


def test_xml_sizes_are_bounded_before_decompression(tmp_path: Path) -> None:
    padding = f"<w:document {W}>" + "<w:p/>" * 20_000 + "</w:document>"
    data = _docx(padding)
    with pytest.raises(ValueError, match="partie XML trop volumineuse"):
        _extract(tmp_path, data, office_max_xml_member_bytes=50_000,
                 office_max_xml_total_bytes=10_000_000)
    with pytest.raises(ValueError, match="volume XML total"):
        _extract(tmp_path, data, office_max_xml_member_bytes=10_000_000,
                 office_max_xml_total_bytes=50_000)


def test_malformed_part_is_reported_instead_of_silently_skipped(tmp_path: Path) -> None:
    detail, output = _extract(tmp_path, _docx(PLAIN, extra={"word/comments.xml": b"<broken"}))
    assert "Plan réseau" in output.read_text(encoding="utf-8")
    assert detail["skipped_xml_members"] == ["word/comments.xml"]


def test_project_index_marks_an_entity_document_unreadable(tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / "intake").mkdir(parents=True)
    (project / "intake/piege.docx").write_bytes(_docx(ENTITY))
    (project / "intake/sain.docx").write_bytes(_docx(PLAIN))
    index = read_json(build_ingestion_index(project, ROOT))
    by_path = {entry["path"]: entry for entry in index["documents"]}
    assert by_path["intake/piege.docx"]["status"] == "UNREADABLE"
    assert "DTD, entités" in by_path["intake/piege.docx"]["reason"]
    assert by_path["intake/sain.docx"]["status"] == "READ"
    extracted = "".join(p.read_text(encoding="utf-8") for p in project.rglob("extracted.txt"))
    assert "INTERNE-DEVELOPPE" not in extracted


@pytest.mark.parametrize(
    ("member", "total"), [(0, 100), (200, 100), ("32M", 100), (None, 100)]
)
def test_office_xml_limits_must_be_coherent_in_the_contract(
    tmp_path: Path, member: Any, total: Any
) -> None:
    shutil.copy(ROOT / "VERSION", tmp_path / "VERSION")
    shutil.copytree(ROOT / "config", tmp_path / "config")
    shutil.copytree(ROOT / "agents", tmp_path / "agents")
    path = tmp_path / "config/core/document_ingestion_policy.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["limits"]["office_max_xml_member_bytes"] = member
    payload["limits"]["office_max_xml_total_bytes"] = total
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    failures, _ = validate_core_contracts(tmp_path)
    assert any("plafonds XML Office" in failure for failure in failures)
