"""Small, deterministic ODF 1.3 text exports and bounded offline text extraction.

Only document text is read. Embedded objects, styles, macros and external resources
are never executed or fetched. No office process or additional package is needed.
"""

from __future__ import annotations

import io
import re
import stat
import zipfile
import zlib
from pathlib import PurePosixPath
from typing import Any
from xml.etree import ElementTree as ET

from defusedxml.ElementTree import fromstring

MIME = "application/vnd.oasis.opendocument.text"
MAX_INPUT = 8 * 1024 * 1024
MAX_MEMBERS = 100
MAX_XML = 1024 * 1024
MAX_TOTAL = 4 * 1024 * 1024
MAX_RATIO = 100
NS = {
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "style": "urn:oasis:names:tc:opendocument:xmlns:style:1.0",
    "fo": "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0",
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "svg": "urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0",
    "manifest": "urn:oasis:names:tc:opendocument:xmlns:manifest:1.0",
}


def _node(parent: ET.Element, tag: str, attrs: dict[str, str] | None = None) -> ET.Element:
    return ET.SubElement(parent, tag, attrs or {})


def _root(tag: str) -> ET.Element:
    return ET.Element(
        tag, {f"xmlns:{key}": value for key, value in NS.items()} | {"office:version": "1.3"}
    )


def _literal(parent: ET.Element, value: str) -> None:
    # XML 1.0 rejects these controls even if Python's serializer accepts them.
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]", value):
        raise ValueError("ODT : caractère XML interdit")
    previous: ET.Element | None = None
    for token in re.split(r"( +|\t|\n)", value):
        if not token:
            continue
        if token.isspace():
            tag = "text:line-break" if token == "\n" else "text:tab" if token == "\t" else "text:s"
            attrs = {"text:c": str(len(token))} if tag == "text:s" else {}
            previous = _node(parent, tag, attrs)
        elif previous is None:
            parent.text = (parent.text or "") + token
        else:
            previous.tail = (previous.tail or "") + token


def _styles() -> bytes:
    root = _root("office:document-styles")
    fonts = _node(root, "office:font-face-decls")
    for name in ("DejaVu Sans", "DejaVu Sans Mono"):
        _node(fonts, "style:font-face", {"style:name": name, "svg:font-family": name})
    styles = _node(root, "office:styles")
    normal = _node(styles, "style:default-style", {"style:family": "paragraph"})
    _node(normal, "style:paragraph-properties", {"fo:margin-bottom": "0.25cm"})
    _node(
        normal, "style:text-properties", {"style:font-name": "DejaVu Sans", "fo:font-size": "10.5pt"}
    )
    _node(styles, "style:style", {"style:name": "Standard", "style:family": "paragraph"})
    for level in range(1, 7):
        heading = _node(
            styles,
            "style:style",
            {
                "style:name": f"H{level}",
                "style:family": "paragraph",
                "style:parent-style-name": "Standard",
                "style:next-style-name": "Standard",
            },
        )
        _node(
            heading,
            "style:paragraph-properties",
            {"fo:keep-with-next": "always", "fo:margin-top": "0.4cm"},
        )
        _node(
            heading,
            "style:text-properties",
            {
                "fo:font-weight": "bold",
                "fo:font-size": f"{19 if level == 1 else 15 if level == 2 else 12}pt",
                "fo:color": "#126b74",
            },
        )
    for name, font, size in (("Code", "DejaVu Sans Mono", "8pt"), ("Quote", "DejaVu Sans", "10.5pt")):
        style = _node(
            styles,
            "style:style",
            {"style:name": name, "style:family": "paragraph", "style:parent-style-name": "Standard"},
        )
        _node(style, "style:paragraph-properties", {"fo:margin-left": "0.5cm"})
        _node(style, "style:text-properties", {"style:font-name": font, "fo:font-size": size})
    bullet = _node(styles, "text:list-style", {"style:name": "Bullet"})
    level = _node(bullet, "text:list-level-style-bullet", {"text:level": "1", "text:bullet-char": "•"})
    _node(
        level,
        "style:list-level-properties",
        {"text:space-before": "0.2cm", "text:min-label-width": "0.4cm"},
    )
    auto = _node(root, "office:automatic-styles")
    page = _node(auto, "style:page-layout", {"style:name": "A4"})
    _node(
        page,
        "style:page-layout-properties",
        {
            "fo:page-width": "21cm",
            "fo:page-height": "29.7cm",
            "style:print-orientation": "portrait",
            "fo:margin": "2cm",
        },
    )
    masters = _node(root, "office:master-styles")
    master = _node(
        masters, "style:master-page", {"style:name": "Standard", "style:page-layout-name": "A4"}
    )
    footer = _node(master, "style:footer")
    _literal(_node(footer, "text:p"), "Atelier IA local · Infrastructure & OPS")
    serialized: bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return serialized


def render(parts: list[tuple[str, Any]]) -> bytes:
    """Render the existing Markdown block model; ODT is an export, never model text."""
    root = _root("office:document-content")
    auto = _node(root, "office:automatic-styles")
    table_style = _node(auto, "style:style", {"style:name": "DocTable", "style:family": "table"})
    _node(table_style, "style:table-properties", {"style:width": "17cm", "table:align": "left"})
    for name, header in (("Cell", False), ("HeaderCell", True)):
        cell = _node(auto, "style:style", {"style:name": name, "style:family": "table-cell"})
        _node(
            cell,
            "style:table-cell-properties",
            {
                "fo:border": "0.5pt solid #8497a0",
                "fo:padding": "0.15cm",
                "fo:background-color": "#e4eef2" if header else "#ffffff",
            },
        )
        if header:
            _node(cell, "style:text-properties", {"fo:font-weight": "bold"})
    body = _node(_node(root, "office:body"), "office:text")
    listing: ET.Element | None = None
    tables = 0
    for kind, value in parts:
        if kind == "list":
            if listing is None:
                listing = _node(body, "text:list", {"text:style-name": "Bullet"})
            _literal(_node(_node(listing, "text:list-item"), "text:p"), value)
            continue
        listing = None
        if kind == "table":
            tables += 1
            columns = max(map(len, value))
            column = _node(
                auto,
                "style:style",
                {"style:name": f"Columns{tables}", "style:family": "table-column"},
            )
            _node(
                column,
                "style:table-column-properties",
                {"style:column-width": f"{17 / columns:.4f}cm"},
            )
            table = _node(
                body, "table:table", {"table:name": f"Table{tables}", "table:style-name": "DocTable"}
            )
            _node(
                table,
                "table:table-column",
                {
                    "table:style-name": f"Columns{tables}",
                    "table:number-columns-repeated": str(columns),
                },
            )
            for index, row in enumerate(value):
                parent = _node(table, "table:table-header-rows") if index == 0 else table
                tr = _node(parent, "table:table-row")
                for cell_text in [*row, *([""] * (columns - len(row)))]:
                    cell = _node(
                        tr,
                        "table:table-cell",
                        {
                            "office:value-type": "string",
                            "table:style-name": "HeaderCell" if index == 0 else "Cell",
                        },
                    )
                    _literal(_node(cell, "text:p"), cell_text)
        else:
            heading = kind.startswith("h") and kind[1:].isdigit()
            attrs = (
                {"text:outline-level": kind[1:], "text:style-name": kind.upper()}
                if heading
                else {
                    "text:style-name": "Code"
                    if kind == "code"
                    else "Quote"
                    if kind == "quote"
                    else "Standard"
                }
            )
            _literal(_node(body, "text:h" if heading else "text:p", attrs), value)
    manifest = ET.Element(
        "manifest:manifest", {"xmlns:manifest": NS["manifest"], "manifest:version": "1.3"}
    )
    for path, mime in (("/", MIME), ("content.xml", "text/xml"), ("styles.xml", "text/xml")):
        _node(
            manifest, "manifest:file-entry", {"manifest:full-path": path, "manifest:media-type": mime}
        )
    files = {
        "mimetype": MIME.encode(),
        "content.xml": ET.tostring(root, encoding="utf-8", xml_declaration=True),
        "styles.xml": _styles(),
        "META-INF/manifest.xml": ET.tostring(manifest, encoding="utf-8", xml_declaration=True),
    }
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        for name, data in files.items():
            # Stored XML keeps even highly repetitive generated text within the import ratio limit.
            entry = zipfile.ZipInfo(name, (2000, 1, 1, 0, 0, 0))
            entry.external_attr = (stat.S_IFREG | 0o600) << 16
            archive.writestr(entry, data)
    return out.getvalue()


def extract_text(data: bytes, *, max_chars: int = 2_000_000) -> str:
    """Read only text paragraphs/headings in a checked package, without extraction to disk."""
    if len(data) > MAX_INPUT or max_chars < 1:
        raise ValueError("ODT : taille ou budget hors limites")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            if not 1 <= len(infos) <= MAX_MEMBERS:
                raise ValueError("ODT : trop de membres")
            total, seen = 0, set()
            for info in infos:
                path = PurePosixPath(info.filename)
                mode = (info.external_attr >> 16) & 0o170000
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or "\\" in info.filename
                    or not path.parts
                    or info.filename.casefold() in seen
                    or mode not in {0, stat.S_IFREG, stat.S_IFDIR}
                    or info.flag_bits & 1
                ):
                    raise ValueError("ODT : membre interdit, dupliqué, lié ou chiffré")
                seen.add(info.filename.casefold())
                total += info.file_size
                if total > MAX_TOTAL or info.file_size / max(1, info.compress_size) > MAX_RATIO:
                    raise ValueError("ODT : limites de décompression dépassées")
                if (
                    info.filename in {"content.xml", "META-INF/manifest.xml"}
                    and info.file_size > MAX_XML
                ):
                    raise ValueError("ODT : XML trop volumineux")
            if (
                archive.getinfo("mimetype").file_size != len(MIME)
                or archive.read("mimetype") != MIME.encode()
            ):
                raise ValueError("ODT : type MIME invalide")
            manifest = fromstring(
                archive.read("META-INF/manifest.xml"),
                forbid_dtd=True,
                forbid_entities=True,
                forbid_external=True,
            )
            if manifest.tag != f"{{{NS['manifest']}}}manifest":
                raise ValueError("ODT : manifeste invalide")
            if manifest.find(".//manifest:encryption-data", NS) is not None:
                raise ValueError("ODT : document chiffré")
            entries = {
                e.get(f"{{{NS['manifest']}}}full-path"): e.get(f"{{{NS['manifest']}}}media-type")
                for e in manifest.findall("manifest:file-entry", NS)
            }
            if entries.get("/") != MIME or entries.get("content.xml") != "text/xml":
                raise ValueError("ODT : manifeste incompatible")
            content = fromstring(
                archive.read("content.xml"),
                forbid_dtd=True,
                forbid_entities=True,
                forbid_external=True,
            )
    except (
        zipfile.BadZipFile,
        OSError,
        KeyError,
        RuntimeError,
        NotImplementedError,
        ET.ParseError,
        EOFError,
        zlib.error,
    ) as exc:
        raise ValueError("ODT : document illisible ou incomplet") from exc
    if content.tag != f"{{{NS['office']}}}document-content":
        raise ValueError("ODT : contenu incompatible")
    body = content.find("office:body/office:text", NS)
    if body is None:
        raise ValueError("ODT : corps texte absent")
    chunks: list[str] = []
    size = 0

    def add(value: str) -> None:
        nonlocal size
        size += len(value)
        if size > max_chars:
            raise ValueError("ODT : texte dépasse le budget autorisé")
        chunks.append(value)

    def walk(node: ET.Element, depth: int = 0) -> None:
        if depth > 64:
            raise ValueError("ODT : XML trop imbriqué")
        # Refuse compressed logical repetitions instead of silently omitting source text.
        for key in ("number-columns-repeated", "number-rows-repeated"):
            if (
                node.tag != f"{{{NS['table']}}}table-column"
                and int(node.get(f"{{{NS['table']}}}{key}", "1")) != 1
            ):
                raise ValueError("ODT : répétition de cellules non prise en charge")
        if node.text:
            add(node.text)
        for child in node:
            if child.tag == f"{{{NS['text']}}}s":
                count = int(child.get(f"{{{NS['text']}}}c", "1"))
                if not 1 <= count <= max_chars - size:
                    raise ValueError("ODT : répétition d'espaces hors limites")
                add(" " * count)
            elif child.tag == f"{{{NS['text']}}}tab":
                add("\t")
            elif child.tag == f"{{{NS['text']}}}line-break":
                add("\n")
            elif child.tag in {f"{{{NS['office']}}}scripts", f"{{{NS['text']}}}tracked-changes"}:
                continue
            else:
                walk(child, depth + 1)
            if child.tail:
                add(child.tail)
        if node.tag in {f"{{{NS['text']}}}p", f"{{{NS['text']}}}h"}:
            add("\n")

    walk(body)
    result = "".join(chunks).strip()
    if not result:
        raise ValueError("ODT : sans texte exploitable")
    return result
