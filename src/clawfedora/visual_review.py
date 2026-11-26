"""Human-reviewed reception reports over integrity-checked real browser captures.

A screenshot, a DOM overflow probe and an operator attestation are distinct
evidence types. Only the operator can mark a visual assessment as reviewed.
"""

from __future__ import annotations

import argparse
import hashlib
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
PREMIUM_CHECKS = ("typography", "contrast", "graphic_hierarchy", "illustrations",
                  "tablet_layout", "all_six_views_inspected")
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
    if any(path.is_symlink() for path in (manifest_path, *manifest_path.parents)):
        raise ReviewError("chemin de preuves lié interdit")
    record = _load_json(manifest_path, maximum=64_000)
    if (
        record.get("schema") not in {1, 2}
        or record.get("assessment") != "BROWSER_CAPTURED_NOT_VISUALLY_CERTIFIED"
        or record.get("quality_verdict") != "NOT_EVALUATED"
        or record.get("kind") not in REQUIRED
    ):
        raise ReviewError("manifeste de capture inconnu ou déjà altéré")
    vc.validate_url(record["kind"], record["source_url"])
    variants = record.get("screenshots")
    premium = record["schema"] == 2
    sizes = vc.PREMIUM_SIZES if premium else vc.SIZES
    if not isinstance(variants, list) or len(variants) != len(sizes):
        raise ReviewError("configurations de navigateur incomplètes")
    expected = set(sizes)
    actual: set[str] = set()
    hashes: list[str] = []
    filenames: set[str] = set()
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
        width, height, scheme = sizes[view]
        if item.get("requested_color_scheme") != scheme:
            raise ReviewError("préférence de thème incohérente")
        images = item.get("sampled_screenshots")
        if not isinstance(images, list) or not 1 <= len(images) <= vc.MAX_SHOTS:
            raise ReviewError("captures incomplètes")
        for image in images:
            if not isinstance(image, dict) or not isinstance(image.get("filename"), str):
                raise ReviewError("référence d'image invalide")
            name = image["filename"]
            if Path(name).name != name or not name.endswith(".png"):
                raise ReviewError("chemin de capture non autorisé")
            if name in filenames:
                raise ReviewError("capture référencée plusieurs fois")
            filenames.add(name)
            path = root / name
            if path.is_symlink():
                raise ReviewError("image liée interdite")
            metadata = vc._shot(path)
            for key in ("filename", "width", "height", "bytes", "sha256"):
                if metadata[key] != image.get(key):
                    raise ReviewError("capture modifiée depuis son manifeste")
            if (metadata["width"], metadata["height"]) != (width, height):
                raise ReviewError("dimensions de capture différentes du profil")
            hashes.append(metadata["sha256"])
        metrics = item.get("metrics")
        if (
            not isinstance(metrics, dict)
            or type(metrics.get("horizontal_overflow")) is not bool
            or not isinstance(metrics.get("document_width"), int)
            or not isinstance(metrics.get("viewport_width"), int)
            or metrics["viewport_width"] != width
        ):
            raise ReviewError("mesures DOM invalides")
        if premium:
            if (
                metrics.get("viewport_height") != height
                or metrics.get("color_scheme_preference") != scheme
                or type(metrics.get("document_height")) is not int
                or metrics["document_height"] < height
                or type(metrics.get("broken_loaded_images")) is not int
                or metrics["broken_loaded_images"] < 0
            ):
                raise ReviewError("mesures Premium incomplètes ou incohérentes")
            positions = vc.screenshot_positions(metrics["document_height"], height)
            if [image.get("requested_scroll_y") for image in images] != positions or any(
                type(image.get("observed_scroll_y")) not in {int, float}
                or abs(image["observed_scroll_y"] - y) > 5
                for image, y in zip(images, positions, strict=True)
            ):
                raise ReviewError("échantillons de défilement non confirmés")
        metrics_summary.append({
            "view": view,
            "horizontal_overflow": metrics["horizontal_overflow"],
            "document_width": metrics["document_width"],
            "viewport_width": metrics["viewport_width"],
            "broken_loaded_images": metrics.get("broken_loaded_images"),
        })
    if actual != expected:
        raise ReviewError("vues attendues manquantes")
    return record, {
        "screenshot_count": len(hashes),
        "distinct_screenshot_count": len(set(hashes)),
        "layout_metrics": metrics_summary,
    }


def evaluate(manifest_path: Path, review_path: Path) -> dict[str, Any]:
    manifest, summary = _verify_capture(manifest_path)
    review = _load_json(review_path, maximum=12_000)
    premium = manifest["schema"] == 2
    expected = REQUIRED[manifest["kind"]] + (PREMIUM_CHECKS if premium else ())
    keys = {"inspected_live_site", "checks"}
    if premium:
        keys.update({"manifest_sha256", "observed_themes"})
    if (
        set(review) != keys
        or review["inspected_live_site"] is not True
        or not isinstance(review["checks"], dict)
        or set(review["checks"]) != set(expected)
        or any(review["checks"][field] not in STATES for field in expected)
    ):
        raise ReviewError("revue humaine live et grille intégrale obligatoires")
    if premium and (
        review["manifest_sha256"] != hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        or not isinstance(review["observed_themes"], dict)
        or set(review["observed_themes"]) != set(vc.PREMIUM_SIZES)
        or any(value not in {"light", "dark", "NOT_EVALUATED"}
               for value in review["observed_themes"].values())
    ):
        raise ReviewError("attestation Premium non liée ou thèmes incomplets")
    observations = review["checks"]
    failed = [key for key in expected if observations[key] == "FAIL"]
    missing = [key for key in expected if observations[key] == "NOT_EVALUATED"]
    overflows = [
        item["view"] for item in summary["layout_metrics"]
        if item["horizontal_overflow"]
    ]
    if overflows:
        failed.append("horizontal_overflow_detected")
    if premium:
        for view, (_, _, scheme) in vc.PREMIUM_SIZES.items():
            observed = review["observed_themes"][view]
            if observed == "NOT_EVALUATED":
                missing.append(f"theme:{view}")
            elif observed != scheme:
                failed.append(f"theme:{view}")
        if any(row["broken_loaded_images"] for row in summary["layout_metrics"]):
            failed.append("broken_loaded_images_detected")
    status = (
        "OPERATOR_REVIEW_FAILED" if failed else
        "OPERATOR_REVIEW_INCOMPLETE" if missing else
        "OPERATOR_REVIEW_REPORTED_PASS"
    )
    return {
        "schema": manifest["schema"], "assessment": status,
        "capture_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
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


def _write_private(path: Path, manifest: Path, data: dict[str, Any]) -> None:
    if (
        not path.is_absolute() or path.parent != manifest.parent
        or path.is_symlink() or path.exists()
    ):
        raise ReviewError("nouveau fichier privé dans le dossier de capture requis")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="clawfedora-visual-review")
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--review", type=Path)
    p.add_argument("--template-out", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--apply", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.template_out is not None:
            if args.review is not None or args.output is not None or args.apply:
                raise ReviewError("mode modèle exclusif : aucun reçu produit")
            manifest, _ = _verify_capture(args.manifest)
            template: dict[str, Any] = {
                "inspected_live_site": False,
                "checks": dict.fromkeys(REQUIRED[manifest["kind"]], "NOT_EVALUATED"),
            }
            if manifest["schema"] == 2:
                template["checks"].update(dict.fromkeys(PREMIUM_CHECKS, "NOT_EVALUATED"))
                template["manifest_sha256"] = hashlib.sha256(args.manifest.read_bytes()).hexdigest()
                template["observed_themes"] = dict.fromkeys(vc.PREMIUM_SIZES, "NOT_EVALUATED")
            _write_private(args.template_out, args.manifest, template)
            print(json.dumps({
                "assessment": "REVIEW_TEMPLATE_CREATED_NOT_COMPLETED",
                "template": str(args.template_out),
            }, ensure_ascii=False))
            return 0
        if args.review is None:
            raise ReviewError("--review ou --template-out requis")
        result = evaluate(args.manifest, args.review)
        if args.apply:
            if args.output is None:
                raise ReviewError("--output requis")
            _write_private(args.output, args.manifest, result)
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
