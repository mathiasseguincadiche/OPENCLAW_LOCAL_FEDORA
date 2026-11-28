"""Read-only inventory of the running desktop portal's advertised capabilities."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from collections.abc import Callable
from typing import TypedDict

DESTINATION = "org.freedesktop.portal.Desktop"
DESKTOP_PATH = "/org/freedesktop/portal/desktop"
SOURCES = "org.freedesktop.portal.ScreenCast"
DEVICES = "org.freedesktop.portal.RemoteDesktop"
COMMAND = ("busctl", "--user", "--auto-start=no", "--allow-interactive-authorization=no",
           "--timeout=2s", "--no-pager", "call")
WINDOW = 2
POINTER = 2
EIS_VERSION = 2


class Advertised(TypedDict):
    status: str
    version: int | None
    mask: int | None


def _call(args: tuple[str, ...]) -> str:
    result = subprocess.run(
        (*COMMAND, *args), capture_output=True, text=True, timeout=3, check=False,
    )
    if result.returncode:
        raise OSError("lecture du portail indisponible")
    return result.stdout.strip()


def _get_uint(
    call: Callable[[tuple[str, ...]], str], owner: str, interface: str, name: str,
) -> int:
    output = call((owner, DESKTOP_PATH, "org.freedesktop.DBus.Properties",
                   "Get", "ss", interface, name))
    value = re.fullmatch(r"v u ([0-9]{1,10})", output)
    if value is None or int(value[1]) > 0xFFFFFFFF:
        raise ValueError("propriété D-Bus uint32 invalide")
    return int(value[1])


def _advertised(
    call: Callable[[tuple[str, ...]], str], owner: str, interface: str, mask_name: str,
) -> Advertised:
    try:
        version = _get_uint(call, owner, interface, "version")
        mask = _get_uint(call, owner, interface, mask_name)
        if version == 0:
            raise ValueError("version du portail invalide")
    except (OSError, subprocess.TimeoutExpired):
        return {"status": "UNAVAILABLE", "version": None, "mask": None}
    except ValueError:
        return {"status": "UNVERIFIED", "version": None, "mask": None}
    return {"status": "ADVERTISED", "version": version, "mask": mask}


def probe(
    session_type: str | None, *, call: Callable[[tuple[str, ...]], str] = _call,
) -> dict[str, object]:
    if session_type != "wayland":
        return {
            "status": "NOT_WAYLAND" if session_type in ("x11", "tty") else "SESSION_UNKNOWN",
            "qualification": "PENDING",
        }
    try:
        reply = call(("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                      "GetNameOwner", "s", DESTINATION))
        owner = re.fullmatch(r's "(:[0-9]+\.[0-9]+)"', reply)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        owner = None
    if owner is None:
        return {"status": "PORTAL_UNAVAILABLE", "qualification": "PENDING"}

    screen_cast = _advertised(call, owner[1], SOURCES, "AvailableSourceTypes")
    remote_desktop = _advertised(call, owner[1], DEVICES, "AvailableDeviceTypes")
    sources, devices = screen_cast["mask"], remote_desktop["mask"]
    version = remote_desktop["version"]
    return {
        "status": "PROBED" if sources is not None and devices is not None else "INCOMPLETE",
        "qualification": "PENDING",
        "screen_cast": screen_cast,
        "remote_desktop": remote_desktop,
        "window_advertised": None if sources is None else bool(sources & WINDOW),
        "pointer_advertised": None if devices is None else bool(devices & POINTER),
        "eis_api_in_version": None if version is None else version >= EIS_VERSION,
    }


def add_portal_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    subparsers.add_parser("desktop-portal", help="lire les capacités annoncées du portail Wayland")


def session_type() -> str | None:
    return os.environ.get("XDG_SESSION_TYPE")


def run_portal_command() -> int:
    result = probe(session_type())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PROBED" else 2
