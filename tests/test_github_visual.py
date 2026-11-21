"""Screenshot integrity checks never assert UI quality without browser review."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from clawfedora import github_visual

URL = "https://github.com/example/infraops"


def _shots(tmp_path: Path) -> dict[str, Path]:
    names = ["light.png", "dark.png", "mobile.png"]
    sizes = [(1280, 800), (1360, 820), (390, 800)]
    for name, size in zip(names, sizes, strict=True):
        Image.new("RGB", size, color="white").save(tmp_path / name)
    return dict(zip(github_visual.CATEGORIES, (tmp_path / n for n in names), strict=True))


def test_preview_requires_three_distinct_real_image_files(
    tmp_path: Path,
) -> None:
    shots = _shots(tmp_path)
    result = github_visual.evidence(URL, shots)
    assert result["quality_verdict"] == "NOT_EVALUATED"
    assert result["assessment"] == "IMAGES_COLLECTED_NOT_VISUALLY_CERTIFIED"
    assert result["operator_visual_review_reported"] is False
    assert {x["width"] for x in result["screenshots"].values()} == {1280, 1360, 390}


def test_missing_or_duplicate_capture_refused(tmp_path: Path) -> None:
    shots = _shots(tmp_path)
    with pytest.raises(github_visual.VisualEvidenceError):
        github_visual.evidence(URL, {"desktop_light": shots["desktop_light"]})
    shots["desktop_dark"] = shots["desktop_light"]
    with pytest.raises(github_visual.VisualEvidenceError, match="dupliquées"):
        github_visual.evidence(URL, shots)


def test_symlink_or_fake_png_refused(tmp_path: Path) -> None:
    shots = _shots(tmp_path)
    target = tmp_path / "fake.png"
    target.write_text("NOT A REAL IMAGE", encoding="utf-8")
    shots["desktop_light"] = target
    with pytest.raises(github_visual.VisualEvidenceError):
        github_visual.evidence(URL, shots)
    shots["desktop_light"] = tmp_path / "linked.png"
    shots["desktop_light"].symlink_to(tmp_path / "dark.png")
    with pytest.raises(github_visual.VisualEvidenceError):
        github_visual.evidence(URL, shots)


def test_cli_writes_only_after_explicit_attestation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    shots = _shots(tmp_path)
    output = tmp_path / "visual-report.json"
    args = [
        "--repo-url", URL,
        "--desktop-light", str(shots["desktop_light"]),
        "--desktop-dark", str(shots["desktop_dark"]),
        "--mobile", str(shots["mobile"]),
        "--output", str(output),
    ]
    assert github_visual.main(args) == 0
    assert not output.exists()
    capsys.readouterr()
    assert github_visual.main(args + ["--apply"]) == 2
    assert not output.exists()
    capsys.readouterr()
    assert github_visual.main(args + ["--reviewed-by-operator", "--apply"]) == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["operator_visual_review_reported"] is True
    assert saved["quality_verdict"] == "NOT_EVALUATED"
    capsys.readouterr()
    assert github_visual.main(args + ["--reviewed-by-operator", "--apply"]) == 2


def test_invalid_repo_url_refused(tmp_path: Path) -> None:
    with pytest.raises(github_visual.VisualEvidenceError):
        github_visual.evidence("https://example.org/repo", _shots(tmp_path))
