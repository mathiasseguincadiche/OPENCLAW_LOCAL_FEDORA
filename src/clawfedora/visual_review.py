"""Human-reviewed reception reports over integrity-checked real browser captures.

A screenshot, a DOM overflow probe and an operator attestation are distinct
evidence types. Only the operator can mark a visual assessment as reviewed.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from clawfedora import visual_capture as vc

COMMON = (
    "navigation", "readability", "content_accuracy",
    "links", "desktop_light_dark", "mobile_layout", "no_overlap",
)
REQUIRED = {
    "local-notion": COMMON + ("approval_controls", "installation_tools_preserved"),
    "local-github": COMMON + ("pr_approval_controls", "dashboard_statuses"),
    "github-readme": COMMON + ("readme_architecture", "svg_diagrams_and_captions"),
    "notion-page": COMMON + (
        "callouts_tables_and_images", "installation_tools_preserved",
        "child_pages_and_progress_preserved",
    ),
}
STATES = frozenset({"PASS", "FAIL", "NOT_EVALUATED"})


class ReviewError(ValueError):
    """Evidence/attestation cannot safely support the requested conclusion."""


def _load_json(path: Path, *, maximum: int) -> dict[str, Any]:
    if (
        path.is_symlink() or not path.is_file() or path.stat().st_size > maximum
        or stat.S_IMODE(path.stat().st_mode) & 0o077
    ):
        raise ReviewError("fichier privé, régulier et de taille limitée requis")
    try:
        value: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise ReviewError("JSON de réception invalide") from exc
    if not isinstance(value, dict):
        raise ReviewError("objet JSON requis")
    return cast(dict[str, Any], value)


def _verify_capture(manifest_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    record = _load_json(manifest_path, maximum=64_000)
    if (
        record.get("schema") != 1
        or record.get("assessment") != "BROWSER_CAPTURED_NOT_VISUALLY_CERTIFIED"
        or record.get("quality_verdict") != "NOT_EVALUATED"
        or record.get("kind") not in REQUIRED
    ):
        raise ReviewError("manifeste de capture inconnu ou déjà altéré")
    vc.validate_url(record["kind"], record["source_url"])
    variants = record.get("screenshots")
    if not isinstance(variants, list) or len(variants) != 3:
        raise ReviewError("trois configurations de navigateur requises")
    expected = set(vc.SIZES)
    actual: set[str] = set()
    hashes: list[str] = []
    metrics_summary: list[dict[str, Any]] = []
    root = manifest_path.parent
    if stat.S_IMODE(root.stat().st_mode) & 0o077:
        raise ReviewError("dossier de preuves privé requis (chmod 700)")
    for item in variants:
        if not isinstance(item, dict) or item.get("view") not in expected:
            raise ReviewError("configuration de capture non reconnue")
        view = item["view"]
        if view in actual:
            raise ReviewError("configuration de capture dupliquée")
        actual.add(view)
        images = item.get("sampled_screenshots")
        if not isinstance(images, list) or not 1 <= len(images) <= vc.MAX_SHOTS:
            raise ReviewError("captures incomplètes")
        for image in images:
            if not isinstance(image, dict) or not isinstance(image.get("filename"), str):
                raise ReviewError("référence d'image invalide")
            name = image["filename"]
            if Path(name).name != name or not name.endswith(".png"):
                raise ReviewError("chemin de capture non autorisé")
            path = root / name
            if path.is_symlink():
                raise ReviewError("image liée interdite")
            metadata = vc._shot(path)
            for key in ("filename", "width", "height", "bytes", "sha256"):
                if metadata[key] != image.get(key):
                    raise ReviewError("capture modifiée depuis son manifeste")
            hashes.append(metadata["sha256"])
        metrics = item.get("metrics")
        if (
            not isinstance(metrics, dict)
            or type(metrics.get("horizontal_overflow")) is not bool
            or not isinstance(metrics.get("document_width"), int)
            or not isinstance(metrics.get("viewport_width"), int)
            or metrics["viewport_width"] < 320
        ):
            raise ReviewError("mesures DOM invalides")
        metrics_summary.append({
            "view": view,
            "horizontal_overflow": metrics["horizontal_overflow"],
            "document_width": metrics["document_width"],
            "viewport_width": metrics["viewport_width"],
        })
    if actual != expected:
        raise ReviewError("vues de bureau clair, sombre et mobile manquantes")
    return record, {
        "screenshot_count": len(hashes),
        "distinct_screenshot_count": len(set(hashes)),
        "layout_metrics": metrics_summary,
    }


def evaluate(manifest_path: Path, review_path: Path) -> dict[str, Any]:
    manifest, summary = _verify_capture(manifest_path)
    review = _load_json(review_path, maximum=12_000)
    expected = REQUIRED[manifest["kind"]]
    if (
        set(review) != {"inspected_live_site", "checks"}
        or review["inspected_live_site"] is not True
        or not isinstance(review["checks"], dict)
        or set(review["checks"]) != set(expected)
        or any(review["checks"][field] not in STATES for field in expected)
    ):
        raise ReviewError("revue humaine live et grille intégrale obligatoires")
    observations = review["checks"]
    failed = [key for key in expected if observations[key] == "FAIL"]
    missing = [key for key in expected if observations[key] == "NOT_EVALUATED"]
    overflows = [
        item["view"] for item in summary["layout_metrics"]
        if item["horizontal_overflow"]
    ]
    if overflows:
        failed.append("horizontal_overflow_detected")
    status = (
        "OPERATOR_REVIEW_FAILED" if failed else
        "OPERATOR_REVIEW_INCOMPLETE" if missing else
        "OPERATOR_REVIEW_REPORTED_PASS"
    )
    return {
        "schema": 1, "assessment": status,
        "kind": manifest["kind"], "source_url": manifest["source_url"],
        "reviewed_at": datetime.now(UTC).isoformat(),
        "operator_observations": observations,
        "failed_checks": failed, "unevaluated_checks": missing,
        "evidence": summary, "human_review_claimed": True,
        "automation_visual_certification": False,
        "limitations": [
            "Résultat déclaré par l'opérateur, sans certification graphique automatique",
            "Captures échantillonnées : parcourir toutes les sections et liens en direct",
            "Les tests Fedora, Notion externe et GitHub ne sont pas substituables",
        ],
    }


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="clawfedora-visual-review")
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--review", type=Path, required=True)
    p.add_argument("--output", type=Path)
    p.add_argument("--apply", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = evaluate(args.manifest, args.review)
        if args.apply:
            output = args.output
            if (
                output is None or not output.is_absolute()
                or output.parent != args.manifest.parent
                or output.exists() or output.is_symlink()
            ):
                raise ReviewError("nouveau reçu privé dans le dossier de capture requis")
            descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(result, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ReviewError, vc.CaptureError, OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({
            "assessment": "REVIEW_REFUSED", "reason": str(exc),
            "automation_visual_certification": False,
        }, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
