"""Premium capture evidence cannot substitute for human review of six actual views."""
from __future__ import annotations

import hashlib
import json

import pytest
from PIL import Image

from clawfedora import visual_capture as vc
from clawfedora import visual_review as vr


@pytest.fixture
def premium(tmp_path):
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    record = {
        "schema": 2, "assessment": "BROWSER_CAPTURED_NOT_VISUALLY_CERTIFIED",
        "quality_verdict": "NOT_EVALUATED", "kind": "local-notion",
        "source_url": "http://127.0.0.1:18890/notion.html", "screenshots": [],
    }
    for index, (name, (width, height, scheme)) in enumerate(vc.PREMIUM_SIZES.items()):
        path = root / f"{name}.png"
        Image.new("RGB", (width, height), (index * 35, 60, 80)).save(path)
        record["screenshots"].append({
            "view": name, "requested_color_scheme": scheme,
            "metrics": {
                "viewport_width": width, "viewport_height": height,
                "document_width": width, "document_height": height,
                "horizontal_overflow": False, "color_scheme_preference": scheme,
                "broken_loaded_images": 0,
            },
            "sampled_screenshots": [{**vc._shot(path), "requested_scroll_y": 0,
                                     "observed_scroll_y": 0}],
        })
    manifest = root / "manifest.json"
    form = root / "review.json"

    def save():
        manifest.write_text(json.dumps(record))
        manifest.chmod(0o600)
        data = {
            "inspected_live_site": True,
            "checks": dict.fromkeys(vr.REQUIRED["local-notion"] + vr.PREMIUM_CHECKS, "PASS"),
            "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
            "observed_themes": {key: scheme for key, (_, _, scheme) in vc.PREMIUM_SIZES.items()},
        }
        form.write_text(json.dumps(data))
        form.chmod(0o600)
        return data

    save()
    return manifest, form, record, save


def test_premium_six_views_and_attestation(premium):
    manifest, form, _, _ = premium
    result = vr.evaluate(manifest, form)
    assert result["assessment"] == "OPERATOR_REVIEW_REPORTED_PASS"
    assert result["evidence"]["screenshot_count"] == 6
    assert result["automation_visual_certification"] is False
    assert result["capture_manifest_sha256"] == hashlib.sha256(manifest.read_bytes()).hexdigest()


def test_template_never_autocertifies_theme(premium):
    manifest, _, _, _ = premium
    template = manifest.parent / "template.json"
    assert vr.main(["--manifest", str(manifest), "--template-out", str(template)]) == 0
    value = json.loads(template.read_text())
    assert value["inspected_live_site"] is False
    assert set(value["observed_themes"]) == set(vc.PREMIUM_SIZES)
    assert set(value["observed_themes"].values()) == {"NOT_EVALUATED"}
    assert set(value["checks"].values()) == {"NOT_EVALUATED"}


def test_theme_mismatch_or_missing_blocks_pass(premium):
    manifest, form, _, save = premium
    data = save()
    data["observed_themes"]["mobile_dark"] = "light"
    form.write_text(json.dumps(data))
    assert vr.evaluate(manifest, form)["assessment"] == "OPERATOR_REVIEW_FAILED"
    data["observed_themes"]["mobile_dark"] = "NOT_EVALUATED"
    form.write_text(json.dumps(data))
    assert vr.evaluate(manifest, form)["assessment"] == "OPERATOR_REVIEW_INCOMPLETE"


@pytest.mark.parametrize("fault", ["overflow", "image"])
def test_machine_signals_override_human_pass(premium, fault):
    manifest, form, record, save = premium
    metrics = record["screenshots"][0]["metrics"]
    if fault == "overflow":
        metrics["horizontal_overflow"] = True
        metrics["document_width"] += 50
    else:
        metrics["broken_loaded_images"] = 1
    save()
    assert vr.evaluate(manifest, form)["assessment"] == "OPERATOR_REVIEW_FAILED"


@pytest.mark.parametrize("fault", ["missing", "scroll", "theme", "viewport", "duplicate"])
def test_refuse_inconsistent_capture(premium, fault):
    manifest, form, record, save = premium
    if fault == "missing":
        record["screenshots"].pop()
    elif fault == "scroll":
        record["screenshots"][0]["sampled_screenshots"][0]["observed_scroll_y"] = 100
    elif fault == "theme":
        record["screenshots"][0]["metrics"]["color_scheme_preference"] = "dark"
    elif fault == "viewport":
        record["screenshots"][0]["metrics"]["viewport_width"] = 390
    else:
        record["screenshots"][1]["sampled_screenshots"] = (
            record["screenshots"][0]["sampled_screenshots"]
        )
    save()
    with pytest.raises(vr.ReviewError):
        vr.evaluate(manifest, form)


def test_manifest_edit_invalidates_attestation(premium):
    manifest, form, _, _ = premium
    manifest.write_text(manifest.read_text() + "\n")
    with pytest.raises(vr.ReviewError, match="non liée"):
        vr.evaluate(manifest, form)


def test_github_redirect_to_another_repository_is_refused():
    with pytest.raises(vc.CaptureError):
        vc._validate_final_url("github-readme", "https://github.com/example/one",
                               "https://github.com/example/two")


def test_premium_dry_run_does_not_capture(tmp_path, capsys):
    assert vc.main([
        "--kind", "local-notion", "--url", "http://127.0.0.1:18890/notion.html",
        "--output-dir", str(tmp_path), "--premium",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["views"] == list(vc.PREMIUM_SIZES)
    assert not list(tmp_path.iterdir())
