"""Verify direct npm tarballs against the SHA512 integrity of the reviewed lock.

Only the explicit OpenClaw and Parallel exact-version artifacts are supported.
The rest of the npm closure is verified during npm ci from package-lock.json.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NAMES = {"openclaw": "openclaw", "parallel": "@openclaw/parallel-plugin"}


def checked(name: str, root: Path = ROOT) -> dict[str, str]:
    record = json.loads((root / "config/npm-runtime/package-lock.json").read_text(
        encoding="utf-8"
    ))["packages"]["node_modules/" + NAMES[name]]
    url = record["resolved"]
    digest = record["integrity"]
    if not url.startswith("https://registry.npmjs.org/") or not digest.startswith("sha512-"):
        raise ValueError("source npm ou empreinte non officielle")
    return {"url": url, "sha512": digest}


def verify(name: str, archive: Path, root: Path = ROOT) -> None:
    expected = base64.b64decode(checked(name, root)["sha512"].removeprefix("sha512-"))
    if len(expected) != 64 or not archive.is_file() or archive.is_symlink():
        raise ValueError("archive npm non fiable")
    if hashlib.sha512(archive.read_bytes()).digest() != expected:
        raise ValueError("archive npm différente du verrou")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("url", "verify"))
    parser.add_argument("name", choices=tuple(NAMES))
    parser.add_argument("archive", nargs="?", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "url":
            print(checked(args.name)["url"])
        elif args.archive is not None:
            verify(args.name, args.archive)
            print("NPM_ARTIFACT_RESULT=PASS")
        else:
            raise ValueError("archive requise")
        return 0
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"NPM_ARTIFACT_RESULT=REFUSED type={type(exc).__name__}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
