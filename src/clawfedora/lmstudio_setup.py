"""Render a user-owned LM Studio bridge service without installing third-party apps."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from clawfedora.project_common import assert_no_symlinks
from clawfedora.storage import mount_unit_lines, service_storage_check
from clawfedora.webui_setup import _secret

SERVICE = "clawfedora-lmstudio-bridge"


def render(repo_root: Path, runtime: Path, unit_root: Path) -> dict[str, str]:
    for path in (repo_root, runtime, unit_root):
        if not path.is_absolute() or not re.fullmatch(r"[A-Za-z0-9_./-]+", str(path)):
            raise ValueError("Chemins système absolus sans caractères spéciaux requis")
        for parent in (path, *path.parents):
            if parent.is_symlink():
                raise ValueError("Lien symbolique sur chemin géré interdit")
    if not (runtime / ".openclaw-fedora-runtime").is_file():
        raise ValueError("Runtime ClawFedora non initialisé")
    python = runtime / "runtime/venv/bin/python"
    if not python.is_file():
        raise ValueError("Environnement Python ClawFedora absent")
    if (runtime / "state").is_symlink():
        raise ValueError("État ClawFedora lié interdit")
    state = runtime / "state/lmstudio"
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    assert_no_symlinks(state, label="LM Studio")
    state.chmod(0o700)
    token = state / "bridge.token"
    _secret(token)  # exact 64-hex, private, stable across rerenders
    unit_root.mkdir(parents=True, exist_ok=True)
    unit = unit_root / (SERVICE + ".service")
    if unit.is_symlink():
        raise ValueError("Unité systemd liée interdite")
    prefix = "# Managed by OPENCLAW_LOCAL_FEDORA\n"
    if unit.exists() and not unit.read_text(encoding="utf-8").startswith(prefix):
        raise ValueError("Unité systemd existante non gérée : aucune écriture")
    body = (
        "[Unit]\nDescription=Atelier IA - pont local LM Studio\n"
        "After=openclaw-gateway.service\n"
        + mount_unit_lines(runtime, repo_root)
        + "\n[Service]\nUMask=0077\nRestart=on-failure\nRestartSec=5\n"
        + service_storage_check(runtime, repo_root)
        + f"Environment=OPENCLAW_LOCAL_FEDORA_ROOT={runtime}\n"
        + f"ExecStart={python} -m clawfedora.lmstudio_bridge "
        + f"--root {repo_root} --runtime-root {runtime}\n"
        + "NoNewPrivileges=true\nPrivateTmp=true\n\n"
        + "[Install]\nWantedBy=default.target\n"
    )
    unit.write_text(prefix + body, encoding="utf-8")
    unit.chmod(0o600)
    return {"unit": SERVICE + ".service", "address": "http://127.0.0.1:18894"}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--unit-root", type=Path, required=True)
    args = parser.parse_args(argv)
    render(args.root, args.runtime_root, args.unit_root)


if __name__ == "__main__":
    main()
