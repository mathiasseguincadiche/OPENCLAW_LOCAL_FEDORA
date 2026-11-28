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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from test_daily_worker import planned as planned

from clawfedora import dashboard, project_engine, visual_capture
from clawfedora.dashboard import DashboardServer, make_server
from clawfedora.project_common import now, write_json

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


@pytest.mark.parametrize(("kind", "path", "api"), [
    ("local-dashboard", "/", "/api/status"),
    ("local-performance", "/performance.html", "/api/performance"),
    ("local-github", "/github.html", "/api/status"),
    ("local-notion", "/notion.html", None),
])
def test_read_only_capture_waits_for_dynamic_panel(
    local_server: DashboardServer, tmp_path: Path, kind: str, path: str, api: str | None,
    planned: tuple[Path, Path],
) -> None:
    _runtime, project = planned
    before = {file.relative_to(project): file.read_bytes()
              for file in project.rglob("*") if file.is_file()}
    local = tmp_path / "observation"
    local.mkdir(mode=0o700)
    # The shared Playwright fixture owns the test thread's event loop.
    with ThreadPoolExecutor(max_workers=1) as executor:
        report = executor.submit(
            visual_capture.capture,
            kind, _url(local_server, path), local, interactive=False, allow_private=False,
        ).result(timeout=60)
    assert report["observation"]["rendering"] == "LOOPBACK_READ_ONLY_PANEL"
    assert report["observation"]["panel_ready"] is True
    traces = {resource["path"]: resource for resource in report["observation"]["resources"]}
    assert traces.keys() == visual_capture._panel_scope(kind).keys()
    assert all(len(resource["sha256"]) == 64 for resource in traces.values())
    if api is not None:
        assert traces[api]["bytes"] > 0
    else:
        assert not any(name.startswith("/api/") for name in traces)
    assert [item["view"] for item in report["screenshots"]] == list(visual_capture.SIZES)
    dark = "light" if kind == "local-performance" else "dark"
    assert [item["metrics"]["applied_color_scheme"] for item in report["screenshots"]] == [
        "light", dark, "light",
    ]
    output = Path(report["output_directory"])
    assert (output / "manifest.json").stat().st_mode & 0o077 == 0
    after = {file.relative_to(project): file.read_bytes()
             for file in project.rglob("*") if file.is_file()}
    assert after == before


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



def test_operator_can_trim_a_plan_and_resolve_its_dependencies(
    browser: Any, local_server: DashboardServer, planned: tuple[Path, Path],
) -> None:
    _runtime, project = planned
    tasks = [
        {
            "id": "research", "title": "Rechercher", "role": "expert-recherche",
            "role_reason": "Recouper les sources documentaires.", "objective": "Cadrer le besoin",
            "depends_on": [], "expected_outputs": ["deliverables/research/notes.md"],
            "acceptance_criteria": ["Sources datées"],
        },
        {
            "id": "design", "title": "Concevoir", "role": "architecte-solutions",
            "role_reason": "Comparer les architectures disponibles.",
            "objective": "Proposer un choix",
            "depends_on": ["research"], "expected_outputs": ["deliverables/design/adr.md"],
            "acceptance_criteria": ["Choix justifié"],
        },
    ]
    context = browser.new_context()
    page = context.new_page()
    submissions: list[dict[str, Any]] = []

    def show_draft(route: Any) -> None:
        response = route.fetch()
        data = response.json()
        data["draft"] = {"approved": False, "kind": "plan", "role_reasons_required": True,
                         "proposal": {"workstreams": [], "tasks": tasks}}
        route.fulfill(response=response, json=data)

    def capture_approval(route: Any) -> None:
        submissions.append(route.request.post_data_json)
        route.fulfill(status=202, json={"ok": True})

    page.route(f"**/api/project?project={project.name}", show_draft)
    page.route("**/api/approve", capture_approval)
    try:
        page.goto(_url(local_server, "/"), wait_until="networkidle")
        page.locator("#selected").select_option(project.name)
        proposal = page.locator("#proposal")
        group = proposal.get_by_role("group", name="Concevoir")
        reason = group.get_by_label("Pourquoi ce rôle ?")
        pw.expect(reason).to_have_value(tasks[1]["role_reason"])
        proposal.get_by_role("group", name="Rechercher").get_by_role(
            "button", name="Retirer cette tâche",
        ).click()
        pw.expect(group.get_by_role("button", name="Retirer cette tâche")).to_be_disabled()
        pw.expect(proposal.get_by_role("status")).to_contain_text("research")
        proposal.locator('input[type="checkbox"]').check()
        submit = proposal.get_by_role("button", name="Approuver et enregistrer")
        submit.click()
        assert not submissions
        group.get_by_label("Dépendances (une par ligne)").fill("")
        pw.expect(proposal.get_by_role("status")).to_have_text("")
        group.get_by_label("Spécialité").select_option("ingenieur-devops")
        pw.expect(reason).to_have_value("")
        submit.click()
        assert not submissions
        rationale = "Décrire l'implémentation et le contrôle local du service."
        reason.fill(rationale)
        with page.expect_response("**/api/approve"):
            submit.click()
        assert len(submissions) == 1
        reduced = submissions[0]["proposal"]["tasks"]
        assert len(reduced) == 1 and reduced[0]["id"] == "design"
        assert reduced[0]["depends_on"] == [] and reduced[0]["role"] == "ingenieur-devops"
        assert reduced[0]["role_reason"] == rationale
    finally:
        context.close()


def test_audit_correction_preview_and_approval_keep_the_report_binding(
    browser: Any, local_server: DashboardServer, planned: tuple[Path, Path],
) -> None:
    _runtime, project = planned
    context = browser.new_context()
    page = context.new_page()
    digest = "a" * 64
    submissions: list[dict[str, Any]] = []

    def expose_audit(route: Any) -> None:
        response = route.fetch()
        data = response.json()
        data["manifest"]["status"] = "VALIDATING"
        data["audit_corrections"] = {
            "kind": "validation", "sha256": digest,
            "tasks": [{"task_id": "design-choice", "role": "architecte-solutions",
                       "findings": [{"number": 1, "criterion": "Justifier le choix",
                                     "evidence": "Le compromis retenu reste à expliquer."}]}],
        }
        route.fulfill(response=response, json=data)

    def capture_revision(route: Any) -> None:
        submissions.append(route.request.post_data_json)
        route.fulfill(status=200, json={"affected_tasks": ["design-choice", "research-check"]})

    page.route(f"**/api/project?project={project.name}", expose_audit)
    page.route("**/api/revise", capture_revision)
    try:
        page.goto(_url(local_server, "/"), wait_until="networkidle")
        page.locator("#selected").select_option(project.name)
        revision = page.locator("#revision")
        revision.get_by_text("Demander une modification cohérente du projet").click()
        pw.expect(revision.get_by_text("Le compromis retenu reste à expliquer.",
                                      exact=False)).to_be_visible()
        revision.get_by_role("button", name="Préparer la reprise de design-choice").click()
        pw.expect(revision.get_by_role("status")).to_contain_text("Constats joints")
        approve = revision.get_by_role("button", name="Approuver la modification")
        pw.expect(approve).to_be_disabled()
        assert not submissions
        revision.get_by_role("button", name="Voir les tâches concernées").click()
        pw.expect(revision.get_by_text("design-choice → research-check", exact=False)).to_be_visible()
        revision.get_by_role("checkbox").check()
        with page.expect_response("**/api/revise"):
            approve.click()
        assert len(submissions) == 1
        assert submissions[0]["audit_sha256"] == digest
        assert submissions[0]["task_id"] == "design-choice" and submissions[0]["human_approved"]
    finally:
        context.close()


def test_project_overview_shows_mission_and_requalifies_a_stale_audit(
    browser: Any, local_server: DashboardServer, planned: tuple[Path, Path],
) -> None:
    _runtime, project = planned
    deliverable = project / "deliverables/design-choice/report.md"
    deliverable.parent.mkdir(parents=True, exist_ok=True)
    deliverable.write_text("Première version", encoding="utf-8")
    write_json(project / "evidence/validation_report.json", {
        "generated_at": now(), "reviewer": "auditeur-qualite", "verdict": "PASS",
        "sealed_inventory": project_engine.audited_inventory(project), "proof_hashes": {},
    })
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    writes: list[str] = []
    page.on("request", lambda req: writes.append(req.url) if req.method != "GET" else None)
    try:
        page.goto(_url(local_server, "/"), wait_until="domcontentloaded")
        page.locator("#selected").select_option(project.name)
        execution = page.locator("#project-execution")
        pw.expect(execution).to_contain_text("0/2 tâches collectées")
        pw.expect(execution).to_contain_text("dépendances en attente")
        pw.expect(execution).to_contain_text("Validation réussie")
        link = execution.get_by_role("link", name="Télécharger le rapport de validation")
        pw.expect(link).to_have_attribute("download", "validation_report.json")

        deliverable.write_text("Version modifiée", encoding="utf-8")
        page.get_by_role("button", name="Actualiser le dossier").click()
        pw.expect(execution).to_contain_text("Validation à renouveler")
        pw.expect(execution).not_to_contain_text("Validation réussie")
        assert writes == []
    finally:
        context.close()


def test_visual_permissions_only_probe_the_portal_on_request(
    browser: Any, local_server: DashboardServer, monkeypatch: pytest.MonkeyPatch,
) -> None:
    probes = []
    replies = iter([
        {"status": "PROBED", "window_advertised": True, "pointer_advertised": False,
         "eis_api_in_version": True},
        {"status": "PORTAL_UNAVAILABLE"},
    ])

    def probe(session: str | None) -> dict[str, object]:
        probes.append(session)
        return next(replies)

    monkeypatch.setattr(dashboard.desktop_portal, "probe", probe)
    context = browser.new_context(viewport={"width": 390, "height": 844}, color_scheme="dark")
    page = context.new_page()
    methods: list[str] = []
    page.on("request", lambda req: methods.append(req.method))
    try:
        page.goto(_url(local_server, "/"), wait_until="domcontentloaded")
        panel = page.get_by_role("region", name="Autorisations visuelles")
        status = panel.get_by_role("status")
        pw.expect(panel).to_contain_text("approbation opérateur à usage unique")
        pw.expect(status).to_have_text("Capacités du portail à vérifier.")
        assert probes == []

        button = panel.get_by_role("button", name="Vérifier le portail Wayland")
        button.click()
        pw.expect(status).to_contain_text("Capture de fenêtre annoncée")
        pw.expect(status).to_contain_text("Pointeur absent")
        pw.expect(status).to_contain_text("qualification en attente")

        button.click()
        pw.expect(status).to_have_text("Portail Wayland indisponible.")
        assert len(probes) == 2
        assert set(methods) == {"GET"}
    finally:
        context.close()
