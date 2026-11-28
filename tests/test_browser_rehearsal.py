"""The operator can approve only one exact, private browser rehearsal."""

from __future__ import annotations

import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from clawfedora import browser_rehearsal as rehearsal
from clawfedora.cli import main


def _no_browser(*_args: Any) -> Any:
    pytest.fail("Chromium ne doit pas démarrer")


@pytest.fixture
def output(tmp_path: Path) -> Path:
    directory = tmp_path / "proofs"
    directory.mkdir(mode=0o700)
    return directory


def test_preview_cli_records_private_plan_without_opening_browser(
    output: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(rehearsal, "_playwright_api", _no_browser)
    assert main(["browser-rehearsal", "preview", "--output-dir", str(output)]) == 0
    plan = json.loads(capsys.readouterr().out)
    directory = Path(plan["session"])
    raw = (directory / "plan.json").read_bytes()
    assert directory.parent == output
    assert plan["status"] == "PREVIEW"
    assert plan["approval_sha256"] == hashlib.sha256(raw).hexdigest()
    assert plan["expires_at_unix"] - plan["issued_at_unix"] == 900
    assert json.loads(raw)["action"] == "open-details"
    assert {path.name for path in directory.iterdir()} == {"plan.json"}
    assert directory.stat().st_mode & 0o777 == 0o700
    assert (directory / "plan.json").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("variant", ["incorrect", "modified", "expired", "moved", "link"])
def test_apply_refuses_an_unapproved_or_stale_plan(
    variant: str, output: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rehearsal, "_playwright_api", _no_browser)
    monkeypatch.setattr(rehearsal.time, "time", lambda: 10000.0)
    preview = rehearsal.preview(output)
    directory = Path(preview["session"])
    approval = preview["approval_sha256"]
    path = directory / "plan.json"
    if variant == "incorrect":
        approval = "a" * 64
    elif variant == "modified":
        raw = path.read_bytes().replace(b"open-details", b"change-site")
        path.write_bytes(raw)
        approval = hashlib.sha256(raw).hexdigest()
    elif variant == "expired":
        monkeypatch.setattr(rehearsal.time, "time", lambda: 10900.0)
    elif variant == "moved":
        parent = output / "moved"
        parent.mkdir(mode=0o700)
        directory = directory.rename(parent / directory.name)
    else:
        current = path.rename(directory / "reference.json")
        path.symlink_to(current)

    with pytest.raises((OSError, rehearsal.CaptureError)):
        rehearsal.apply(directory, approval)
    assert not (directory / "attempt.json").exists()


def test_approval_is_used_only_once_even_with_concurrent_calls(
    output: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = rehearsal.preview(output)
    directory = Path(plan["session"])
    calls: list[Path] = []

    def fake_browser(session: Path, approved: dict[str, Any]) -> dict[str, Any]:
        assert (session / "attempt.json").is_file()
        calls.append(session)
        return {"before": approved["before"], "after": approved["after"], "screenshots": []}

    monkeypatch.setattr(rehearsal, "_exercise", fake_browser)

    def run() -> str:
        try:
            return str(rehearsal.apply(directory, plan["approval_sha256"])["status"])
        except rehearsal.CaptureError as exc:
            assert "déjà utilisée" in str(exc)
            return "SPENT"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: run(), range(2)))
    assert sorted(results) == ["PASS", "SPENT"]
    assert calls == [directory]
    receipt = directory / "receipt.json"
    assert json.loads(receipt.read_bytes())["approval_sha256"] == plan["approval_sha256"]
    assert receipt.stat().st_mode & 0o777 == 0o600


def test_interrupted_attempt_cannot_reuse_approval(
    output: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = rehearsal.preview(output)
    directory = Path(plan["session"])

    def interrupted(_session: Path, _plan: dict[str, Any]) -> dict[str, Any]:
        raise rehearsal.CaptureError("capture interrompue")

    monkeypatch.setattr(rehearsal, "_exercise", interrupted)
    with pytest.raises(rehearsal.CaptureError, match="refaire la préparation"):
        rehearsal.apply(directory, plan["approval_sha256"])
    assert json.loads((directory / "receipt.json").read_bytes())["status"] == "FAILED"
    monkeypatch.setattr(rehearsal, "_exercise", _no_browser)
    with pytest.raises(rehearsal.CaptureError, match="déjà utilisée"):
        rehearsal.apply(directory, plan["approval_sha256"])


@pytest.mark.parametrize("scenario", ["details", "navigation"])
def test_real_chromium_applies_one_rehearsal_and_records_dom_and_screenshots(
    output: Path, capsys: pytest.CaptureFixture[str], scenario: str,
) -> None:
    if os.getenv("CLAWFEDORA_REQUIRE_BROWSER_REHEARSAL") != "1":
        pytest.skip("Exécuté dans le job Chromium de la CI")
    assert main([
        "browser-rehearsal", "preview", "--output-dir", str(output), "--scenario", scenario,
    ]) == 0
    plan = json.loads(capsys.readouterr().out)
    args = [
        "browser-rehearsal", "apply", "--session", plan["session"],
        "--approve-sha256", plan["approval_sha256"],
    ]
    assert main(args) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["status"] == "PASS" and receipt["scope"] == "SYNTHETIC_OFFLINE"
    assert receipt["before"] == plan["before"] and receipt["after"] == plan["after"]
    if scenario == "details":
        assert receipt["before"] == {"details_open": False, "result_visible": False}
        assert receipt["after"] == {"details_open": True, "result_visible": True}
    else:
        assert receipt["before"]["url"] == rehearsal.NAV_HOME
        assert receipt["after"]["url"] == rehearsal.NAV_REPORT
        assert receipt["navigation"]["served"] == [rehearsal.NAV_HOME, rehearsal.NAV_REPORT]
    assert receipt["fixture_sha256"] == plan["fixture_sha256"]
    assert [row["filename"] for row in receipt["screenshots"]] == ["before.png", "after.png"]
    session = Path(plan["session"])
    for image in receipt["screenshots"]:
        path = session / image["filename"]
        assert image["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert path.stat().st_mode & 0o777 == 0o600
    assert receipt["screenshots"][0]["sha256"] != receipt["screenshots"][1]["sha256"]
    assert main(args) == 2
    assert "déjà utilisée" in json.loads(capsys.readouterr().out)["reason"]


def test_navigation_approval_cannot_bind_a_modified_destination(
    output: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rehearsal, "_playwright_api", _no_browser)
    plan = rehearsal.preview(output, scenario="navigation")
    session = Path(plan["session"])
    path = session / "plan.json"
    raw = path.read_bytes().replace(b".invalid/rapport", b".invalid/autre")
    path.write_bytes(raw)
    with pytest.raises(rehearsal.CaptureError, match="plan différent"):
        rehearsal.apply(session, hashlib.sha256(raw).hexdigest())
    assert not (session / "attempt.json").exists()


@pytest.mark.parametrize("modified", [
    {"href": "/autre"},
    {"href": "https://hors-perimetre.invalid/"},
    {"target": "_blank"},
    {"download": ""},
    {"ping": "https://hors-perimetre.invalid/"},
])
def test_navigation_refuses_a_different_link_before_click(modified: dict[str, str]) -> None:
    attrs = {"href": "/rapport", **modified}
    link = SimpleNamespace(
        count=lambda: 1, is_visible=lambda: True,
        get_attribute=lambda attr, **_kwargs: attrs.get(attr),
    )
    with pytest.raises(rehearsal.CaptureError, match="clic refusé"):
        rehearsal._report_link(SimpleNamespace(locator=lambda _selector: link))


def test_navigation_fence_consumes_only_the_expected_main_frame_gets() -> None:
    primary = object()
    foreign = object()
    fence = rehearsal._NavigationFence(SimpleNamespace(main_frame=primary), RuntimeError)
    seen: list[str] = []

    def request(
        url: str, *, frame: object = primary, method: str = "GET",
        resource: str = "document", navigation: bool = True,
    ) -> None:
        fence.handle(SimpleNamespace(
            request=SimpleNamespace(
                url=url, frame=frame, method=method, resource_type=resource,
                is_navigation_request=lambda: navigation,
            ),
            abort=lambda: seen.append("refus"),
            fulfill=lambda **_response: seen.append(url),
        ))

    request(rehearsal.NAV_REPORT)
    request(rehearsal.NAV_HOME)
    request(rehearsal.NAV_HOME)
    fence.authorize_report()
    request(rehearsal.NAV_REPORT, method="POST")
    request(rehearsal.NAV_REPORT, resource="fetch", navigation=False)
    request(rehearsal.NAV_REPORT, frame=foreign)
    request(rehearsal.NAV_REPORT + "?parametre=1")
    request("https://hors-perimetre.invalid/")
    request(rehearsal.NAV_REPORT)
    request(rehearsal.NAV_REPORT)
    assert fence.served == [rehearsal.NAV_HOME, rehearsal.NAV_REPORT]
    assert fence.blocked_requests == 8 and seen.count("refus") == 8
    assert fence.expected is None
    with pytest.raises(rehearsal.CaptureError, match="déjà utilisée"):
        fence.authorize_report()


def test_real_chromium_refuses_another_destination_and_another_tab() -> None:
    if os.getenv("CLAWFEDORA_REQUIRE_BROWSER_REHEARSAL") != "1":
        pytest.skip("Exécuté dans le job Chromium de la CI")
    sync_playwright, playwright_error = rehearsal._playwright_api()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            context = browser.new_context(offline=True, service_workers="block")
            try:
                page = context.new_page()
                fence = rehearsal._NavigationFence(page, playwright_error)
                context.route("**/*", fence.handle)
                page.goto(rehearsal.NAV_HOME, timeout=5000)
                fence.authorize_report()
                other = context.new_page()
                with pytest.raises(playwright_error):
                    other.goto(rehearsal.NAV_REPORT, timeout=5000)
                with pytest.raises(playwright_error):
                    other.goto(rehearsal.NAV_HOME + "hors-perimetre", timeout=5000)
                other.close()
                assert fence.served == [rehearsal.NAV_HOME]
                assert fence.blocked_requests >= 2
                assert page.url == rehearsal.NAV_HOME
                rehearsal._report_link(page).click(timeout=5000)
                assert page.url == rehearsal.NAV_REPORT
                assert fence.served == [rehearsal.NAV_HOME, rehearsal.NAV_REPORT]
                with pytest.raises(playwright_error):
                    page.reload(timeout=5000)
            finally:
                context.close()
        finally:
            browser.close()
