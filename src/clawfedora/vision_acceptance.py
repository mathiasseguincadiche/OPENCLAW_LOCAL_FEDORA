"""Manual acceptance with synthetic, non-private PNG and scanned PDF.

Opt-in only. Uses clawfedora.local_vision which refuses cloud routing and
requires the user's private vision marker and preflight.
"""
from __future__ import annotations

import argparse
import io
import json
import tempfile
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageDraw
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from clawfedora.local_vision import local_vision

Vision = Callable[..., dict[str, Any]]


def vision_smoke(repo_root: Path, runtime: Path, *, vision: Vision = local_vision) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="clawfedora-vision-check-") as directory:
        root = Path(directory)
        image = Image.new("RGB", (240, 160), "white")
        ImageDraw.Draw(image).rectangle((30, 30, 100, 100), fill="red")
        png = root / "synthetic-red-square.png"
        image.save(png)
        pdf = root / "synthetic-scanned.pdf"
        with pdf.open("wb") as stream:
            doc = canvas.Canvas(stream, pagesize=(400, 300))
            doc.drawImage(ImageReader(image), 60, 60, width=240, height=160)
            doc.showPage()
            doc.save()
        examples = (("image", png), ("scanned_pdf", pdf))
        records = []
        for kind, source in examples:
            result = vision(
                repo_root, runtime, source, source.name, maximum_output=12_000
            )
            text = result.get("text")
            if not isinstance(text, str) or not text.strip():
                raise ValueError("réponse vision locale vide")
            records.append({
                "kind": kind,
                "response_received": True,
                "description": text[:1500],
                "source": "synthetic_non_private_fixture",
                "manual_visual_accuracy_review_required": True,
            })
    return {
        "verdict": "LOCAL_VISION_RESPONDED_NOT_ACCURACY_CERTIFIED",
        "cloud_route_enabled_by_test": False,
        "private_sources_used": False,
        "manual_review_required": True,
        "results": records,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Épreuve locale PNG/PDF sans données privées")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    if not args.apply:
        print(json.dumps({
            "verdict": "DRY_RUN", "requires_local_vision_private_opt_in": True,
            "requests_sent": 0, "cloud_used": False,
        }))
        return 0
    try:
        result = vision_smoke(args.root, args.runtime_root)
    except (ValueError, OSError, TimeoutError) as exc:
        print(json.dumps({"verdict": "REFUSED", "reason": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
