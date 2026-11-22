"""Independent user-owned Atelier systemd unit. No container or WebUI credentials."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from clawfedora.storage import mount_unit_lines, service_storage_check

SERVICE = "clawfedora-dashboard.service"
HEADER = "# Managed by OPENCLAW_LOCAL_FEDORA\n"


def render(repo_root: Path, runtime: Path, unit_root: Path) -> Path:
    for path in (repo_root, runtime, unit_root):
        if not path.is_absolute() or not re.fullmatch(r"[A-Za-z0-9_./-]+", str(path)):
            raise ValueError("Chemins absolus simples requis")
        for parent in (path, *path.parents):
            if parent.is_symlink():
                raise ValueError("Liens symboliques non autorisés")
    if not (runtime / ".openclaw-fedora-runtime").is_file():
        raise ValueError("Runtime géré requis")
    python = runtime / "runtime/venv/bin/python"
    if not python.is_file():
        raise ValueError("Python géré absent")
    unit_root.mkdir(parents=True, exist_ok=True)
    unit = unit_root / SERVICE
    if unit.is_symlink() or (
        unit.exists() and not unit.read_text(encoding="utf-8").startswith(HEADER)
    ):
        raise ValueError("Unité système non gérée : refus")
    body = (
        "[Unit]\nDescription=Atelier IA Fedora - interface unique\n"
        "After=openclaw-gateway.service\n"
        + mount_unit_lines(runtime, repo_root)
        + "\n[Service]\nUMask=0077\nRestart=on-failure\nRestartSec=5\n"
        + service_storage_check(runtime, repo_root)
        + f"ExecStart={python} -m clawfedora.cli --root {repo_root} dashboard "
        + f"--serve --runtime-root {runtime}\n"
        + "NoNewPrivileges=true\nPrivateTmp=true\n\n"
        + "[Install]\nWantedBy=default.target\n"
    )
    unit.write_text(HEADER + body, encoding="utf-8")
    unit.chmod(0o600)
    return unit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--unit-root", required=True, type=Path)
    args = parser.parse_args()
    render(args.root, args.runtime_root, args.unit_root)


if __name__ == "__main__":
    main()
