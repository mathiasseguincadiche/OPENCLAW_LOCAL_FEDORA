"""Validate PDF and image previews using ONLY production package dependencies.

Run in a freshly installed environment: `pip install -e .`, not `.[dev]`.
This smoke test prevents a CI dev environment from hiding runtime import gaps.
"""

from __future__ import annotations

import io
import tempfile
from pathlib import Path

from PIL import Image
from reportlab.pdfgen import canvas

from clawfedora.chat_document_preview import preview_document
from clawfedora.document_exports import export


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="clawfedora-runtime-smoke-") as directory:
        root = Path(directory)
        pdf = root / "runbook.pdf"
        stream = io.BytesIO()
        page = canvas.Canvas(stream)
        page.drawString(40, 700, "Infrastructure DevOps verified")
        page.save()
        pdf.write_bytes(stream.getvalue())
        result = preview_document(pdf, pdf.name, 12_000)
        if result["type"] != "pdf-text" or "Infrastructure DevOps" not in result["text"]:
            raise SystemExit("PRODUCTION_DOCUMENT_SMOKE=FAIL PDF text extraction")
        odt = root / "runbook.odt"
        odt.write_bytes(export("# Infrastructure DevOps\n\nProcédure vérifiée.", "odt"))
        result = preview_document(odt, odt.name, 12_000)
        if result["type"] != "odt-text" or "Procédure vérifiée." not in result["text"]:
            raise SystemExit("PRODUCTION_DOCUMENT_SMOKE=FAIL ODT round trip")
        image = root / "image.png"
        Image.new("RGB", (14, 10)).save(image, format="PNG")
        result = preview_document(image, image.name, 12_000)
        if result["type"] != "image-metadata-only" or result["width"] != 14 or result["height"] != 10:
            raise SystemExit("PRODUCTION_DOCUMENT_SMOKE=FAIL image validation")
    print(
        "PRODUCTION_DOCUMENT_SMOKE=PASS pdf=pypdf odt=stdlib+defusedxml "
        "image=Pillow dev_extra=not_used"
    )


if __name__ == "__main__":
    main()
