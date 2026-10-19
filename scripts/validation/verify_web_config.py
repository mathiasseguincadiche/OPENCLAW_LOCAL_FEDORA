"""Check a managed OpenClaw JSON config without printing secrets or contacting a network.

This checks *saved* policy. A shell wrapper must also restart the native Gateway
and check that systemd reports it active before claiming the switch succeeded.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
from pathlib import Path
from typing import Any

WEB_TOOLS = frozenset(("web_search", "web_fetch"))


def _mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("structure de configuration invalide")
    return value


def verify_policy(payload: dict[str, Any], *, private: bool) -> None:
    """Validate the actual saved seven-agent Web permissions, not a staged marker."""
    tools = _mapping(payload.get("tools"))
    web = _mapping(tools.get("web"))
    for kind in ("search", "fetch"):
        enabled = _mapping(web.get(kind)).get("enabled")
        if enabled is not (not private):
            raise ValueError("activation globale Web incohérente")
    deny = tools.get("deny")
    if not isinstance(deny, list) or not all(isinstance(x, str) for x in deny):
        raise ValueError("liste de refus globale invalide")
    if private and not WEB_TOOLS.issubset(set(deny)):
        raise ValueError("outil Web absent des refus globaux")
    if not private and WEB_TOOLS.intersection(deny):
        raise ValueError("outil Web refusé malgré choix connecté")

    agents = _mapping(_mapping(payload.get("agents")).get("entries"))
    if len(agents) != 7:
        raise ValueError("inventaire des sept rôles incomplet")
    for role in agents.values():
        perms = _mapping(_mapping(role).get("tools"))
        allow = perms.get("alsoAllow", [])
        forbidden = perms.get("deny", [])
        if not isinstance(allow, list) or not isinstance(forbidden, list):
            raise ValueError("droits agent invalides")
        if private and (
            WEB_TOOLS.intersection(allow) or not WEB_TOOLS.issubset(set(forbidden))
        ):
            raise ValueError("permissions Web d'un rôle encore actives")
        if not private and not WEB_TOOLS.issubset(set(allow)):
            raise ValueError("permissions Web connectées d'un rôle incomplètes")


def verify_file(path: Path, *, private: bool) -> None:
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError("chemin de configuration lié interdit")
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
        raise ValueError("fichier de configuration non privé ou non géré")
    if info.st_mode & 0o077:
        raise ValueError("permissions de configuration trop ouvertes")
    if info.st_size > 4_194_304:
        raise ValueError("fichier de configuration trop grand")
    flags = os.O_RDONLY | os.O_NOFOLLOW
    fd = os.open(path, flags)
    with os.fdopen(fd, "r", encoding="utf-8") as source:
        payload = json.load(source)
    verify_policy(_mapping(payload), private=private)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--mode", choices=("private", "connected"), required=True)
    args = parser.parse_args()
    try:
        verify_file(args.config, private=args.mode == "private")
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        # Deliberately never print OpenClaw settings, token values or file contents.
        print(f"WEB_CONFIG_RESULT=REFUSED reason={type(exc).__name__}")
        return 2
    print(f"WEB_CONFIG_RESULT=PASS mode={args.mode} scope=saved-config-not-network-proof")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
