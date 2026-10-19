"""Regenerate reviewed wheel hashes from exact pins in an isolated Python venv.

Never installs packages or changes versions; the operator first prepares a clean
venv with pinned production and speech packages. This script then snapshots
official PyPI release archives. Rebuilding locks is an explicit --apply step.
"""
from __future__ import annotations

import argparse
import importlib.metadata as metadata
import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def snapshot(root: Path = ROOT) -> tuple[dict[str, str], dict[str, str]]:
    base: dict[str, str] = {}
    for line in (root / "config/python-runtime-constraints.txt").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.count("==") != 1:
            raise ValueError("production pin invalide")
        name, version = line.split("==", 1)
        base[canonical(name)] = version
    found = {
        canonical(str(dist.metadata["Name"])): dist.version
        for dist in metadata.distributions()
        if dist.metadata.get("Name")
    }
    for name in ("setuptools", "wheel"):
        if name not in found:
            raise ValueError("outil de build absent: " + name)
        base[name] = found[name]
    for name, version in base.items():
        if found.get(name) != version:
            raise ValueError("environnement non conforme: " + name)
    speech = {name: version for name, version in found.items() if name not in base
              and name not in {"pip", "openclaw-local-fedora"}}
    if "faster-whisper" not in speech or len(base) > 100 or len(speech) > 100:
        raise ValueError("environnement voix incomplet ou mélangé")
    return base, speech


def official_wheel_hashes(name: str, version: str) -> list[str]:
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    with urllib.request.urlopen(url, timeout=30) as response:
        record = json.load(response)
    if record["info"]["version"] != version:
        raise ValueError("version PyPI inattendue")
    hashes = sorted({
        item["digests"]["sha256"] for item in record["urls"]
        if item["packagetype"] == "bdist_wheel"
    })
    if not hashes or any(not re.fullmatch("[0-9a-f]{64}", x) for x in hashes):
        raise ValueError("wheels SHA256 introuvables: " + name)
    return hashes


def render(wheels: dict[str, str]) -> str:
    text = ""
    for name, version in sorted(wheels.items()):
        hashes = official_wheel_hashes(name, version)
        text += f"{name}=={version} \\\n"
        text += " \\\n".join("    --hash=sha256:" + digest for digest in hashes)
        text += "\n"
    return text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    production, speech = snapshot()
    print(f"PYTHON_LOCK_PLAN production={len(production)} speech={len(speech)}")
    if not args.apply:
        print("DRY_RUN=PASS files_not_changed=true")
        return 0
    base = (
        "# Frozen official PyPI wheel SHA256 for Fedora/CPython installations.\n"
        "--only-binary=:all:\n" + render(production)
    )
    extra = (
        "# Speech-only wheels: import the complete production closure.\n"
        "-r python-runtime-hashes.txt\n--only-binary=:all:\n" + render(speech)
    )
    (ROOT / "config/python-runtime-hashes.txt").write_text(base)
    (ROOT / "config/python-speech-hashes.txt").write_text(extra)
    print("PYTHON_LOCK_RESULT=WRITTEN review_diff_before_merge=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
