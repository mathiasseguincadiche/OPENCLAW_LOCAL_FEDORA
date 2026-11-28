"""Single-action browser rehearsal for an operator, using a built-in offline fixture."""

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


def _plan(directory: Path, issued_at: int) -> dict[str, Any]:
    return {
        "schema": 1,
        "scope": "SYNTHETIC_OFFLINE",
        "session": str(directory),
        "action": ACTION,
        "description": "Ouvrir les détails de la page de recette par un clic.",
        "fixture_sha256": hashlib.sha256(FIXTURE.encode()).hexdigest(),
        "issued_at_unix": issued_at,
        "expires_at_unix": issued_at + TTL_SECONDS,
        "before": {"details_open": False, "result_visible": False},
        "after": {"details_open": True, "result_visible": True},
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


def preview(output_root: Path) -> dict[str, Any]:
    """Prepare the exact action without starting Playwright."""
    directory = _private_destination(output_root, prefix="rehearsal-")
    plan = _plan(directory, int(time.time()))
    raw = _encoded(plan)
    _write_exclusive(directory / "plan.json", raw)
    return {
        "status": "PREVIEW",
        "approval_sha256": hashlib.sha256(raw).hexdigest(),
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
    issued_at = plan.get("issued_at_unix")
    if type(issued_at) is not int or raw != _encoded(_plan(directory, issued_at)):
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
                    context.route("**/*", lambda route: route.abort())
                    context.route_web_socket("**/*", lambda route: route.close())
                    page = context.new_page()
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
    plan = actions.add_parser("preview", help="préparer le clic de recette")
    plan.add_argument("--output-dir", type=Path, required=True)
    execute = actions.add_parser("apply", help="exécuter une préparation approuvée")
    execute.add_argument("--session", type=Path, required=True)
    execute.add_argument("--approve-sha256", required=True)


def run_browser_command(args: argparse.Namespace) -> int:
    try:
        if args.browser_command == "preview":
            result = preview(args.output_dir)
        else:
            result = apply(args.session, args.approve_sha256)
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "REFUSED_OR_INCOMPLETE", "reason": str(exc)},
                         ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
