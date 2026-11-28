"""Operator-approved actions on built-in offline browser fixtures."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import time
from hmac import compare_digest
from pathlib import Path
from typing import Any

from clawfedora.visual_capture import (
    CaptureError,
    _playwright_api,
    _private_destination,
    _shot,
    _validate_private_directory,
)

TTL_SECONDS = 15 * 60
MAX_PLAN_BYTES = 8192
TIMEOUT_MS = 10000
SESSION_NAME = re.compile(r"rehearsal-[a-f0-9]{32}\Z")
APPROVAL_SHA = re.compile(r"[a-f0-9]{64}\Z")
ACTION = "open-details"
NAVIGATE = "open-report"
SCENARIOS = {"details": ACTION, "navigation": NAVIGATE}
PROPOSAL_TOOL = "clawfedora_browser_proposal"
PROPOSAL_ROLES = ("ingenieur-devops", "auditeur-qualite")
NAV_HOME = "https://recette-clawfedora.invalid/"
NAV_REPORT = NAV_HOME + "rapport"
NAV_LINK = "#rehearsal-report-link"
NAV_HEADINGS = {NAV_HOME: "Accueil de la recette", NAV_REPORT: "Rapport de la recette"}
NAV_CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; form-action 'none'; "
    "base-uri 'none'; frame-ancestors 'none'"
)
FIXTURE = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Recette ClawFedora</title>
<style>
body { font: 18px system-ui, sans-serif; margin: 3rem; background: #f5f7fb; color: #152338; }
main { max-width: 46rem; margin: auto; padding: 2rem; background: white; border-radius: 1rem; }
summary { cursor: pointer; }
</style>
</head>
<body>
<main>
<h1>Recette du navigateur isolé</h1>
<p>Cette page contient uniquement des données de recette.</p>
<details id="rehearsal-details">
  <summary>Afficher les détails</summary>
  <p id="rehearsal-result">État attendu : détails affichés.</p>
</details>
</main>
</body>
</html>"""


def _navigation_fixture(heading: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<title>{heading} · ClawFedora</title>
<style>
body {{font: 18px system-ui, sans-serif; margin: 3rem; background: #f5f7fb; color: #152338}}
main {{max-width: 46rem; margin: auto; padding: 2rem; background: white; border-radius: 1rem}}
</style></head><body><main>
<h1>{heading}</h1>
{body}
</main></body></html>"""


NAV_PAGES = {
    NAV_HOME: _navigation_fixture(
        NAV_HEADINGS[NAV_HOME],
        '<p>Environnement synthétique de l’atelier.</p>'
        '<a id="rehearsal-report-link" href="/rapport">Lire le rapport</a>',
    ),
    NAV_REPORT: _navigation_fixture(
        NAV_HEADINGS[NAV_REPORT],
        '<p id="rehearsal-report-result">La destination attendue est affichée.</p>',
    ),
}


def _scenario_details(action: str) -> dict[str, Any]:
    if action == NAVIGATE:
        return {
            "description": "Ouvrir le rapport de recette par le lien autorisé.",
            "fixture_sha256": hashlib.sha256(_encoded(NAV_PAGES)).hexdigest(),
            "before": {"url": NAV_HOME, "heading": NAV_HEADINGS[NAV_HOME]},
            "after": {"url": NAV_REPORT, "heading": NAV_HEADINGS[NAV_REPORT]},
        }
    if action == ACTION:
        return {
            "description": "Ouvrir les détails de la page de recette par un clic.",
            "fixture_sha256": hashlib.sha256(FIXTURE.encode()).hexdigest(),
            "before": {"details_open": False, "result_visible": False},
            "after": {"details_open": True, "result_visible": True},
        }
    raise CaptureError("scénario de recette non autorisé")


def propose(scenario: str) -> dict[str, Any]:
    """Describe one built-in scenario without allocating a session or approving execution."""
    action = SCENARIOS.get(scenario)
    if action is None:
        raise CaptureError("scénario de recette non autorisé")
    spec = {
        "schema": 1, "scope": "SYNTHETIC_OFFLINE", "scenario": scenario, "action": action,
        **_scenario_details(action),
    }
    return {
        **spec, "status": "PROPOSED", "operator_approval_required": True,
        "proposal_sha256": hashlib.sha256(_encoded(spec)).hexdigest(),
    }


def _plan(directory: Path, issued_at: int, action: str = ACTION) -> dict[str, Any]:
    return {
        "schema": 1,
        "scope": "SYNTHETIC_OFFLINE",
        "session": str(directory),
        "action": action,
        "issued_at_unix": issued_at,
        "expires_at_unix": issued_at + TTL_SECONDS,
        **_scenario_details(action),
    }


def _encoded(data: dict[str, Any]) -> bytes:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _write_exclusive(path: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)


def _read_plan(path: Path) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as handle:
        mode = os.fstat(handle.fileno()).st_mode
        if not stat.S_ISREG(mode) or mode & 0o077:
            raise CaptureError("plan de recette privé et régulier requis")
        raw = handle.read(MAX_PLAN_BYTES + 1)
    if len(raw) > MAX_PLAN_BYTES:
        raise CaptureError("plan de recette trop volumineux")
    return raw


def preview(
    output_root: Path, *, scenario: str = "details", proposal_sha256: str | None = None,
) -> dict[str, Any]:
    """Prepare locally, optionally verifying the exact scenario proposed by a role."""
    proposal = propose(scenario)
    if proposal_sha256 is not None and (
        APPROVAL_SHA.fullmatch(proposal_sha256) is None
        or not compare_digest(proposal_sha256, proposal["proposal_sha256"])
    ):
        raise CaptureError("empreinte de proposition divergente, vérifier le scénario")
    directory = _private_destination(output_root, prefix="rehearsal-")
    plan = _plan(directory, int(time.time()), SCENARIOS[scenario])
    raw = _encoded(plan)
    _write_exclusive(directory / "plan.json", raw)
    return {
        "status": "PREVIEW",
        "approval_sha256": hashlib.sha256(raw).hexdigest(),
        **({"proposal_sha256": proposal_sha256} if proposal_sha256 is not None else {}),
        **plan,
    }


def _approved_plan(directory: Path, approval: str) -> dict[str, Any]:
    _validate_private_directory(directory)
    if SESSION_NAME.fullmatch(directory.name) is None:
        raise CaptureError("dossier de recette attendu")
    if APPROVAL_SHA.fullmatch(approval) is None:
        raise CaptureError("empreinte SHA-256 de préparation requise")
    raw = _read_plan(directory / "plan.json")
    if not compare_digest(approval, hashlib.sha256(raw).hexdigest()):
        raise CaptureError("empreinte divergente, refaire la préparation")
    plan = json.loads(raw)
    if not isinstance(plan, dict):
        raise CaptureError("plan de recette invalide")
    issued_at, action = plan.get("issued_at_unix"), plan.get("action")
    if type(issued_at) is not int or not isinstance(action, str) or action not in SCENARIOS.values():
        raise CaptureError("plan différent de l'action de recette autorisée")
    if raw != _encoded(_plan(directory, issued_at, action)):
        raise CaptureError("plan différent de l'action de recette autorisée")
    now = int(time.time())
    if not issued_at <= now < issued_at + TTL_SECONDS:
        raise CaptureError("plan périmé, refaire la préparation")
    return plan


def _state(page: Any) -> dict[str, bool]:
    if page.url != "about:blank":
        raise CaptureError("navigation imprévue pendant la recette")
    details = page.locator("#rehearsal-details")
    result = page.locator("#rehearsal-result")
    if details.count() != 1 or result.count() != 1:
        raise CaptureError("la structure de la page de recette a changé")
    return {
        "details_open": details.get_attribute("open", timeout=TIMEOUT_MS) is not None,
        "result_visible": bool(result.is_visible()),
    }


def _screenshot(page: Any, directory: Path, name: str) -> dict[str, Any]:
    path = directory / name
    picture = page.screenshot(animations="disabled", timeout=TIMEOUT_MS)
    _write_exclusive(path, picture)
    return _shot(path)


class _NavigationFence:
    """Admit each fixed document once and only in the main frame of the selected page."""

    def __init__(self, page: Any, playwright_error: type[Exception]) -> None:
        self.page = page
        self.playwright_error = playwright_error
        self.expected: str | None = NAV_HOME
        self.served: list[str] = []
        self.blocked_requests = 0

    def authorize_report(self) -> None:
        if self.expected is not None or self.served != [NAV_HOME]:
            raise CaptureError("transition de recette déjà utilisée ou inattendue")
        self.expected = NAV_REPORT

    def handle(self, route: Any) -> None:
        request = route.request
        url = request.url
        if (
            url != self.expected or request.method != "GET"
            or request.resource_type != "document" or not request.is_navigation_request()
        ):
            self.blocked_requests += 1
            route.abort()
            return
        try:
            selected_frame = request.frame == self.page.main_frame
        except self.playwright_error:
            selected_frame = False
        if not selected_frame:
            self.blocked_requests += 1
            route.abort()
            return
        self.expected = None
        self.served.append(url)
        route.fulfill(status=200, body=NAV_PAGES[url], headers={
            "Content-Type": "text/html; charset=utf-8",
            "Content-Security-Policy": NAV_CSP,
            "Referrer-Policy": "no-referrer",
        })


def _navigation_state(page: Any) -> dict[str, Any]:
    heading = page.locator("main h1")
    if heading.count() != 1 or not heading.is_visible():
        raise CaptureError("titre visible de la page de recette requis")
    return {"url": page.url, "heading": heading.inner_text(timeout=TIMEOUT_MS)}


def _report_link(page: Any) -> Any:
    link = page.locator(NAV_LINK)
    if link.count() != 1 or not link.is_visible():
        raise CaptureError("lien de recette visible et unique requis")
    if (
        link.get_attribute("href", timeout=TIMEOUT_MS) != "/rapport"
        or any(link.get_attribute(attr, timeout=TIMEOUT_MS) is not None
               for attr in ("target", "download", "ping"))
    ):
        raise CaptureError("destination du lien divergente, clic refusé")
    return link


def _exercise_navigation(
    context: Any, page: Any, directory: Path, plan: dict[str, Any],
    playwright_error: type[Exception],
) -> dict[str, Any]:
    fence = _NavigationFence(page, playwright_error)
    context.route("**/*", fence.handle)
    page.goto(NAV_HOME, wait_until="load", timeout=TIMEOUT_MS)
    before = _navigation_state(page)
    if before != plan["before"]:
        raise CaptureError("état initial divergent, navigation refusée")
    before_shot = _screenshot(page, directory, "before.png")
    link = _report_link(page)
    fence.authorize_report()
    link.click(timeout=TIMEOUT_MS)
    page.wait_for_url(NAV_REPORT, wait_until="load", timeout=TIMEOUT_MS)
    after = _navigation_state(page)
    if (
        after != plan["after"] or fence.served != [NAV_HOME, NAV_REPORT]
        or len(context.pages) != 1 or not page.locator("#rehearsal-report-result").is_visible()
    ):
        raise CaptureError("navigation ou état final divergent")
    after_shot = _screenshot(page, directory, "after.png")
    return {
        "before": before, "after": after, "screenshots": [before_shot, after_shot],
        "navigation": {"served": fence.served, "blocked_requests": fence.blocked_requests},
    }


def _exercise(directory: Path, plan: dict[str, Any]) -> dict[str, Any]:
    sync_playwright, playwright_error = _playwright_api()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context(
                    offline=True, java_script_enabled=False, service_workers="block",
                    accept_downloads=False, viewport={"width": 1000, "height": 640},
                )
                try:
                    context.route_web_socket("**/*", lambda route: route.close())
                    page = context.new_page()
                    if plan["action"] == NAVIGATE:
                        return _exercise_navigation(context, page, directory, plan, playwright_error)
                    context.route("**/*", lambda route: route.abort())
                    page.set_content(FIXTURE, wait_until="load", timeout=TIMEOUT_MS)
                    before = _state(page)
                    if before != plan["before"]:
                        raise CaptureError("état initial divergent, clic refusé")
                    before_shot = _screenshot(page, directory, "before.png")
                    page.locator("#rehearsal-details > summary").click(timeout=TIMEOUT_MS)
                    after = _state(page)
                    if after != plan["after"]:
                        raise CaptureError("état final divergent après le clic")
                    after_shot = _screenshot(page, directory, "after.png")
                finally:
                    context.close()
            finally:
                browser.close()
    except playwright_error as exc:
        raise CaptureError("recette Chromium interrompue ou indisponible") from exc
    return {"before": before, "after": after, "screenshots": [before_shot, after_shot]}


def apply(directory: Path, approval: str) -> dict[str, Any]:
    plan = _approved_plan(directory, approval)
    attempt = {
        "scope": plan["scope"], "action": plan["action"],
        "approval_sha256": approval, "fixture_sha256": plan["fixture_sha256"],
        "started_at_unix": int(time.time()),
    }
    try:
        _write_exclusive(directory / "attempt.json", _encoded(attempt))
    except FileExistsError as exc:
        raise CaptureError("approbation déjà utilisée, refaire la préparation") from exc
    try:
        observations = _exercise(directory, plan)
    except (OSError, CaptureError) as exc:
        failed = {**attempt, "status": "FAILED", "finished_at_unix": int(time.time())}
        _write_exclusive(directory / "receipt.json", _encoded(failed))
        raise CaptureError(f"recette interrompue, refaire la préparation ({exc})") from exc
    receipt = {
        **attempt, **observations, "status": "PASS", "finished_at_unix": int(time.time()),
    }
    _write_exclusive(directory / "receipt.json", _encoded(receipt))
    return {**receipt, "session": str(directory)}


def add_browser_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    browser = subparsers.add_parser("browser-rehearsal", help="recette locale d'une action isolée")
    actions = browser.add_subparsers(dest="browser_command", required=True)
    plan = actions.add_parser("preview", help="préparer une interaction de recette")
    plan.add_argument("--output-dir", type=Path, required=True)
    plan.add_argument("--scenario", choices=tuple(SCENARIOS), default="details")
    plan.add_argument("--proposal-sha256", help="vérifier l'empreinte remise par le rôle")
    execute = actions.add_parser("apply", help="exécuter une préparation approuvée")
    execute.add_argument("--session", type=Path, required=True)
    execute.add_argument("--approve-sha256", required=True)


def run_browser_command(args: argparse.Namespace) -> int:
    try:
        if args.browser_command == "preview":
            result = preview(
                args.output_dir, scenario=args.scenario, proposal_sha256=args.proposal_sha256,
            )
        else:
            result = apply(args.session, args.approve_sha256)
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "REFUSED_OR_INCOMPLETE", "reason": str(exc)},
                         ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
