"""Human visual claims are separate from browser metrics and screenshot integrity."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from clawfedora import visual_capture as capture
from clawfedora import visual_review as review


def _evidence(
    tmp_path: Path, *, overflow: bool = False,
) -> tuple[Path, Path, dict[str, Any]]:
    root = tmp_path / "private-captures"
    root.mkdir(mode=0o700)
    record: dict[str, Any] = {
        "schema": 1, "assessment": "BROWSER_CAPTURED_NOT_VISUALLY_CERTIFIED",
        "quality_verdict": "NOT_EVALUATED",
        "kind": "local-notion",
        "source_url": "http://127.0.0.1:18890/notion.html",
        "screenshots": [],
    }
    for index, (name, (width, height, scheme)) in enumerate(capture.SIZES.items()):
        image_path = root / (name + ".png")
        Image.new("RGB", (width, height), (index * 50, 60, 80)).save(image_path)
        captured = capture._shot(image_path)
        record["screenshots"].append({
            "view": name, "requested_color_scheme": scheme,
            "metrics": {
                "viewport_width": width, "document_width": width + (10 if overflow else 0),
                "horizontal_overflow": overflow,
            },
            "sampled_screenshots": [{**captured, "requested_scroll_y": 0}],
        })
    manifest = root / "manifest.json"
    manifest.write_text(json.dumps(record), encoding="utf-8")
    manifest.chmod(0o600)
    observations = {
        "inspected_live_site": True,
        "checks": dict.fromkeys(review.REQUIRED["local-notion"], "PASS"),
    }
    assessed = root / "operator-review.json"
    assessed.write_text(json.dumps(observations), encoding="utf-8")
    assessed.chmod(0o600)
    return manifest, assessed, observations


def test_pass_is_attributed_only_to_human_not_automation(tmp_path: Path) -> None:
    manifest, form, _ = _evidence(tmp_path)
    result = review.evaluate(manifest, form)
    assert result["assessment"] == "OPERATOR_REVIEW_REPORTED_PASS"
    assert result["automation_visual_certification"] is False
    assert result["human_review_claimed"] is True
    assert result["evidence"]["screenshot_count"] == 3


def test_operator_review_rejects_missing_checks(tmp_path: Path) -> None:
    manifest, form, data = _evidence(tmp_path)
    data["checks"].pop("mobile_layout")
    form.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(review.ReviewError, match="intégrale"):
        review.evaluate(manifest, form)
    data["checks"]["mobile_layout"] = "NOT_EVALUATED"
    form.write_text(json.dumps(data), encoding="utf-8")
    result = review.evaluate(manifest, form)
    assert result["assessment"] == "OPERATOR_REVIEW_INCOMPLETE"
    assert result["unevaluated_checks"] == ["mobile_layout"]


def test_operator_failure_and_overflow_cannot_pass(tmp_path: Path) -> None:
    manifest, form, data = _evidence(tmp_path, overflow=True)
    result = review.evaluate(manifest, form)
    assert result["assessment"] == "OPERATOR_REVIEW_FAILED"
    assert "horizontal_overflow_detected" in result["failed_checks"]
    data["checks"]["links"] = "FAIL"
    form.write_text(json.dumps(data), encoding="utf-8")
    assert "links" in review.evaluate(manifest, form)["failed_checks"]


def test_mutated_screenshot_fails_integrity(tmp_path: Path) -> None:
    manifest, form, _ = _evidence(tmp_path)
    target = manifest.parent / "desktop_light.png"
    Image.new("RGB", (1440, 900), "red").save(target)
    with pytest.raises(review.ReviewError, match="modifiée"):
        review.evaluate(manifest, form)


def test_operator_must_have_inspected_live_page(tmp_path: Path) -> None:
    manifest, form, data = _evidence(tmp_path)
    data["inspected_live_site"] = False
    form.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(review.ReviewError, match="live"):
        review.evaluate(manifest, form)


def test_no_output_without_apply_and_no_overwrite(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    manifest, form, _ = _evidence(tmp_path)
    output = manifest.parent / "review-receipt.json"
    args = [
        "--manifest", str(manifest), "--review", str(form),
        "--output", str(output),
    ]
    assert review.main(args) == 0
    assert not output.exists()
    capsys.readouterr()
    assert review.main(args + ["--apply"]) == 0
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["automation_visual_certification"] is False
    assert output.stat().st_mode & 0o077 == 0
    capsys.readouterr()
    assert review.main(args + ["--apply"]) == 2


def test_privacy_of_manifest_and_report_is_mandatory(tmp_path: Path) -> None:
    manifest, form, _ = _evidence(tmp_path)
    form.chmod(0o644)
    with pytest.raises(review.ReviewError, match="privé"):
        review.evaluate(manifest, form)
    form.chmod(0o600)
    manifest.chmod(0o644)
    with pytest.raises(review.ReviewError, match="privé"):
        review.evaluate(manifest, form)


def test_generate_explicit_review_template_without_auto_pass(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    manifest, _, _ = _evidence(tmp_path)
    template = manifest.parent / "new-review.json"
    assert review.main([
        "--manifest", str(manifest), "--template-out", str(template),
    ]) == 0
    assert template.stat().st_mode & 0o077 == 0
    values = json.loads(template.read_text(encoding="utf-8"))
    assert values["inspected_live_site"] is False
    assert set(values["checks"]) == set(review.REQUIRED["local-notion"])
    assert set(values["checks"].values()) == {"NOT_EVALUATED"}
    assert "NOT_COMPLETED" in capsys.readouterr().out
    assert review.main([
        "--manifest", str(manifest), "--template-out", str(template),
    ]) == 2
