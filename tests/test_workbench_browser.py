"""Chromium smoke tests of the *actual* local dashboard, with synthetic data.

Runs only in the dedicated browser CI job. No real Notion/GitHub credentials,
no outbound API writes, and no claims of Fedora/native visual certification.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from test_daily_worker import planned as planned

from clawfedora import dashboard
from clawfedora.dashboard import DashboardServer, make_server

pw = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parents[1]
PAGE_ID = "a" * 32
BLOCK_ID = "b" * 32


@pytest.fixture(scope="module")
def browser() -> Iterator[Any]:
    with pw.sync_playwright() as engine:
        instance = engine.chromium.launch(headless=True)
        try:
            yield instance
        finally:
            instance.close()


@pytest.fixture
def local_server(
    planned: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch,
) -> Iterator[DashboardServer]:
    runtime, _project = planned
    monkeypatch.setattr(
        dashboard, "urlopen",
        lambda *_args, **_kwargs: io.BytesIO(b'{"models":[]}'),
    )
    with make_server(ROOT, runtime, 0) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            thread.join(timeout=5)


def _url(server: DashboardServer, route: str) -> str:
    return f"http://127.0.0.1:{server.server_port}{route}"


def _screen(page: Any, name: str, tmp_path: Path) -> None:
    """Write only synthetic local browser views, never real account content."""
    directory = Path(os.environ.get("WORKBENCH_BROWSER_EVIDENCE", str(tmp_path)))
    directory.mkdir(parents=True, exist_ok=True)
    image = directory / (name + ".png")
    page.screenshot(path=str(image), full_page=False, animations="disabled")
    assert image.is_file() and 500 < image.stat().st_size < 10_000_000
    digest = hashlib.sha256(image.read_bytes()).hexdigest()
    print(f"SYNTHETIC_BROWSER_SCREENSHOT={image.name} SHA256={digest}")


@pytest.mark.parametrize(
    ("route", "label"), [
        ("/", "projects"),
        ("/discussions.html", "discussions"),
        ("/github.html", "github"),
        ("/notion.html", "notion"),
    ],
)
@pytest.mark.parametrize(
    ("width", "height", "scheme"), [
        (1440, 900, "light"),
        (1366, 900, "dark"),
        (390, 844, "light"),
    ],
)
def test_real_chromium_renders_workspaces_without_document_overflow(
    browser: Any, local_server: DashboardServer, tmp_path: Path,
    route: str, label: str, width: int, height: int, scheme: str,
) -> None:
    context = browser.new_context(
        viewport={"width": width, "height": height}, color_scheme=scheme,
        reduced_motion="reduce",
    )
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(_url(local_server, route), wait_until="networkidle")
        pw.expect(page.locator("body")).to_have_class(
            "workbench workbench--" + label,
        )
        pw.expect(page.locator(".workspace-rail-link")).to_have_count(4)
        pw.expect(page.locator("header.workspace-hero h1")).to_be_visible()
        pw.expect(page.locator(".workspace-topbar")).to_be_visible()
        layout: dict[str, Any] = page.evaluate(
            """() => ({
                document: document.documentElement.scrollWidth,
                viewport: innerWidth,
                missingMain: !document.querySelector("main"),
                invisibleHero: !document.querySelector(".workspace-hero"),
            })""",
        )
        assert not layout["missingMain"] and not layout["invisibleHero"]
        assert layout["document"] <= layout["viewport"] + 5, layout
        assert errors == [], errors
        _screen(page, f"{label}-{width}-{scheme}", tmp_path)
    finally:
        context.close()


@pytest.mark.parametrize(
    ("route", "initial", "other", "other_panel"), [
        ("/github.html", "create", "governance", "governance"),
        ("/notion.html", "inspect", "media", "media"),
    ],
)
def test_tabs_click_keyboard_and_hash_are_functional(
    browser: Any, local_server: DashboardServer,
    route: str, initial: str, other: str, other_panel: str,
) -> None:
    context = browser.new_context(viewport={"width": 1080, "height": 820})
    page = context.new_page()
    writes: list[str] = []
    page.on(
        "request",
        lambda request: writes.append(request.url)
        if request.method == "POST" else None,
    )
    try:
        page.goto(_url(local_server, route), wait_until="networkidle")
        selected = page.locator(f"#workspace-tab-{initial}")
        pw.expect(selected).to_have_attribute("aria-selected", "true")
        pw.expect(page.locator(f"#{other_panel}")).to_be_hidden()
        page.locator(f"#workspace-tab-{other}").click()
        pw.expect(page.locator(f"#{other_panel}")).to_be_visible()
        pw.expect(page.locator(f"#workspace-tab-{other}")).to_have_attribute(
            "aria-selected", "true",
        )
        assert page.url.endswith("#" + other)
        page.keyboard.press("Home")
        pw.expect(selected).to_have_attribute("aria-selected", "true")
        page.keyboard.press("End")
        pw.expect(page.locator("[role=tab]:last-child")).to_have_attribute(
            "aria-selected", "true",
        )
        assert writes == [], writes
    finally:
        context.close()


def test_theme_toggle_survives_reload_without_remote_write(
    browser: Any, local_server: DashboardServer,
) -> None:
    context = browser.new_context(
        viewport={"width": 1280, "height": 900}, color_scheme="light",
    )
    page = context.new_page()
    writes: list[str] = []
    page.on(
        "request",
        lambda request: writes.append(request.url)
        if request.method == "POST" else None,
    )
    try:
        page.goto(_url(local_server, "/github.html"), wait_until="networkidle")
        pw.expect(page.locator("html")).to_have_attribute("data-theme", "light")
        before = page.locator("body").evaluate(
            "(element) => getComputedStyle(element).backgroundColor",
        )
        page.locator(".theme-toggle").click()
        pw.expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        after = page.locator("body").evaluate(
            "(element) => getComputedStyle(element).backgroundColor",
        )
        assert before != after, "Thème sombre sans changement visuel"
        page.reload(wait_until="networkidle")
        pw.expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        assert writes == []
    finally:
        context.close()


def test_github_preview_keeps_sensitive_submit_separate(
    browser: Any, local_server: DashboardServer,
) -> None:
    context = browser.new_context()
    page = context.new_page()
    requests: list[str] = []
    page.on(
        "request",
        lambda request: requests.append(request.url)
        if request.method == "POST" else None,
    )
    try:
        page.goto(_url(local_server, "/github.html"), wait_until="networkidle")
        pw.expect(page.locator("#repo-apply-form")).to_be_hidden()
        page.locator("#repo-name").fill("ProjetTestVisual")
        page.locator("#repo-plan-form button[type=submit]").click()
        pw.expect(page.locator("#repo-apply-form")).to_be_visible()
        assert any("/api/github/create-plan" in url for url in requests)
        assert not any("/api/github/create-apply" in url for url in requests)
        assert not any("/api/github/draft-apply" in url for url in requests)
        page.locator("#repo-name").fill("AutreProjetTest")
        pw.expect(page.locator("#repo-apply-form")).to_be_hidden()
    finally:
        context.close()


def test_notion_review_indicator_does_not_approve_anything(
    browser: Any, local_server: DashboardServer,
) -> None:
    context = browser.new_context()
    page = context.new_page()
    requests: list[str] = []
    page.on(
        "request",
        lambda request: requests.append(request.url)
        if request.method == "POST" else None,
    )
    inventory = {
        "page_id": PAGE_ID, "editable_count": 1, "protected_count": 0,
        "inventory_sha256": "d" * 64,
        "blocks": [{
            "block_id": BLOCK_ID, "type": "paragraph",
            "eligible": True, "rich_candidate": True,
            "media_candidate": False, "excerpt": "Document de test",
        }],
    }
    proposal = {
        "plan_id": "e" * 32, "page_id": PAGE_ID,
        "manifest_sha256": "f" * 64,
        "edits": [{"block_id": BLOCK_ID, "diff": "-Document de test\n+Texte validé"}],
    }
    page.route(
        "**/api/notion/inspect",
        lambda route: route.fulfill(
            status=200, content_type="application/json",
            body=json.dumps(inventory),
        ),
    )
    page.route(
        "**/api/notion/plan",
        lambda route: route.fulfill(
            status=200, content_type="application/json",
            body=json.dumps(proposal),
        ),
    )
    try:
        page.goto(_url(local_server, "/notion.html"), wait_until="networkidle")
        pw.expect(page.locator("#apply-form")).to_be_hidden()
        page.locator("#notion-page").fill(PAGE_ID)
        page.locator("#inspect-form button[type=submit]").click()
        pw.expect(page.locator("#block-totals")).to_contain_text(
            "1 blocs textuels candidats",
        )
        page.locator("#workspace-tab-changes").click()
        page.locator("#editors textarea").fill("Texte validé")
        page.locator("#plan-form button[type=submit]").click()
        pw.expect(page.locator("#workspace-tab-approve")).to_have_class(
            "workspace-tab is-ready",
        )
        page.locator("#workspace-tab-approve").click()
        pw.expect(page.locator("#apply-form")).to_be_visible()
        assert "/api/notion/inspect" in " ".join(requests)
        assert "/api/notion/plan" in " ".join(requests)
        assert not any("/api/notion/apply" in url for url in requests)
    finally:
        context.close()


@pytest.mark.parametrize(
    ("route", "count", "first", "second", "last"), [
        ("/github.html", 4, "create", "governance", "visual"),
        ("/notion.html", 6, "inspect", "changes", "verify"),
    ],
)
def test_mobile_stepper_exposes_hidden_tabs_without_writes(
    browser: Any, local_server: DashboardServer, tmp_path: Path,
    route: str, count: int, first: str, second: str, last: str,
) -> None:
    context = browser.new_context(
        viewport={"width": 390, "height": 844}, reduced_motion="reduce",
    )
    page = context.new_page()
    writes: list[str] = []
    page.on(
        "request",
        lambda request: writes.append(request.url)
        if request.method == "POST" else None,
    )
    try:
        page.goto(_url(local_server, route), wait_until="networkidle")
        navigation = page.get_by_role("group", name="Changer d’étape")
        pw.expect(navigation).to_be_visible()
        pw.expect(page.locator(".workspace-step-count")).to_have_text(
            f"Étape 1 sur {count}",
        )
        previous = navigation.get_by_role("button", name="Précédent")
        following = navigation.get_by_role("button", name="Suivant")
        pw.expect(previous).to_be_disabled()
        following.click()
        pw.expect(page.locator(f"#workspace-tab-{second}")).to_have_attribute(
            "aria-selected", "true",
        )
        pw.expect(previous).to_be_enabled()
        pw.expect(page.locator(".workspace-step-count")).to_have_text(
            f"Étape 2 sur {count}",
        )
        page.locator(".workspace-tabs").evaluate(
            "(el) => el.scrollLeft = el.scrollWidth",
        )
        page.locator(f"#workspace-tab-{last}").click()
        pw.expect(following).to_be_disabled()
        pw.expect(page.locator(".workspace-step-count")).to_have_text(
            f"Étape {count} sur {count}",
        )
        assert page.url.endswith("#" + last)
        _screen(page, "mobile-" + route.replace("/", "").replace(".html", "") +
                "-last-step", tmp_path)
        assert writes == [], writes
    finally:
        context.close()


@pytest.mark.parametrize("route", ["/", "/github.html", "/notion.html"])
def test_mobile_icon_navigation_retains_accessible_names_and_skip_link(
    browser: Any, local_server: DashboardServer, route: str,
) -> None:
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    try:
        page.goto(_url(local_server, route), wait_until="networkidle")
        for name in ("Tableau de bord", "Dépôts & CI", "Documentation"):
            link = page.get_by_role("link", name=name, exact=True)
            pw.expect(link).to_be_visible()
            assert link.get_attribute("aria-label") == name
        skip = page.get_by_role("link", name="Aller au contenu principal")
        pw.expect(skip).to_have_attribute("href", "#main-content")
        page.keyboard.press("Tab")
        pw.expect(skip).to_be_focused()
        page.keyboard.press("Enter")
        pw.expect(page.locator("#main-content")).to_be_focused()
    finally:
        context.close()


def test_discussion_role_guidance_does_not_send_or_create(
    browser: Any, local_server: DashboardServer,
) -> None:
    context = browser.new_context(viewport={"width": 1100, "height": 820})
    page = context.new_page()
    writes: list[str] = []
    page.on(
        "request",
        lambda request: writes.append(request.url) if request.method == "POST" else None,
    )
    try:
        page.goto(_url(local_server, "/discussions.html"), wait_until="networkidle")
        role = page.locator("#new-agent")
        pw.expect(role).to_have_value("chef-operations")
        pw.expect(page.locator("#agent-help")).to_contain_text("Qwen")
        role.select_option("ingenieur-devops")
        pw.expect(page.locator("#agent-help")).to_contain_text("Ornith")
        role.select_option("expert-recherche")
        pw.expect(page.locator("#agent-help")).to_contain_text("Gemma")
        pw.expect(page.locator("#new-project")).to_have_value("")
        assert writes == [], writes
    finally:
        context.close()
