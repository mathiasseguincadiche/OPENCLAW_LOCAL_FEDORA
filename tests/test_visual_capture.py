"""Refusals and integrity properties of opt-in screenshot capture; no browser started."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from clawfedora import visual_capture as visual


@pytest.mark.parametrize(
    ("kind", "url"),
    [
        ("local-notion", "http://127.0.0.1:18890/notion.html"),
        ("local-github", "http://127.0.0.1:18890/github.html"),
        ("github-readme", "https://github.com/example/infraops"),
        ("github-readme", "https://github.com/example/infraops/blob/main/README.md"),
        ("notion-page", "https://app.notion.com/p/" + "a" * 32),
        ("notion-page", "https://www.notion.so/Exercice-" + "a" * 32),
    ],
)
def test_allowed_exact_visual_targets(kind: str, url: str) -> None:
    assert visual.validate_url(kind, url) == url


@pytest.mark.parametrize(
    ("kind", "url"),
    [
        ("local-notion", "http://localhost:18890/notion.html"),
        ("local-github", "http://127.0.0.1:18890/"),
        ("local-github", "http://127.0.0.1:18890/notion.html"),
        ("local-github", "http://127.0.0.1:18890/github.html?token=secret"),
        ("local-notion", "http://127.0.0.1:18890@evil.org/notion.html"),
        ("github-readme", "https://evil.org/example/infraops"),
        ("github-readme", "https://github.com/login"),
        ("github-readme", "https://github.com/example/infraops?token=secret"),
        ("notion-page", "https://www.notion.so/login"),
        ("notion-page", "https://notion.example.org/p/" + "a" * 32),
        ("notion-page", "https://app.notion.com/p/" + "a" * 32 + "?secret=1"),
    ],
)
def test_denied_external_or_ambiguous_targets(kind: str, url: str) -> None:
    with pytest.raises(visual.CaptureError):
        visual.validate_url(kind, url)


def test_refuse_authentication_or_off_domain_redirects() -> None:
    github = "https://github.com/example/infraops"
    notion = "https://app.notion.com/p/" + "a" * 32
    with pytest.raises(visual.CaptureError):
        visual._validate_final_url("github-readme", github, "https://github.com/login")
    with pytest.raises(visual.CaptureError):
        visual._validate_final_url("notion-page", notion, "https://notion.so/login")
    with pytest.raises(visual.CaptureError):
        visual._validate_final_url(
            "notion-page", notion, "https://app.notion.com/p/" + "b" * 32,
        )
    with pytest.raises(visual.CaptureError):
        visual._validate_final_url(
            "local-notion", "http://127.0.0.1:18890/notion.html",
            "https://app.notion.com/p/" + "a" * 32,
        )


def test_screenshot_sampling_is_bounded() -> None:
    assert visual.screenshot_positions(640, 900) == [0]
    assert visual.screenshot_positions(1800, 900) == [0, 450, 900]
    assert visual.screenshot_positions(25000, 900) == [0, 4550, 9100]
    assert len(visual.screenshot_positions(100000, 900)) <= visual.MAX_SHOTS
    with pytest.raises(visual.CaptureError):
        visual.screenshot_positions(100, 0)


def test_preview_never_starts_browser(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    url = "http://127.0.0.1:18890/notion.html"
    assert visual.main([
        "--kind", "local-notion", "--url", url, "--output-dir", str(tmp_path),
    ]) == 0
    assert json.loads(capsys.readouterr().out)["assessment"] == "DRY_RUN_NO_BROWSER"
    assert list(tmp_path.iterdir()) == []


def test_private_notion_requires_operator_tty_and_explicit_consent(
    tmp_path: Path,
) -> None:
    with pytest.raises(visual.CaptureError, match="Notion privé"):
        visual.capture(
            "notion-page", "https://app.notion.com/p/" + "a" * 32,
            tmp_path, interactive=False, allow_private=False,
        )


def test_directory_refuses_public_permissions_symlinks_and_git_repo(
    tmp_path: Path,
) -> None:
    root = tmp_path / "screenshots"
    root.mkdir(mode=0o700)
    root.chmod(0o755)
    with pytest.raises(visual.CaptureError, match="chmod 700"):
        visual._private_destination(root)
    root.chmod(0o700)
    (tmp_path / ".git").mkdir()
    with pytest.raises(visual.CaptureError, match="dépôt Git"):
        visual._private_destination(root)
    (tmp_path / ".git").rmdir()
    linked = tmp_path / "screenshots-link"
    linked.symlink_to(root)
    with pytest.raises(visual.CaptureError, match="lié"):
        visual._private_destination(linked)
    assert visual._private_destination(root).is_dir()


def test_png_metadata_is_verified_not_a_visual_verdict(tmp_path: Path) -> None:
    path = tmp_path / "capture.png"
    Image.new("RGB", (390, 844), "white").save(path)
    record = visual._shot(path)
    assert record["width"] == 390
    assert record["height"] == 844
    assert len(record["sha256"]) == 64
    assert path.stat().st_mode & 0o077 == 0
    path.write_bytes(b"not a valid png")
    with pytest.raises((OSError, ValueError)):
        visual._shot(path)


def test_metrics_code_measures_overflow_without_claiming_approval() -> None:
    assert "horizontal_overflow" in visual.METRICS_JS
    assert "document_width" in visual.METRICS_JS
    assert "images_without_alt" in visual.METRICS_JS
    assert "console" not in visual.METRICS_JS
