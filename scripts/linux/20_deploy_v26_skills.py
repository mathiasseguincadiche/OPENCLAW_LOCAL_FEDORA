#!/usr/bin/env python3
"""Installer V26 dans les workspaces gérés. Dry-run par défaut, zéro écrasement."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MARKER = ".openclaw-fedora-managed"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def no_symlink(path):
    for part in (path, *path.parents):
        require(not part.is_symlink(), f"lien symbolique refusé: {part}")


def plan(runtime):
    allocation = json.loads((REPO / "config/v26_skills.json").read_text(encoding="utf-8"))
    sources = REPO / "skills"
    available = {p.name for p in sources.iterdir() if p.is_dir() and (p / "SKILL.md").is_file()}
    require(len(allocation) == 7 and len(available) == 11, "inventaire des agents ou skills incomplet")
    require(set().union(*(set(x) for x in allocation.values())) == available, "attributions incomplètes")
    no_symlink(runtime)
    actions = []
    for agent, names in allocation.items():
        require(re.fullmatch(r"[a-z0-9-]+", agent) is not None, f"agent invalide: {agent}")
        workspace = runtime / "workspaces" / agent
        no_symlink(workspace)
        marker = workspace / MARKER
        require(marker.is_file() and not marker.is_symlink(), f"workspace non géré: {workspace}")
        data = json.loads(marker.read_text(encoding="utf-8"))
        require(data.get("managed_by") == "OPENCLAW_LOCAL_FEDORA" and data.get("agent_id") == agent,
                f"marqueur incohérent: {workspace}")
        require(len(names) == len(set(names)), f"doublon d'attribution pour {agent}")
        for name in names:
            src = sources / name
            require(name in available and re.fullmatch(r"v26-[a-z0-9-]+", name), f"skill inconnu: {name}")
            require((src / "SKILL.md").read_text(encoding="utf-8").startswith("---\nname: " + name + "\n"),
                    f"frontmatter invalide: {name}")
            no_symlink(src)
            require(not any(p.is_symlink() for p in src.rglob("*")), f"source liée: {src}")
            dst = workspace / "skills" / name
            no_symlink(dst)
            require(not dst.exists(), f"collision sans écrasement: {dst}")
            actions.append((src, dst))
    return actions


def apply(actions):
    prepared = []
    promoted = []
    dirs = set()
    try:
        for src, dst in actions:
            if not dst.parent.exists():
                dst.parent.mkdir(mode=0o750)
                dirs.add(dst.parent)
            staged = dst.parent / (".v26-staged-" + uuid.uuid4().hex)
            shutil.copytree(src, staged)
            prepared.append((staged, dst))
        for staged, dst in prepared:
            staged.rename(dst)
            promoted.append(dst)
    except Exception:
        for dst in promoted:
            shutil.rmtree(dst, ignore_errors=True)
        for staged, _ in prepared:
            shutil.rmtree(staged, ignore_errors=True)
        for path in dirs:
            try:
                path.rmdir()
            except OSError:
                pass
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description="Déploiement isolé de 11 Skills V26 dans les 7 agents")
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        actions = plan(args.runtime_root.expanduser())
        print(f"V26_PLAN=OK copies={len(actions)} mode={'APPLY' if args.apply else 'DRY_RUN'}")
        for _, dst in actions:
            print(f"  {dst}")
        if args.apply:
            apply(actions)
            print("V26_RESULT=INSTALLED (chargement OpenClaw à vérifier sur Fedora)")
        else:
            print("V26_RESULT=DRY_RUN (aucun changement)")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"V26_RESULT=REFUSED: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
