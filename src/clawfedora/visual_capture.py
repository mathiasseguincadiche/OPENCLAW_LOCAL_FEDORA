"""Opt-in browser observation for the workshop, GitHub, Notion and official docs.

Requires optional pinned Playwright and a browser installed by the operator.
No browser is launched without --capture. No credential/cookie/session export.
Screenshots are private local files; DOM metrics are checks, not a visual verdict.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import uuid
from datetime import UTC, datetime
from http.client import HTTPException, HTTPSConnection
from importlib import import_module
from pathlib import Path
from time import monotonic
from typing import Any
from urllib.parse import urlsplit

from PIL import Image

KINDS = ("local-notion", "local-github", "github-readme", "notion-page", "official-docs")
OFFICIAL_DOCS_HOSTS = frozenset({
    "developer.hashicorp.com",
    "docs.ansible.com",
    "docs.fedoraproject.org",
    "docs.github.com",
    "docs.openclaw.ai",
    "kubernetes.io",
    "playwright.dev",
})
DOCS_PATH = re.compile(r"/[A-Za-z0-9._~/-]*\Z")
MAX_DOC_BYTES = 2_000_000
DOC_TIMEOUT = 10
DOC_CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; img-src data:; "
    "font-src data:; base-uri 'none'; form-action 'none'"
)
DOC_OBSERVATION_JS = """() => {
  const text = (value, limit) => (value || "").replace(/\\s+/g, " ").trim().slice(0, limit);
  const main = document.querySelector("main, article, [role=main]") || document.body;
  const headings = [...main.querySelectorAll("h1, h2, h3")].slice(0, 12);
  return {
    title: text(document.title, 160),
    headings: headings.map(node => ({
      level: Number(node.tagName.slice(1)), text: text(node.innerText, 120)
    })).filter(node => node.text),
    excerpt: text(main.innerText, 1600)
  };
}"""
GITHUB_PATH = re.compile(
    r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/(?:blob|tree)/[A-Za-z0-9_./-]+)?/?\Z",
)
NOTION_PAGE = re.compile(r"/(?:p/)?[A-Za-z0-9_-]*(?:[0-9a-f]{32}|[0-9a-f-]{36})/?\Z")
SIZES = {
    "desktop_light": (1440, 900, "light"),
    "desktop_dark": (1366, 900, "dark"),
    "mobile_viewport": (390, 844, "light"),
}
PREMIUM_SIZES = {
    "desktop_light": (1440, 900, "light"),
    "desktop_dark": (1440, 900, "dark"),
    "tablet_light": (820, 1180, "light"),
    "tablet_dark": (820, 1180, "dark"),
    "mobile_light": (390, 844, "light"),
    "mobile_dark": (390, 844, "dark"),
}
MAX_SHOTS = 3
MAX_PICTURE_BYTES = 15_000_000
MAX_SHOT_PIXELS = 10_000
METRICS_JS = """() => {
  const root = document.documentElement;
  const body = document.body;
  if (!root || !body) return null;
  const wide = [...body.querySelectorAll("main, section, table, pre, img, svg, input, textarea")]
    .filter(el => {
      const box = el.getBoundingClientRect();
      const css = getComputedStyle(el);
      return css.display !== "none" && css.visibility !== "hidden" &&
        box.width > 0 && (box.left < -5 || box.right > innerWidth + 5);
    })
    .slice(0, 12)
    .map(el => el.tagName.toLowerCase());
  return {
    viewport_width: innerWidth,
    viewport_height: innerHeight,
    document_width: root.scrollWidth,
    document_height: Math.max(root.scrollHeight, body.scrollHeight),
    horizontal_overflow: root.scrollWidth > innerWidth + 5,
    potential_overflow_elements: wide,
    h1_count: body.querySelectorAll("h1").length,
    tables_count: body.querySelectorAll("table").length,
    images_without_alt: [...body.querySelectorAll("img")].filter(
      img => !img.hasAttribute("alt")
    ).length,
    visible_text_length: (body.innerText || "").length,
    color_scheme_preference: matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light",
    broken_loaded_images: [...body.querySelectorAll("img")].filter(
      img => img.complete && img.naturalWidth === 0 && !!img.currentSrc
    ).length
  };
}"""


class CaptureError(ValueError):
    """Capture unavailable; no unsupported evidence or verdict claimed."""


def validate_url(kind: str, url: str) -> str:
    if kind not in KINDS or not isinstance(url, str):
        raise CaptureError("type de page non autorisé")
    parts = urlsplit(url)
    if (
        parts.username is not None or parts.password is not None
        or parts.query or parts.fragment or not parts.hostname
    ):
        raise CaptureError("URL avec identifiants, paramètres ou fragment interdite")
    if kind == "official-docs":
        if (
            parts.scheme != "https" or parts.netloc not in OFFICIAL_DOCS_HOSTS
            or DOCS_PATH.fullmatch(parts.path or "/") is None
            or any(item in (".", "..") for item in parts.path.split("/"))
            or url != parts.geturl() or any(ord(char) < 33 for char in url)
        ):
            raise CaptureError("URL HTTPS canonique d'une documentation autorisée requise")
        return url if parts.path else url + "/"
    if kind.startswith("local-"):
        desired = "/notion.html" if kind == "local-notion" else "/github.html"
        if (
            parts.scheme != "http" or parts.hostname != "127.0.0.1"
            or parts.path != desired or parts.port is None
            or not 1 <= parts.port <= 65535
        ):
            raise CaptureError("adresse loopback exacte du panneau requise")
    elif kind == "github-readme":
        if (
            parts.scheme != "https" or parts.hostname != "github.com"
            or parts.port is not None or GITHUB_PATH.fullmatch(parts.path) is None
        ):
            raise CaptureError("URL canonique GitHub de dépôt/README requise")
    elif (
        parts.scheme != "https" or parts.hostname not in (
            "www.notion.so", "notion.so", "app.notion.com",
        ) or parts.port is not None or NOTION_PAGE.fullmatch(parts.path) is None
    ):
        raise CaptureError("URL d'une page Notion identifiable requise")
    return url


def _validate_final_url(kind: str, start: str, current: str) -> None:
    """Reject login/consent screens and unexpected final browser origins."""
    final = urlsplit(current)
    expected = urlsplit(start)
    if kind == "official-docs":
        if current != start:
            raise CaptureError("navigation hors du document autorisé")
        return
    if kind.startswith("local-"):
        if current != start:
            raise CaptureError("redirection hors du panneau local refusée")
        return
    if kind == "github-readme":
        if (
            final.scheme != "https" or final.hostname != "github.com"
            or final.path.rstrip("/").casefold() != expected.path.rstrip("/").casefold()
            or final.path.startswith(("/login", "/session", "/signup"))
        ):
            raise CaptureError("page GitHub non ouverte ou accès insuffisant")
        return
    if (
        final.scheme != "https"
        or final.hostname not in ("www.notion.so", "notion.so", "app.notion.com")
        or final.path.startswith(("/login", "/signup", "/sign-in"))
        or expected.path.replace("-", "").split("/")[-1][-32:].lower() not in
        final.path.replace("-", "").lower()
    ):
        raise CaptureError("page Notion cible non ouverte après authentification")


def screenshot_positions(document_height: int, viewport_height: int) -> list[int]:
    if not 1 <= viewport_height <= 4000 or document_height < 0:
        raise CaptureError("dimensions du navigateur incorrectes")
    last = max(0, min(document_height, MAX_SHOT_PIXELS) - viewport_height)
    if last == 0:
        return [0]
    middle = last // 2
    return sorted({0, middle, last})[:MAX_SHOTS]


def _private_destination(root: Path) -> Path:
    if (not root.is_absolute() or not root.is_dir()
            or any(parent.is_symlink() for parent in (root, *root.parents))):
        raise CaptureError("dossier absolu existant, privé et non lié requis")
    if stat.S_IMODE(root.stat().st_mode) & 0o077:
        raise CaptureError("dossier privé requis (chmod 700)")
    # Captures contain private Notion content; never place them in a Git checkout.
    for parent in (root, *root.parents):
        if (parent / ".git").exists():
            raise CaptureError("capture interdite dans un dépôt Git")
    directory = root / ("capture-" + uuid.uuid4().hex)
    directory.mkdir(mode=0o700)
    return directory


def _shot(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_PICTURE_BYTES:
        raise CaptureError("capture absente, liée ou trop volumineuse")
    os.chmod(path, 0o600)
    with Image.open(path) as picture:
        if picture.format != "PNG":
            raise CaptureError("capture non PNG")
        width, height = picture.size
        if not 320 <= width <= MAX_SHOT_PIXELS or not 320 <= height <= MAX_SHOT_PIXELS:
            raise CaptureError("dimensions de capture incorrectes")
        picture.verify()
    return {
        "filename": path.name, "width": width, "height": height,
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _read_official_document(url: str) -> bytes:
    """Read a bounded UTF-8 HTML response over one direct, authenticated HTTPS request."""
    target = urlsplit(validate_url("official-docs", url))
    connection = HTTPSConnection(target.netloc, timeout=DOC_TIMEOUT)
    deadline = monotonic() + DOC_TIMEOUT
    payload = bytearray()
    try:
        connection.request("GET", target.path, headers={
            "Accept": "text/html", "Accept-Encoding": "identity",
            "User-Agent": "ClawFedora-Documentation-Observer",
        })
        with connection.getresponse() as response:
            if 300 <= response.status < 400:
                raise CaptureError("redirection refusée, fournir l'adresse finale")
            if response.status != 200 or response.headers.get_content_type() != "text/html":
                raise CaptureError("document HTML public indisponible")
            if response.getheader("Content-Encoding", "identity") != "identity":
                raise CaptureError("encodage de transport non pris en charge")
            charset = response.headers.get_content_charset() or "utf-8"
            if charset not in {"utf-8", "utf8"}:
                raise CaptureError("document HTML UTF-8 requis")
            while len(payload) <= MAX_DOC_BYTES:
                if monotonic() >= deadline:
                    raise CaptureError("délai de lecture du document dépassé")
                chunk = response.read1(min(65536, MAX_DOC_BYTES + 1 - len(payload)))
                if not chunk:
                    break
                payload.extend(chunk)
    except (OSError, HTTPException) as exc:
        raise CaptureError("lecture HTTPS de la documentation interrompue") from exc
    finally:
        connection.close()
    if not payload or len(payload) > MAX_DOC_BYTES:
        raise CaptureError("document vide ou supérieur à 2 Mo")
    try:
        payload.decode("utf-8-sig")
    except UnicodeError as exc:
        raise CaptureError("document HTML UTF-8 requis") from exc
    return bytes(payload)


def _offline_document(context: Any, url: str, document: bytes) -> None:
    """Fulfill only the first top-level GET from memory; all other requests are aborted."""
    served = False

    def handle(route: Any) -> None:
        nonlocal served
        request = route.request
        if request.url != url or request.method != "GET" or (
            served or request.resource_type != "document"
        ):
            route.abort()
            return
        served = True
        route.fulfill(status=200, body=document, headers={
            "Content-Type": "text/html; charset=utf-8",
            "Content-Security-Policy": DOC_CSP,
            "Referrer-Policy": "no-referrer",
        })

    context.route("**/*", handle)


def capture(
    kind: str, url: str, output_root: Path, *,
    interactive: bool, allow_private: bool, premium: bool = False,
) -> dict[str, Any]:
    url = validate_url(kind, url)
    if kind == "official-docs" and (interactive or allow_private):
        raise CaptureError("observation de documentation publique en session isolée")
    if kind == "notion-page" and (
        not interactive or not allow_private or not sys.stdin.isatty()
    ):
        raise CaptureError(
            "Notion privé : --interactive --allow-private et terminal requis",
        )
    if interactive and not sys.stdin.isatty():
        raise CaptureError("capture interactive exige un terminal")
    try:
        playwright_api = import_module("playwright.sync_api")
        sync_playwright = playwright_api.__dict__["sync_playwright"]
        playwright_error = playwright_api.__dict__["Error"]
    except (ImportError, KeyError) as exc:
        raise CaptureError(
            "installer l'option visuelle épinglée puis Chromium Playwright",
        ) from exc
    document = _read_official_document(url) if kind == "official-docs" else None
    output = _private_destination(output_root)
    previous_umask = os.umask(0o077)
    items: list[dict[str, Any]] = []
    observation: dict[str, Any] = {}
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=not interactive)
            context = browser.new_context(
                viewport={"width": 1440, "height": 900},
                color_scheme="light",
                device_scale_factor=1, accept_downloads=False,
                **({"offline": True, "java_script_enabled": False, "service_workers": "block"}
                   if document is not None else {}),
            )
            try:
                if document is not None:
                    _offline_document(context, url, document)
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                if interactive:
                    input(
                        "Examiner la page cible dans le navigateur temporaire ; "
                        "pour Notion, se connecter manuellement et revenir à la page. "
                        "Appuyer sur Entrée uniquement quand la page correcte est affichée : ",
                    )
                _validate_final_url(kind, url, page.url)
                if document is not None:
                    data = page.evaluate(DOC_OBSERVATION_JS)
                    if not isinstance(data, dict) or not data.get("excerpt"):
                        raise CaptureError("observation structurée non disponible")
                    observation = {
                        "document_sha256": hashlib.sha256(document).hexdigest(),
                        "document_bytes": len(document),
                        "rendering": "ISOLATED_STATIC_HTML",
                        "content_trust": "UNTRUSTED_WEB_CONTENT",
                        "dom": data,
                    }
                sizes = PREMIUM_SIZES if premium else SIZES
                for category, (width, height, scheme) in sizes.items():
                    page.set_viewport_size({"width": width, "height": height})
                    page.emulate_media(color_scheme=scheme)
                    page.wait_for_timeout(600)
                    _validate_final_url(kind, url, page.url)
                    if premium:
                        page.evaluate("() => window.scrollTo(0, 0)")
                        if interactive:
                            input(f"{category} : vérifier le thème réel du site ({scheme}), "
                                  "le régler si nécessaire puis Entrée : ")
                        _validate_final_url(kind, url, page.url)
                        page.evaluate("() => window.scrollTo(0, 0)")
                    metrics = page.evaluate(METRICS_JS)
                    if not isinstance(metrics, dict):
                        raise CaptureError("mesures DOM non disponibles")
                    if metrics.get("visible_text_length", 0) < 20:
                        raise CaptureError("page vide ou non chargée")
                    positions = screenshot_positions(
                        int(metrics["document_height"]), height,
                    )
                    pictures: list[dict[str, Any]] = []
                    for index, y in enumerate(positions):
                        page.evaluate("(position) => window.scrollTo(0, position)", y)
                        page.wait_for_timeout(200)
                        name = f"{category}-{index + 1}.png"
                        target = output / name
                        if target.exists() or target.is_symlink():
                            raise CaptureError("capture existante")
                        page.screenshot(
                            path=str(target), full_page=False, animations="disabled",
                        )
                        shot = {**_shot(target), "requested_scroll_y": y}
                        if premium:
                            shot["observed_scroll_y"] = page.evaluate("() => window.scrollY")
                        pictures.append(shot)
                    items.append({
                        "view": category, "requested_color_scheme": scheme,
                        "metrics": metrics, "sampled_screenshots": pictures,
                    })
            finally:
                context.close()
                browser.close()
        report = {
            "schema": 2 if premium else 1,
            "assessment": "BROWSER_CAPTURED_NOT_VISUALLY_CERTIFIED",
            "kind": kind, "source_url": url,
            "captured_at": datetime.now(UTC).isoformat(),
            "browser_engine": "chromium",
            "screenshots": items,
            "quality_verdict": "NOT_EVALUATED",
            "operator_review": "REQUIRED",
            **({"observation": observation} if observation else {}),
            "limitations": [
                "Les captures ne prouvent pas une lecture humaine complète",
                "Le thème demandé n'est pas forcément le thème appliqué par le site",
                "Les longues pages peuvent être partiellement échantillonnées",
                "Tests du GPU, Fedora et des données privées non certifiés par la capture",
            ],
        }
        report_path = output / "manifest.json"
        with report_path.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.chmod(report_path, 0o600)
        return {**report, "output_directory": str(output)}
    except playwright_error as exc:
        raise CaptureError("observation Chromium interrompue ou indisponible") from exc
    finally:
        os.umask(previous_umask)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="clawfedora-visual-capture")
    p.add_argument("--kind", required=True, choices=KINDS)
    p.add_argument("--url", required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--capture", action="store_true")
    p.add_argument("--interactive", action="store_true")
    p.add_argument("--allow-private", action="store_true")
    p.add_argument("--premium", action="store_true", help="six vues clair/sombre")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        url = validate_url(args.kind, args.url)
        if not args.capture:
            print(json.dumps({
                "assessment": "DRY_RUN_NO_BROWSER",
                "kind": args.kind, "url": url,
                "remote_writes": False, "local_screenshots": False,
                "views": list(PREMIUM_SIZES if args.premium else SIZES),
            }, ensure_ascii=False))
            return 0
        result = capture(
            args.kind, url, args.output_dir,
            interactive=args.interactive, allow_private=args.allow_private, premium=args.premium,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (CaptureError, OSError, ValueError, TypeError) as exc:
        print(json.dumps({
            "assessment": "CAPTURE_REFUSED_OR_INCOMPLETE",
            "reason": str(exc), "quality_verdict": "NOT_EVALUATED",
        }, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
