"""Offline validation of reviewed npm and PyPI artifact integrity locks.

The registry release manifests are captured in a separate CI job. Validation
checks structure, exact runtime pins, integrity and bundled-package ancestry.
It does not assert that an installed package matches the lock; installers must
use npm ci / pip --require-hashes and perform their own runtime checks.
"""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
PIN = re.compile(r"^([\w.-]+)==([\w.+!-]+)$")
HASH = re.compile(r"--hash=sha256:([0-9a-f]{64})(?=\s|$)")
B64 = re.compile(r"^sha512-([a-zA-Z0-9+/]+={0,2})$")


def read_python_hashes(path: Path) -> dict[str, tuple[str, int]]:
    """Require binary-only installs and hashes for every pinned wheel package."""
    raw = path.read_text(encoding="utf-8")
    if "--only-binary=:all:" not in raw:
        raise ValueError("installation binaire uniquement requise")
    entries: dict[str, tuple[str, int]] = {}
    buffer = ""
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line == "--only-binary=:all:":
            continue
        if line.startswith("-r "):
            # Speech lock references the full production hash inventory.
            if path.name != "python-speech-hashes.txt" or line != "-r python-runtime-hashes.txt":
                raise ValueError("inclusion non autorisée")
            continue
        buffer += " " + line.rstrip("\\").strip()
        if line.endswith("\\"):
            continue
        parts = buffer.split()
        buffer = ""
        match = PIN.fullmatch(parts[0])
        if not match:
            raise ValueError("paquet Python non épinglé")
        name = re.sub(r"[-_.]+", "-", match.group(1)).lower()
        hashes = HASH.findall(" ".join(parts[1:]))
        if not hashes or len(hashes) != len(set(hashes)):
            raise ValueError("empreinte manquante ou répétée")
        if len(hashes) != len(parts) - 1:
            raise ValueError("directive Python non autorisée")
        if name in entries:
            raise ValueError("paquet Python dupliqué")
        entries[name] = (match.group(2), len(hashes))
    if buffer or not entries:
        raise ValueError("verrou Python incomplet")
    return entries


def verify(root: Path = ROOT) -> dict[str, int]:
    version = yaml.safe_load((root / "config/runtime_versions.yaml").read_text(encoding="utf-8"))
    policy = json.loads((root / "config/install_artifact_integrity.json").read_text(encoding="utf-8"))
    npm = json.loads((root / "config/npm-runtime/package-lock.json").read_text(encoding="utf-8"))
    package = json.loads((root / "config/npm-runtime/package.json").read_text(encoding="utf-8"))
    if npm.get("lockfileVersion") != 3 or npm.get("packages", {}).get("", {}).get("dependencies") != package["dependencies"]:
        raise ValueError("npm lock et paquet racine différents")
    targets = {
        "openclaw": version["openclaw"]["version"],
        "@openclaw/parallel-plugin": version["openclaw"]["plugins"]["parallel"]["version"],
    }
    if package["dependencies"] != targets:
        raise ValueError("npm runtime root désynchronisé")
    registry = npm["packages"]
    bundled = 0
    for name, value in registry.items():
        if not name:
            continue
        if value.get("inBundle") is True:
            # These npm-bundled descendants are integrity-covered by their
            # closest parent tarball, not by separate registry digests.
            parent = name
            covered = False
            while "/node_modules/" in parent:
                parent = parent.rsplit("/node_modules/", 1)[0]
                if parent in registry and registry[parent].get("integrity"):
                    covered = True
                    break
            if not covered:
                raise ValueError("paquet npm bundled sans archive parente vérifiée")
            bundled += 1
            continue
        if value.get("link"):
            raise ValueError("lien npm non épinglé")
        url = value.get("resolved", "")
        digest = value.get("integrity", "")
        if not url.startswith("https://registry.npmjs.org/"):
            raise ValueError("source npm hors registre officiel")
        match = B64.fullmatch(digest)
        if not match or len(base64.b64decode(match[1], validate=True)) != 64:
            raise ValueError("intégrité npm SHA512 absente ou invalide")
    for name, pin in targets.items():
        record = registry[f"node_modules/{name}"]
        if record["version"] != pin:
            raise ValueError("version npm divergente")
    expected = base64.b64encode(bytes.fromhex(policy["openclaw"]["sha512"])).decode("ascii")
    if registry["node_modules/openclaw"]["integrity"] != "sha512-" + expected:
        raise ValueError("OpenClaw npm lock différent de l'archive vérifiée")
    prod = read_python_hashes(root / "config/python-runtime-hashes.txt")
    extras = read_python_hashes(root / "config/python-speech-hashes.txt")
    constraints = {
        re.sub(r"[-_.]+", "-", name).lower(): ver
        for line in (root / "config/python-runtime-constraints.txt").read_text().splitlines()
        if line and not line.startswith("#")
        for name, ver in [line.split("==")]
    }
    if not constraints.items() <= {k: v[0] for k, v in prod.items()}.items():
        raise ValueError("verrou Python divergent des contraintes")
    if not {"setuptools", "wheel"} <= prod.keys():
        raise ValueError("outils de build PEP517 sans empreintes")
    if "faster-whisper" not in extras or set(extras) & set(prod):
        raise ValueError("fermeture voix manquante ou dupliquée")
    return {"npm_packages": len(registry) - 1, "npm_bundled": bundled,
            "python_production": len(prod), "python_speech_extra": len(extras)}


if __name__ == "__main__":
    print(json.dumps(verify(), sort_keys=True))
