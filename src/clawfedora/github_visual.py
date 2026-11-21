"""Inspect actual user-provided GitHub browser screenshots for evidence integrity.

No browser automation or visual pass claim: dimensions, formats, distinct files,
hashes and operator attestation only. Does not modify source images.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

REPO_URL = re.compile(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?\Z")
MAX_BYTES = 15_000_000
MAX_DIMENSION = 10000
CATEGORIES = ("desktop_light", "desktop_dark", "mobile")


class VisualEvidenceError(ValueError):
    """No unsupported graphical success claim."""


def _picture(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise VisualEvidenceError("capture absente ou liée")
    if path.stat().st_size > MAX_BYTES:
        raise VisualEvidenceError("capture trop volumineuse")
    try:
        with Image.open(path) as image:
            if image.format not in ("PNG", "JPEG", "WEBP"):
                raise VisualEvidenceError("format d'image non pris en charge")
            width, height = image.size
            if not 320 <= width <= MAX_DIMENSION or not 320 <= height <= MAX_DIMENSION:
                raise VisualEvidenceError("dimensions de capture anormales")
            image.verify()
    except (OSError, ValueError, UnidentifiedImageError) as exc:
        raise VisualEvidenceError("image invalide ou illisible") from exc
    return {
        "filename": path.name, "width": width, "height": height,
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def evidence(
    repository_url: str, captures: dict[str, Path], *,
    reviewed_by_operator: bool = False,
) -> dict[str, Any]:
    if REPO_URL.fullmatch(repository_url) is None:
        raise VisualEvidenceError("URL canonique du dépôt GitHub requise")
    if set(captures) != set(CATEGORIES):
        raise VisualEvidenceError("captures desktop clair/sombre et mobile requises")
    pictures = {category: _picture(captures[category]) for category in CATEGORIES}
    hashes = [record["sha256"] for record in pictures.values()]
    if len(set(hashes)) != len(hashes):
        raise VisualEvidenceError("captures dupliquées ; trois vues indépendantes requises")
    return {
        "assessment": "IMAGES_COLLECTED_NOT_VISUALLY_CERTIFIED",
        "repository": repository_url.rstrip("/"),
        "screenshots": pictures,
        "operator_visual_review_reported": reviewed_by_operator,
        "quality_verdict": "NOT_EVALUATED",
        "limitations": [
            "Pas de navigateur utilisé par cette commande",
            "Aucune vérification automatique des textes, contrastes ou débordements",
            "La capture et la déclaration humaine ne valident pas les tests Fedora",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clawfedora-github-visual")
    parser.add_argument("--repo-url", required=True)
    parser.add_argument("--desktop-light", type=Path, required=True)
    parser.add_argument("--desktop-dark", type=Path, required=True)
    parser.add_argument("--mobile", type=Path, required=True)
    parser.add_argument("--reviewed-by-operator", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--apply", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = evidence(
            args.repo_url,
            {
                "desktop_light": args.desktop_light,
                "desktop_dark": args.desktop_dark,
                "mobile": args.mobile,
            },
            reviewed_by_operator=args.reviewed_by_operator,
        )
        if args.apply:
            if args.output is None or not args.reviewed_by_operator:
                raise VisualEvidenceError("sortie et déclaration de revue manuelle requises")
            output = args.output
            if output.is_symlink() or output.exists() or not output.parent.is_dir():
                raise VisualEvidenceError("sortie existante, liée ou dossier parent absent")
            with output.open("x", encoding="utf-8") as stream:
                json.dump(result, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (VisualEvidenceError, OSError, ValueError) as exc:
        print(json.dumps({"assessment": "REFUSED", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
