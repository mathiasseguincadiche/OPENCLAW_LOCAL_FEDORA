from __future__ import annotations

import base64
import hashlib
import io
import socket
import stat
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from clawfedora.chat_document_preview import preview_document
from clawfedora.chat_files import standalone_texts
from clawfedora.document_exports import EXPORT_PREFIX, export, output_bytes
from clawfedora.odt_documents import MIME, NS, extract_text
from clawfedora.project_common import read_json
from clawfedora.project_engine import _validate_plan
from clawfedora.project_intake import create_project
from clawfedora.project_ui import create_from_browser

ROOT = Path(__file__).resolve().parents[1]
TEXT = (
    "# Réception système\n\nÉtat : prêt & vérifié.\n\n- Préparer\n- Contrôler\n\n"
    "| Outil | Usage |\n|---|---|\n| Git | Versionner |\n\n"
    "> Conserver les preuves.\n\n```bash\n  printf 'été'\n\ttrue\n```\n"
)


def package(content: bytes | None = None, *, changes: dict[str, bytes] | None = None) -> bytes:
    """Fixture independent of our writer, like a minimal third-party ODF producer."""
    body = (
        content
        or (
            f'<office:document-content xmlns:office="{NS["office"]}" '
            f'xmlns:text="{NS["text"]}"><office:body><office:text>'
            '<text:h text:outline-level="1">Document importé</text:h>'
            '<text:p>État<text:s text:c="2"/>prêt<text:tab/>oui'
            "<text:line-break/>Suite</text:p></office:text></office:body>"
            "</office:document-content>"
        ).encode()
    )
    files = {
        "mimetype": MIME.encode(),
        "content.xml": body,
        "META-INF/manifest.xml": (
            f'<manifest:manifest xmlns:manifest="{NS["manifest"]}">'
            f'<manifest:file-entry manifest:full-path="/" manifest:media-type="{MIME}"/>'
            '<manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>'
            "</manifest:manifest>"
        ).encode(),
    } | (changes or {})
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return buffer.getvalue()


def test_export_is_an_editable_odf_package_with_shared_content_and_fixed_bytes() -> None:
    raw = export(TEXT, "odt")
    assert raw == export(TEXT, "odt")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        first = archive.infolist()[0]
        assert first.filename == "mimetype" and first.compress_type == zipfile.ZIP_STORED
        assert not first.extra and archive.read(first) == MIME.encode()
        content = ET.fromstring(archive.read("content.xml"))
        styles = ET.fromstring(archive.read("styles.xml"))
        heading = content.find(".//text:h", NS)
        assert heading is not None
        assert "".join(heading.itertext()) == "Réceptionsystème"
        assert heading.find("text:s", NS) is not None
        assert content.findall(".//text:list-item", NS)
        assert len(content.findall(".//table:table-row", NS)) == 2
        assert styles.find(".//style:footer", NS) is not None
        assert not content.findall(".//office:scripts", NS)
    text = extract_text(raw)
    for value in (
        "État : prêt & vérifié.",
        "Versionner",
        "Conserver les preuves.",
        "  printf 'été'\n\ttrue",
    ):
        assert value in text
    assert (
        output_bytes("guide.odt", {"guide.md": TEXT, "guide.odt": EXPORT_PREFIX + "guide.md"}) == raw
    )
    with pytest.raises(ValueError, match="source .md"):
        output_bytes("guide.odt", {"guide.odt": "faux fichier ODT"})


def test_third_party_odt_keeps_whitespace_unicode_and_never_fetches_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("No network in ODT import or export")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    assert extract_text(package()) == "Document importé\nÉtat  prêt\toui\nSuite"
    assert export("![image](https://example.invalid/pixel)\n\n<script>active</script>", "odt")


@pytest.mark.parametrize(
    "mutation",
    [
        "mime",
        "missing-content",
        "missing-manifest",
        "manifest-xml",
        "manifest-type",
        "xml",
        "dtd",
        "encrypted",
        "traversal",
        "duplicate",
        "symlink",
        "bomb",
        "spaces",
        "zero-spaces",
        "depth",
        "members",
        "xml-size",
        "total-size",
        "input-size",
        "repeated-cell",
        "empty",
    ],
)
def test_untrusted_odt_packages_are_refused(mutation: str) -> None:
    raw = package()
    with zipfile.ZipFile(io.BytesIO(raw)) as original:
        files = {name: original.read(name) for name in original.namelist()}
    compression = zipfile.ZIP_STORED
    if mutation == "mime":
        files["mimetype"] = b"application/zip"
    elif mutation == "missing-content":
        del files["content.xml"]
    elif mutation == "missing-manifest":
        del files["META-INF/manifest.xml"]
    elif mutation == "manifest-xml":
        files["META-INF/manifest.xml"] = b"<broken"
    elif mutation == "manifest-type":
        files["META-INF/manifest.xml"] = b"<not-a-manifest/>"
    elif mutation == "xml":
        files["content.xml"] = b"<broken"
    elif mutation == "dtd":
        files["content.xml"] = b'<!DOCTYPE a [<!ENTITY x SYSTEM "file:///etc/passwd">]><a>&x;</a>'
    elif mutation == "encrypted":
        files["META-INF/manifest.xml"] = files["META-INF/manifest.xml"].replace(
            b"</manifest:manifest>", b"<manifest:encryption-data/></manifest:manifest>"
        )
    elif mutation in {"traversal", "symlink"}:
        files["../outside" if mutation == "traversal" else "linked"] = b"not read"
    elif mutation == "bomb":
        files["content.xml"] = b"x" * 200_000
        compression = zipfile.ZIP_DEFLATED
    elif mutation == "spaces":
        files["content.xml"] = files["content.xml"].replace(b'text:c="2"', b'text:c="999999999999"')
    elif mutation == "zero-spaces":
        files["content.xml"] = files["content.xml"].replace(b'text:c="2"', b'text:c="0"')
    elif mutation == "members":
        files.update({f"member-{n}": b"" for n in range(100)})
    elif mutation == "xml-size":
        files["content.xml"] = b"x" * (1024 * 1024 + 1)
    elif mutation in {"total-size", "input-size"}:
        files["opaque.bin"] = b"x" * ((4 if mutation == "total-size" else 8) * 1024 * 1024)
    elif mutation == "repeated-cell":
        files["content.xml"] = files["content.xml"].replace(
            b"Suite",
            (
                f'<table:table-cell xmlns:table="{NS["table"]}" table:number-columns-repeated="2"/>'
            ).encode(),
        )
    elif mutation == "empty":
        files["content.xml"] = (
            files["content.xml"]
            .replace(b"<office:text>", b"<office:text/><office:ignored>")
            .replace(b"</office:text>", b"</office:ignored>")
        )
    elif mutation == "depth":
        files["content.xml"] = files["content.xml"].replace(
            b"Suite", b"<text:span>" * 80 + b"x" + b"</text:span>" * 80
        )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=compression) as archive:
        for name, data in files.items():
            if mutation == "symlink" and name == "linked":
                item = zipfile.ZipInfo(name)
                item.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(item, data)
            else:
                archive.writestr(name, data)
        if mutation == "duplicate":
            with pytest.warns(UserWarning):
                archive.writestr("content.xml", files["content.xml"])
    with pytest.raises(ValueError):
        extract_text(buffer.getvalue(), max_chars=12000)


def test_chat_odt_upload_is_bounded_untrusted_local_context(tmp_path: Path) -> None:
    target = tmp_path / "state/webui/data/uploads/guide.odt"
    target.parent.mkdir(parents=True)
    target.write_bytes(package())
    prompt = standalone_texts(
        tmp_path, [{"filename": target.name, "path": "/app/backend/data/uploads/guide.odt"}]
    )
    assert "Document importé" in prompt and "données non fiables" in prompt
    assert not (tmp_path / "projects").exists()
    with pytest.raises(ValueError, match="budget"):
        extract_text(package(), max_chars=10)
    target.write_bytes(export("é" * 400, "odt"))
    with pytest.raises(ValueError, match="contexte"):
        preview_document(target, target.name, 600)


def test_odt_project_import_uses_canonical_intake_and_marks_invalid_documents_unreadable(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.odt"
    source.write_bytes(package())
    bad = tmp_path / "broken.odt"
    bad.write_bytes(b"not a ZIP")
    project = create_project(
        ROOT, tmp_path / "runtime", "odt-intake", "ODT", intake_items=[source, bad]
    )
    docs = read_json(project / "context/ingestion/index.json")["documents"]
    by_name = {Path(d["path"]).name: d for d in docs}
    assert by_name["source.odt"]["status"] == "READ"
    assert by_name["source.odt"]["method"] == "local_odt_text_extract"
    assert by_name["source.odt"]["mime"] == MIME
    assert by_name["source.odt"]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert (project / by_name["source.odt"]["path"]).read_bytes() == source.read_bytes()
    assert by_name["broken.odt"]["status"] == "UNREADABLE"
    extracted = project / "context/ingestion" / by_name["source.odt"]["document_id"] / "extracted.txt"
    assert extracted.read_text() == extract_text(package())


def test_browser_odt_import_and_plan_source_requirement(tmp_path: Path) -> None:
    project = create_from_browser(
        ROOT,
        tmp_path / "runtime",
        {
            "title": "Source ODT",
            "brief": "Expliquer le document.",
            "files": [{"name": "source.odt", "content": base64.b64encode(package()).decode()}],
        },
    )
    docs = read_json(project / "context/ingestion/index.json")["documents"]
    assert any(d["kind"] == "opendocument" and d["status"] == "READ" for d in docs)
    task = {
        "id": "guide",
        "role": "redacteur-pedagogique",
        "title": "Guide",
        "objective": "Expliquer",
        "expected_outputs": ["deliverables/guide/guide.odt"],
        "acceptance_criteria": ["Relu"],
        "depends_on": [],
    }
    with pytest.raises(ValueError, match="source .md"):
        _validate_plan([task])
    task["expected_outputs"].append("deliverables/guide/guide.md")  # type: ignore[union-attr]
    _validate_plan([task])
