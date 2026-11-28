from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from clawfedora import desktop_portal
from clawfedora.cli import main
from clawfedora.desktop_rehearsal import (
    DETAILS,
    MAX_OBSERVATIONS,
    TTL_SECONDS,
    WINDOW,
    DesktopRehearsal,
)
from clawfedora.notion_write import _digest


@pytest.mark.parametrize(("window", "mode", "accepted"), [
    ("other-window", "pointer", True),
    (WINDOW, "observe", True),
    (WINDOW, "pointer", False),
])
def test_consent_is_required_and_bound_to_exact_window_and_mode(
    window: str, mode: str, accepted: bool,
) -> None:
    session = DesktopRehearsal("pointer")
    with pytest.raises(ValueError, match="en attente"):
        session.observe(window=WINDOW)
    with pytest.raises(ValueError, match="consentement requis"):
        session.consent(window=window, mode=mode, accepted=accepted)
    with pytest.raises(ValueError, match="session fermée"):
        session.observe(window=WINDOW)
    with pytest.raises(ValueError, match="déjà décidée"):
        session.consent(window=WINDOW, mode="pointer", accepted=True)


def test_observation_grant_cannot_control_the_pointer() -> None:
    session = DesktopRehearsal("observe")
    session.consent(window=WINDOW, mode="observe", accepted=True)
    before = session.observe(window=WINDOW)
    with pytest.raises(ValueError, match="non approuvée"):
        session.open_details(before, window=WINDOW, target=DETAILS, approved=True)
    assert session.observe(window=WINDOW) == before


def test_click_requires_approval_and_the_latest_observation_of_the_same_session() -> None:
    session = DesktopRehearsal("pointer")
    other = DesktopRehearsal("pointer")
    for instance in (session, other):
        instance.consent(window=WINDOW, mode="pointer", accepted=True)
    before = session.observe(window=WINDOW)
    foreign = other.observe(window=WINDOW)
    for snapshot, target, approved in ((before, DETAILS, False), (before, "other", True),
                                       (foreign, DETAILS, True)):
        with pytest.raises(ValueError):
            session.open_details(snapshot, window=WINDOW, target=target, approved=approved)
    session.open_details(before, window=WINDOW, target=DETAILS, approved=True)
    with pytest.raises(ValueError, match="périmée"):
        session.open_details(before, window=WINDOW, target=DETAILS, approved=True)
    after = session.observe(window=WINDOW)
    assert after.details_open and after.revision == before.revision + 1
    assert session.events.count("DETAILS_OPENED") == 1


@pytest.mark.parametrize(("reason", "terminal"), [
    ("expired", "EXPIRED"), ("switch", "WINDOW_CHANGED"), ("revoke", "REVOKED"),
    ("limit", "OBSERVATION_LIMIT"),
])
def test_stop_conditions_are_terminal(reason: str, terminal: str) -> None:
    now = 10.0
    session = DesktopRehearsal("pointer", clock=lambda: now)
    session.consent(window=WINDOW, mode="pointer", accepted=True)
    before = session.observe(window=WINDOW)
    if reason == "revoke":
        session.revoke()
    elif reason == "limit":
        for _ in range(MAX_OBSERVATIONS - 1):
            session.observe(window=WINDOW)
        with pytest.raises(ValueError, match="limite"):
            session.observe(window=WINDOW)
    else:
        if reason == "expired":
            now += TTL_SECONDS
        with pytest.raises(ValueError):
            session.open_details(
                before, window=WINDOW if reason == "expired" else "other-window",
                target=DETAILS, approved=True,
            )
    assert session.closed and session.events[-1] == terminal
    with pytest.raises(ValueError, match="session fermée"):
        session.open_details(before, window=WINDOW, target=DETAILS, approved=True)
    assert "DETAILS_OPENED" not in session.events


@pytest.mark.parametrize("mode", ["observe", "pointer"])
def test_cli_exposes_a_simulation_result(mode: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["desktop-rehearsal", "--mode", mode]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["scope"] == "SYNTHETIC_NO_COMPOSITOR" and result["closed"]
    assert result["before"]["window"] == WINDOW
    assert result["before"]["details_open"] is False
    assert result["after"]["details_open"] is (mode == "pointer")
    assert result["events"][-1] == "REVOKED"


def test_wayland_acceptance_binds_modes_and_invalidates_an_active_session(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    def advertised(pointer: bool, version: int = 2) -> dict[str, object]:
        def call(args: tuple[str, ...]) -> str:
            if args[3] == "GetNameOwner":
                return 's ":1.42"'
            if args[-2] == desktop_portal.SOURCES:
                return "v u 2"  # v2 and window bit.
            if args[-1] == "version":
                return f"v u {version}"
            return "v u 2" if pointer else "v u 1"

        return desktop_portal.probe("wayland", call=call)

    def command(mode: str, pointer: bool) -> tuple[int, dict[str, object]]:
        def read(_session: str | None) -> dict[str, object]:
            return advertised(pointer)

        with monkeypatch.context() as patch:
            patch.setattr(desktop_portal, "probe", read)
            returncode = main(["desktop-rehearsal", "--mode", mode, "--require-portal"])
        return returncode, json.loads(capsys.readouterr().out)

    status, observation = command("observe", pointer=False)
    assert status == 0 and observation["scope"] == "SYNTHETIC_NO_COMPOSITOR"
    assert observation["before"] == observation["after"]
    status, refused = command("pointer", pointer=False)
    assert status == 2 and refused["status"] == "REFUSED"
    assert "pointer_advertised" in str(refused["reason"])
    with pytest.raises(ValueError, match="eis_api_in_version"):
        DesktopRehearsal("pointer", capabilities=advertised(pointer=True, version=1))
    status, controlled = command("pointer", pointer=True)
    events = controlled["events"]
    assert status == 0 and isinstance(events, list) and "DETAILS_OPENED" in events

    exercise = DesktopRehearsal("pointer", capabilities=advertised(pointer=True))
    exercise.consent(window=WINDOW, mode="pointer", accepted=True)
    before = exercise.observe(window=WINDOW)
    exercise.portal_closed()
    with pytest.raises(ValueError, match="session fermée"):
        exercise.open_details(before, window=WINDOW, target=DETAILS, approved=True)
    with pytest.raises(ValueError, match="session fermée"):
        exercise.observe(window=WINDOW)
    assert exercise.events == ["CONSENT_GRANTED", "OBSERVED", "PORTAL_CLOSED"]

    output = os.environ.get("CLAWFEDORA_DESKTOP_ACCEPTANCE_EVIDENCE")
    if output:
        report = {
            "scope": "SYNTHETIC_NO_COMPOSITOR",
            "tested_commit": os.environ["GITHUB_SHA"],
            "campaign_verdict": "CONFORME",
            "cases": ["observe", "pointer_refused", "eis_unavailable",
                      "pointer_approved", "portal_closed"],
        }
        Path(output).write_text(
            json.dumps({**report, "report_sha256": _digest(report)}, indent=2) + "\n",
            encoding="utf-8",
        )
