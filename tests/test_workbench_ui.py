"""Presentation contracts for the modern local workbench.

No browser, Notion write or GitHub write is needed for these checks.
Visual acceptance on real Fedora is tracked separately.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import threading
from collections.abc import Iterator
from html.parser import HTMLParser
from http.client import HTTPConnection
from pathlib import Path

import pytest
from test_daily_worker import planned as planned

from clawfedora import dashboard
from clawfedora.dashboard import DashboardServer, make_server

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "src/clawfedora/web"
PAGES = ("dashboard.html", "github.html", "notion.html")


class DocumentStructure(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.links: list[str] = []
        self.scripts: list[str] = []
        self.forms: list[str] = []
        self.labels: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = dict(attrs)
        identifier = data.get("id")
        if identifier:
            self.ids.append(identifier)
        if tag == "link" and data.get("rel") == "stylesheet":
            self.links.append(data.get("href") or "")
        if tag == "script" and data.get("src"):
            self.scripts.append(data["src"] or "")
        if tag == "form" and identifier:
            self.forms.append(identifier)
        if tag == "label" and data.get("for"):
            self.labels.append(data["for"] or "")


@pytest.fixture
def server(planned: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch) -> Iterator[DashboardServer]:
    runtime, _ = planned
    monkeypatch.setattr(dashboard, "urlopen", lambda *_a, **_kw: io.BytesIO(b'{"models":[]}'))
    with make_server(ROOT, runtime, 0) as instance:
        thread = threading.Thread(target=instance.serve_forever, daemon=True)
        thread.start()
        try:
            yield instance
        finally:
            instance.shutdown()
            thread.join(timeout=5)


def _get(instance: DashboardServer, path: str) -> tuple[int, str]:
    conn = HTTPConnection("127.0.0.1", instance.server_port, timeout=6)
    conn.request("GET", path, headers={"Host": f"127.0.0.1:{instance.server_port}"})
    response = conn.getresponse()
    status, body = response.status, response.read().decode("utf-8")
    conn.close()
    return status, body


def test_all_pages_share_local_design_system_and_preserve_forms() -> None:
    essential = {
        "dashboard.html": {"create-form", "search-form", "note-form"},
        "github.html": {"repo-plan-form", "repo-apply-form", "policy-plan-form",
                        "policy-apply-form", "draft-plan-form", "draft-apply-form"},
        "notion.html": {"inspect-form", "plan-form", "apply-form", "rich-plan-form",
                        "rich-apply-form", "media-plan-form", "media-apply-form"},
    }
    for page in PAGES:
        dom = DocumentStructure()
        dom.feed((WEB / page).read_text(encoding="utf-8"))
        assert "/workbench.css" in dom.links
        assert "/workbench.js" in dom.scripts
        assert len(dom.ids) == len(set(dom.ids)), page
        assert essential[page] <= set(dom.forms)
        assert set(dom.labels) <= set(dom.ids), page
        assert all(item.startswith("/") for item in dom.links + dom.scripts)


def test_assets_are_served_same_origin_without_side_effects(
    server: DashboardServer, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        dashboard.github_remote, "create_repository",
        lambda **_kw: pytest.fail("static GET created a repository"),
    )
    monkeypatch.setattr(
        dashboard.notion_panel, "inspect",
        lambda *_args: pytest.fail("static GET read Notion"),
    )
    for path in (
        "/", "/github.html", "/notion.html", "/workbench.css", "/workbench.js",
    ):
        code, payload = _get(server, path)
        assert code == 200 and payload
    assert _get(server, "/api/workbench/apply")[0] == 404


def test_tabs_are_accessible_keyboard_operated_and_non_submitting() -> None:
    script = (WEB / "workbench.js").read_text(encoding="utf-8")
    for contract in (
        'setAttribute("role", "tablist")', 'setAttribute("role", "tab")',
        'setAttribute("aria-selected"', 'setAttribute("aria-controls"',
        '"ArrowRight"', '"ArrowLeft"', '"Home"', '"End"',
        'tab.type = "button"', "history.replaceState",
        "MutationObserver(update)",
    ):
        assert contract in script
    assert 'fetch(' not in script
    assert "XMLHttpRequest" not in script
    assert "localStorage.setItem" in script  # Only the visual theme preference.


def test_theme_responsive_accessibility_and_privacy() -> None:
    theme = (WEB / "workbench.css").read_text(encoding="utf-8")
    for contract in (
        'html[data-theme="dark"]', 'max-width: 780px',
        'max-width: 490px', 'prefers-reduced-motion: reduce',
        'focus-visible', '.workspace-tabs', '.workspace-rail',
        '.workbench-form-grid', 'body.workbench [hidden]',
    ):
        assert contract in theme
    assert "@import" not in theme
    assert "url(http" not in theme
    script = (WEB / "workbench.js").read_text(encoding="utf-8")
    assert "document.createElementNS" in script  # Local icon artwork.
    assert "innerHTML" not in script
    assert "eval(" not in script
    assert 'document.body.classList.add("workbench", "workbench--" + view)' in script


def test_mobile_a11y_labels_skip_and_step_controls_are_present() -> None:
    script = (WEB / "workbench.js").read_text(encoding="utf-8")
    styles = (WEB / "workbench.css").read_text(encoding="utf-8")
    for expression in (
        'link.setAttribute("aria-label", item.label)',
        'skip.textContent = "Aller au contenu principal"',
        'main.tabIndex = -1',
        'stepNavigation.setAttribute("role", "group")',
        'stepCount.setAttribute("aria-live", "polite")',
        'stepCount.textContent = "Étape "',
        'previous.type = "button"',
        'next.type = "button"',
    ):
        assert expression in script
    assert ".workspace-step-navigation" in styles
    assert ".workspace-skip:focus" in styles


def test_shared_frontend_javascript_syntax_when_node_is_available() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node absent : lint Python et contrat HTML restent exécutés")
    result = subprocess.run(
        [node, "--check", str(WEB / "workbench.js")],
        capture_output=True, text=True, check=False, timeout=10,
    )
    assert result.returncode == 0, result.stderr
