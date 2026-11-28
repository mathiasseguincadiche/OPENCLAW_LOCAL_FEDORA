"""Refusals and integrity properties of opt-in screenshot capture; no browser started."""

from __future__ import annotations

import hashlib
import json
import os
from email.message import Message
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image

from clawfedora import visual_capture as visual


@pytest.mark.parametrize(
    ("kind", "url"),
    [
        ("local-notion", "http://127.0.0.1:18890/notion.html"),
        ("local-github", "http://127.0.0.1:18890/github.html"),
        ("local-dashboard", "http://127.0.0.1:18890/"),
        ("local-performance", "http://127.0.0.1:18890/performance.html"),
        ("github-readme", "https://github.com/example/infraops"),
        ("github-readme", "https://github.com/example/infraops/blob/main/README.md"),
        ("notion-page", "https://app.notion.com/p/" + "a" * 32),
        ("notion-page", "https://www.notion.so/Exercice-" + "a" * 32),
        ("official-docs", "https://docs.fedoraproject.org/en-US/quick-docs/"),
    ],
)
def test_allowed_exact_visual_targets(kind: str, url: str) -> None:
    assert visual.validate_url(kind, url) == url


@pytest.mark.parametrize(
    ("kind", "url"),
    [
        ("local-notion", "http://localhost:18890/notion.html"),
        ("local-github", "http://127.0.0.1:18890/"),
        ("local-dashboard", "http://127.0.0.1:0/"),
        ("local-dashboard", "http://127.0.0.1:18890/api/status"),
        ("local-performance", "http://127.0.0.1:18890/performance.html?project=atlas"),
        ("local-performance", "http://127.0.0.2:18890/performance.html"),
        ("local-github", "http://127.0.0.1:18890/notion.html"),
        ("local-github", "http://127.0.0.1:18890/github.html?token=secret"),
        ("local-notion", "http://127.0.0.1:18890@evil.org/notion.html"),
        ("github-readme", "https://evil.org/example/infraops"),
        ("github-readme", "https://github.com/login"),
        ("github-readme", "https://github.com/example/infraops?token=secret"),
        ("notion-page", "https://www.notion.so/login"),
        ("notion-page", "https://notion.example.org/p/" + "a" * 32),
        ("notion-page", "https://app.notion.com/p/" + "a" * 32 + "?secret=1"),
        ("official-docs", "http://docs.fedoraproject.org/en-US/quick-docs/"),
        ("official-docs", "https://127.0.0.1/reference"),
        ("official-docs", "https://docs.fedoraproject.org.example.net/reference"),
        ("official-docs", "https://docs.fedoraproject.org:8443/reference"),
        ("official-docs", "https://user@docs.fedoraproject.org/reference"),
        ("official-docs", "https://docs.fedoraproject.org/reference?value=1"),
        ("official-docs", "https://docs.fedoraproject.org/reference#section"),
        ("official-docs", "https://docs.fedoraproject.org/reference/../other"),
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


@pytest.mark.parametrize(("kind", "url"), [
    ("local-notion", "http://127.0.0.1:18890/notion.html"),
    ("official-docs", "https://docs.fedoraproject.org/en-US/quick-docs/"),
])
def test_preview_never_starts_browser(
    kind: str, url: str, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_fetch(_url: str) -> bytes:
        pytest.fail("Une prévisualisation ne doit faire aucun appel HTTPS")

    monkeypatch.setattr(visual, "_read_official_document", no_fetch)
    assert visual.main([
        "--kind", kind, "--url", url, "--output-dir", str(tmp_path),
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


DOC_URL = "https://docs.fedoraproject.org/en-US/quick-docs/"
DOC_HTML = b"""<!doctype html>
<html lang="en"><head><title>Atlas documentation</title>
<style>main { max-width: 50rem; margin: auto; }</style>
<script>document.title = 'Unexpected executed script';</script>
</head><body><main>
<h1>Restore a local backup</h1><h2>Check the archive</h2>
<p>Read the protocol before restoring. This document is a test fixture.</p>
<img src="https://outside.example/diagram.png" alt="External diagram">
<iframe src="http://127.0.0.1:3333/private"></iframe>
</main></body></html>"""


@pytest.mark.parametrize(("status", "media", "body", "error"), [
    (200, "text/html; charset=UTF-8", b"<html>Atlas</html>", ""),
    (302, "text/html; charset=UTF-8", b"", "redirection"),
    (200, "application/zip", b"test", "HTML public"),
    (200, "text/html; charset=UTF-8", b"x" * 200, "supérieur"),
    (200, "text/html; charset=UTF-8", b"\xff", "UTF-8"),
])
def test_official_document_uses_one_bounded_https_request(
    status: int, media: str, body: bytes, error: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []

    class Response(BytesIO):
        def __init__(self) -> None:
            super().__init__(body)
            self.status = status
            self.headers = Message()
            self.headers["Content-Type"] = media
            self.headers["Location"] = "http://127.0.0.1:3333/private"

        def getheader(self, header: str, default: str) -> str:
            return str(self.headers.get(header, default))

    class Connection:
        def __init__(self, host: str, *, timeout: int) -> None:
            assert host == "docs.fedoraproject.org" and timeout == visual.DOC_TIMEOUT

        def request(self, method: str, path: str, *, headers: dict[str, str]) -> None:
            calls.append((method, path))
            assert "Authorization" not in headers and "Cookie" not in headers

        def getresponse(self) -> Response:
            return Response()

        def close(self) -> None:
            calls.append(("close", ""))

    monkeypatch.setattr(visual, "HTTPSConnection", Connection)
    monkeypatch.setattr(visual, "MAX_DOC_BYTES", 100)
    if error:
        with pytest.raises(visual.CaptureError, match=error):
            visual._read_official_document(DOC_URL)
    else:
        assert visual._read_official_document(DOC_URL) == body
    assert calls == [("GET", "/en-US/quick-docs/"), ("close", "")]


def test_offline_document_route_serves_exactly_one_document() -> None:
    handlers = []
    events = []
    context = SimpleNamespace(route=lambda pattern, handler: handlers.append((pattern, handler)))
    visual._offline_document(context, DOC_URL, DOC_HTML)
    (pattern, handle), = handlers
    assert pattern == "**/*"
    for url, method, resource in (
        ("https://outside.example/control", "GET", "document"),
        (DOC_URL, "POST", "document"),
        (DOC_URL, "GET", "script"),
        (DOC_URL, "GET", "document"),
        (DOC_URL, "GET", "document"),
    ):
        handle(SimpleNamespace(
            request=SimpleNamespace(url=url, method=method, resource_type=resource),
            abort=lambda: events.append("blocked"),
            fulfill=lambda **response: events.append(response),
        ))
    assert events[:3] == ["blocked"] * 3 and events[-1] == "blocked"
    assert events[3]["body"] == DOC_HTML
    assert events[3]["headers"]["Content-Security-Policy"] == visual.DOC_CSP


def test_official_document_real_chromium_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.getenv("CLAWFEDORA_REQUIRE_OFFICIAL_DOCS_BROWSER") != "1":
        pytest.skip("Exécuté dans le job Chromium de la CI")
    calls: list[str] = []

    def fixture(url: str) -> bytes:
        calls.append(url)
        return DOC_HTML

    monkeypatch.setattr(visual, "_read_official_document", fixture)
    tmp_path.chmod(0o700)
    report: dict[str, Any] = visual.capture(
        "official-docs", DOC_URL, tmp_path, interactive=False, allow_private=False,
    )
    assert calls == [DOC_URL]
    observation = report["observation"]
    assert observation["document_sha256"] == hashlib.sha256(DOC_HTML).hexdigest()
    assert observation["content_trust"] == "UNTRUSTED_WEB_CONTENT"
    assert observation["dom"]["title"] == "Atlas documentation"
    assert observation["dom"]["headings"] == [
        {"level": 1, "text": "Restore a local backup"},
        {"level": 2, "text": "Check the archive"},
    ]
    assert report["quality_verdict"] == "NOT_EVALUATED"
    destination = Path(report["output_directory"])
    assert (destination / "manifest.json").stat().st_mode & 0o077 == 0
    assert [view["metrics"]["viewport_width"] for view in report["screenshots"]] == [
        1440, 1366, 390,
    ]
    assert [view["metrics"]["color_scheme_preference"] for view in report["screenshots"]] == [
        "light", "dark", "light",
    ]
    for view in report["screenshots"]:
        for picture in view["sampled_screenshots"]:
            photo = destination / picture["filename"]
            assert photo.stat().st_mode & 0o077 == 0
            assert hashlib.sha256(photo.read_bytes()).hexdigest() == picture["sha256"]


def test_panel_scope_blocks_unlisted_requests_and_freezes_local_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    origin = "http://127.0.0.1:18890"
    routes: dict[str, Any] = {}
    calls: list[tuple[int, str, str]] = []

    def fake_asset(port: int, path: str, media: str, _deadline: float) -> bytes:
        calls.append((port, path, media))
        return path.encode()

    monkeypatch.setattr(visual, "_read_panel_asset", fake_asset)
    context = SimpleNamespace(
        route=lambda _pattern, handler: routes.update(http=handler),
        route_web_socket=lambda _pattern, handler: routes.update(socket=handler),
    )
    captured = visual._offline_panel(context, "local-performance", origin + "/performance.html")
    results: list[str] = []

    def request(url: str, method: str, resource: str) -> None:
        routes["http"](SimpleNamespace(
            request=SimpleNamespace(url=url, method=method, resource_type=resource),
            abort=lambda: results.append("blocked"),
            fulfill=lambda **response: results.append(response["body"].decode()),
        ))

    request(origin + "/performance.html", "GET", "document")
    request(origin + "/api/performance", "GET", "fetch")
    request(origin + "/api/performance", "GET", "fetch")
    request(origin + "/api/performance", "POST", "fetch")
    request(origin + "/api/status", "GET", "fetch")
    request(origin + "/api/performance?project=atlas", "GET", "fetch")
    request("http://127.0.0.1:19890/api/performance", "GET", "fetch")
    request("https://outside.example/performance.js", "GET", "script")
    request(origin + "/discussions.js", "GET", "script")
    request(origin + "/performance.html", "GET", "fetch")
    routes["socket"](SimpleNamespace(close=lambda: results.append("blocked")))
    assert results == ["/performance.html", "/api/performance", "/api/performance"] + ["blocked"] * 8
    assert calls == [(18890, "/performance.html", "text/html"),
                     (18890, "/api/performance", "application/json")]
    assert captured == {"/performance.html": b"/performance.html",
                        "/api/performance": b"/api/performance"}


@pytest.mark.parametrize(("status", "attachment", "error"), [
    (302, False, "réponse inattendue"),
    (200, True, "téléchargement refusé"),
])
def test_panel_transport_refuses_redirects_and_attachments(
    monkeypatch: pytest.MonkeyPatch, status: int, attachment: bool, error: str,
) -> None:
    class Response(BytesIO):
        def __init__(self) -> None:
            super().__init__(b"{}")
            self.status = status
            self.headers = Message()
            self.headers["Content-Type"] = "application/json"
            self.headers["Location"] = "http://127.0.0.1:18891/other"
            if attachment:
                self.headers["Content-Disposition"] = "attachment; filename=Other.json"

        def getheader(self, name: str, default: str | None = None) -> str | None:
            return self.headers.get(name, default)

    calls: list[tuple[str, str]] = []

    class Connection:
        def __init__(self, host: str, port: int, *, timeout: float) -> None:
            assert host == "127.0.0.1" and port == 18890 and timeout > 0

        def request(self, method: str, path: str, *, headers: dict[str, str]) -> None:
            calls.append((method, path))
            assert "Cookie" not in headers and "Authorization" not in headers

        def getresponse(self) -> Response:
            return Response()

        def close(self) -> None:
            calls.append(("close", ""))

    monkeypatch.setattr(visual, "HTTPConnection", Connection)
    with pytest.raises(visual.CaptureError, match=error):
        visual._read_panel_asset(18890, "/api/performance", "application/json",
                                 visual.monotonic() + 10)
    assert calls == [("GET", "/api/performance"), ("close", "")]
