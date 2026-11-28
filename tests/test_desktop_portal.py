from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest

from clawfedora import desktop_portal as portal
from clawfedora.cli import main

OWNER = ':1.42'


def test_portal_cli_reads_only_the_active_owner_on_the_user_bus(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    calls = []
    replies = iter([f's "{OWNER}"', "v u 5", "v u 3", "v u 2", "v u 6"])

    def run(args: tuple[str, ...], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert kwargs == {"capture_output": True, "text": True, "timeout": 3, "check": False}
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, next(replies), "")

    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setattr(portal.subprocess, "run", run)
    assert main(["desktop-portal"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "PROBED" and data["qualification"] == "PENDING"
    assert data["window_advertised"] and data["pointer_advertised"] and data["eis_api_in_version"]
    assert len(calls) == 5
    assert all(args[:len(portal.COMMAND)] == portal.COMMAND for args in calls)
    assert "--user" in portal.COMMAND and "--auto-start=no" in portal.COMMAND
    assert "--allow-interactive-authorization=no" in portal.COMMAND
    assert calls[0][-3:] == ("GetNameOwner", "s", portal.DESTINATION)
    assert all(args[-7:-2] == (OWNER, portal.DESKTOP_PATH,
                                "org.freedesktop.DBus.Properties", "Get", "ss")
               for args in calls[1:])


@pytest.mark.parametrize(("session", "status"), [(None, "SESSION_UNKNOWN"), ("x11", "NOT_WAYLAND")])
def test_portal_skips_sessions_without_wayland(session: str | None, status: str) -> None:
    def no_call(_args: tuple[str, ...]) -> str:
        pytest.fail("Aucune lecture D-Bus attendue")

    assert portal.probe(session, call=no_call) == {"status": status, "qualification": "PENDING"}


@pytest.mark.parametrize(("reply", "status"), [
    ("v b true", "UNVERIFIED"),
    ("v u 4294967296", "UNVERIFIED"),
    (None, "UNAVAILABLE"),
])
def test_portal_keeps_observation_result_if_remote_desktop_cannot_be_verified(
    reply: str | None, status: str,
) -> None:
    def call(args: tuple[str, ...]) -> str:
        if args[3] == "GetNameOwner":
            return f's "{OWNER}"'
        if args[-2] == portal.SOURCES:
            return "v u 1"  # ScreenCast v1 advertises monitors only.
        if reply is None:
            raise subprocess.TimeoutExpired(args, 2)
        return reply

    result = portal.probe("wayland", call=call)
    assert result["status"] == "INCOMPLETE"
    assert result["window_advertised"] is False and result["pointer_advertised"] is None
    assert result["eis_api_in_version"] is None
    assert result["remote_desktop"] == {"status": status, "version": None, "mask": None}


def test_portal_requires_a_unique_bus_owner() -> None:
    calls = []

    def wrong_owner(args: tuple[str, ...]) -> str:
        calls.append(args)
        return 's "org.example.Other"'

    assert portal.probe("wayland", call=wrong_owner)["status"] == "PORTAL_UNAVAILABLE"
    assert len(calls) == 1
