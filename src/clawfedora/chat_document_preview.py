"""Bounded offline document previews for *local* Open WebUI chat.

Text is untrusted content, not instructions. Image bytes are deliberately not
passed to text-only Qwen: only independently verified file metadata is shown.
"""

from __future__ import annotations

import io
import re
import stat
import zipfile
from pathlib import Path
from typing import Any

from defusedxml.ElementTree import fromstring
from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader

MAX_INPUT = 2 * 1024 * 1024
MAX_PDF_PAGES = 12
MAX_OFFICE_MEMBERS = 100
MAX_OFFICE_XML = 1024 * 1024
MAX_OFFICE_TOTAL = 4 * 1024 * 1024
MAX_IMAGE_PIXELS = 12_000_000

PDF_SUFFIXES = frozenset({".pdf"})
OFFICE_SUFFIXES = frozenset({".docx", ".pptx", ".xlsx"})
IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp"})
SUPPORTED_SUFFIXES = PDF_SUFFIXES | OFFICE_SUFFIXES | IMAGE_SUFFIXES

_SLIDE = re.compile(r"ppt/slides/slide[0-9]{1,3}\.xml$")
_SHEET = re.compile(r"xl/worksheets/sheet[0-9]{1,3}\.xml$")


def preview_document(path: Path, name: str, budget: int) -> dict[str, Any]:
    """Return bounded extracted text or explicit *metadata-only* image status."""
    if budget < 256:
        raise ValueError("budget de contexte local insuffisant")
    if path.is_symlink() or not path.is_file():
        raise ValueError("pièce jointe liée ou non régulière")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_INPUT:
        raise ValueError("document limité à 2 Mio en chat libre")
    suffix = Path(name).suffix.casefold()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError("type de document non autorisé")
    # Limiting bytes before parsing bounds the input to every document handler.
    raw = path.read_bytes()
    if suffix in PDF_SUFFIXES:
        content = _pdf(raw, budget)
        return {"type": "pdf-text", "note": "Texte PDF uniquement, sans OCR", "text": content}
    if suffix in OFFICE_SUFFIXES:
        content = _office(raw, suffix, budget)
        return {
            "type": "office-text",
            "note": "Extraction textuelle partielle, sans mise en page ni formules garanties",
            "text": content,
        }
    return _image(raw, suffix)


def _pdf(data: bytes, budget: int) -> str:
    if not data.startswith(b"%PDF-"):
        raise ValueError("PDF invalide")
    try:
        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise ValueError("PDF chiffré non accepté")
        if not 1 <= len(reader.pages) <= MAX_PDF_PAGES:
            raise ValueError("PDF : 1 à 12 pages maximum")
        pieces: list[str] = []
        for number, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ""
            if text.strip():
                pieces.append(f"[page {number}]\n{text.strip()}")
        combined = "\n\n".join(pieces)
        if not combined.strip():
            raise ValueError("PDF scanné sans texte : analyse visuelle requise dans un projet")
        if len(combined.encode("utf-8")) > budget:
            raise ValueError("texte PDF dépasse le contexte local : utiliser un projet")
        return combined
    except (OSError, IndexError, KeyError, TypeError) as exc:
        raise ValueError("PDF non analysable par le lecteur texte") from exc


def _wanted(name: str, suffix: str) -> bool:
    if suffix == ".docx":
        return name == "word/document.xml"
    if suffix == ".pptx":
        return bool(_SLIDE.fullmatch(name))
    return name == "xl/sharedStrings.xml" or bool(_SHEET.fullmatch(name))


def _office(data: bytes, suffix: str, budget: int) -> str:
    text: list[str] = []
    total = 0
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_OFFICE_MEMBERS:
                raise ValueError("document Office contient trop de membres")
            selected = sorted((i for i in infos if _wanted(i.filename, suffix)),
                              key=lambda i: i.filename)
            if not selected:
                raise ValueError("document Office sans contenu XML attendu")
            for item in infos:
                if item.flag_bits & 1:
                    raise ValueError("document Office chiffré")
                mode = (item.external_attr >> 16) & 0o170000
                if mode not in {0, stat.S_IFREG, stat.S_IFDIR}:
                    raise ValueError("lien ou fichier spécial dans Office")
                if item.file_size > MAX_OFFICE_XML and item in selected:
                    raise ValueError("XML Office trop volumineux")
            for item in selected:
                total += item.file_size
                if (total > MAX_OFFICE_TOTAL or
                        item.file_size / max(1, item.compress_size) > 100):
                    raise ValueError("Office dépasse les limites de décompression")
                root = fromstring(
                    archive.read(item),
                    forbid_dtd=True,
                    forbid_entities=True,
                    forbid_external=True,
                )
                # ElementTree itertext deliberately drops formatting, macros and hyperlinks.
                section = " ".join(value.strip() for value in root.itertext() if value.strip())
                if section:
                    text.append(f"[{item.filename}]\n{section}")
                if len("\n\n".join(text).encode()) > budget:
                    raise ValueError("texte Office dépasse le contexte local : utiliser un projet")
        if not text:
            raise ValueError("Office sans texte exploitable")
        return "\n\n".join(text)
    except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
        raise ValueError("document Office illisible") from exc


def _image(data: bytes, suffix: str) -> dict[str, Any]:
    try:
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            fmt = image.format
            if (
                width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS
                or fmt not in {"PNG", "JPEG", "WEBP"}
                or (suffix == ".png" and fmt != "PNG")
                or (suffix in {".jpg", ".jpeg"} and fmt != "JPEG")
                or (suffix == ".webp" and fmt != "WEBP")
            ):
                raise ValueError("image invalide, trop grande ou type divergent")
            image.verify()
        return {
            "type": "image-metadata-only",
            "width": width,
            "height": height,
            "format": fmt,
            "note": (
                "Pixels non transmis au modèle texte. Aucune analyse visuelle "
                "n'a été effectuée ; utiliser la chaîne image du projet."
            ),
        }
    except (OSError, UnidentifiedImageError) as exc:
        raise ValueError("image illisible") from exc
