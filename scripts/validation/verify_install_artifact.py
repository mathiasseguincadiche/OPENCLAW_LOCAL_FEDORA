"""Fail-closed offline verification of approved upstream release artifacts.

The manifest is reviewed with source code. No digest or URL is learned from a
downloaded sidecar, mutable latest tag, environment variable or redirect.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "config/install_artifact_integrity.json"
ALLOWED = {
    "openclaw": ("sha512", re.compile(r"https://registry\\.npmjs\\.org/openclaw/-/openclaw-(\\d{4}\\.\\d+\\.\\d+)\\.tgz")),
    "ollama": ("sha256", re.compile(r"https://github\\.com/ollama/ollama/releases/download/v(\\d+\\.\\d+\\.\\d+)/ollama-linux-amd64\\.tar\\.zst")),
}


def checked_entry(kind: str, version: str, manifest: Path = MANIFEST) -> dict[str, str]:
    if kind not in ALLOWED:
        raise ValueError("unsupported release artifact")
    raw: Any = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema") != 1:
        raise ValueError("invalid integrity manifest schema")
    entry = raw.get(kind)
    if not isinstance(entry, dict) or set(entry) != {"url", "version", ALLOWED[kind][0]}:
        raise ValueError("incomplete artifact integrity entry")
    algo, pattern = ALLOWED[kind]
    url = entry["url"]
    digest = entry[algo]
    if not all(isinstance(v, str) for v in entry.values()):
        raise ValueError("non-string integrity metadata")
    match = pattern.fullmatch(url)
    if not match or match.group(1) != version or entry["version"] != version:
        raise ValueError("release URL/version mismatch")
    if not re.fullmatch(r"[a-f0-9]{" + str(hashlib.new(algo).digest_size * 2) + r"}", digest):
        raise ValueError("malformed release digest")
    return entry


def verify(kind: str, version: str, artifact: Path, manifest: Path = MANIFEST) -> None:
    entry = checked_entry(kind, version, manifest)
    algo = ALLOWED[kind][0]
    h = hashlib.new(algo)
    with artifact.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    if h.hexdigest() != entry[algo]:
        raise ValueError("upstream artifact hash mismatch; refusal before installation")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["url", "verify"])
    parser.add_argument("kind", choices=sorted(ALLOWED))
    parser.add_argument("version")
    parser.add_argument("artifact", nargs="?")
    args = parser.parse_args()
    try:
        if args.action == "url":
            if args.artifact:
                raise ValueError("artifact argument invalid for URL lookup")
            print(checked_entry(args.kind, args.version)["url"])
        else:
            if not args.artifact:
                raise ValueError("artifact path required")
            verify(args.kind, args.version, Path(args.artifact))
            print("INSTALL_ARTIFACT_INTEGRITY=PASS")
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.exit(2, f"INSTALL_ARTIFACT_INTEGRITY=REFUSED: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
