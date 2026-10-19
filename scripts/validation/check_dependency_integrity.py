"""Audit committed npm and Python artifact hashes without using the network.

The npm lock must cover OpenClaw and Parallel together. Bundled npm children have
no separate tarball: their content is covered by the containing archive's SRI.
Python locks cover binary runtime and build wheels, never arbitrary URLs or sdists.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)==([A-Za-z0-9][A-Za-z0-9_.+!-]*)")
HASH = re.compile(r"^--hash=sha256:([a-fA-F0-9]{64})(?:\\\\)?$")
SRI = re.compile(r"^sha512-([A-Za-z0-9+/]+={0,2})$")


def _canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _read(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError("verrou absent ou lié")
    return path.read_text(encoding="utf-8")


def parse_pins(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in _read(path).splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        match = PIN.fullmatch(value)
        if match is None:
            raise ValueError("dépendance non épinglée")
        name = _canonical(match.group(1))
        if name in result:
            raise ValueError("dépendance dupliquée")
        result[name] = match.group(2)
    if not result:
        raise ValueError("fichier de contraintes vide")
    return result


def parse_python_hashes(path: Path) -> dict[str, tuple[str, set[str]]]:
    result: dict[str, tuple[str, set[str]]] = {}
    current = ""
    for raw in _read(path).splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("--hash="):
            match = HASH.fullmatch(line.removesuffix(" \\").strip())
            if not current or match is None:
                raise ValueError("ligne SHA256 de verrou Python invalide")
            result[current][1].add(match.group(1).lower())
            continue
        token = line.removesuffix("\\").strip()
        match = PIN.fullmatch(token)
        if match is None:
            raise ValueError("élément non épinglé ou option externe Python")
        current = _canonical(match.group(1))
        if current in result:
            raise ValueError("hash Python dupliqué")
        result[current] = (match.group(2), set())
    if not result or any(not hashes for _, hashes in result.values()):
        raise ValueError("hash SHA256 absent")
    return result


def check_python(root: Path) -> dict[str, int]:
    total = 0
    for name in ("runtime", "build"):
        expected = parse_pins(root / f"config/python-{name}-constraints.txt")
        locked = parse_python_hashes(root / f"config/python-{name}-hashes.txt")
        actual = {key: version for key, (version, _) in locked.items()}
        if expected != actual:
            raise ValueError(f"fermeture Python {name} non alignée")
        total += len(locked)
    return {"python_pinned_packages": total}


def check_npm(root: Path) -> dict[str, int]:
    import tomllib

    manifest = json.loads(_read(root / "config/npm-runtime/package.json"))
    lock = json.loads(_read(root / "config/npm-runtime/package-lock.json"))
    versions = tomllib.loads(_read(root / "pyproject.toml"))
    del versions  # The npm pins are checked against the runtime version YAML below.
    runtime = _read(root / "config/runtime_versions.yaml")
    import re as _re
    openclaw_version = _re.search(r'(?m)^openclaw:\\s*\\n\\s+version: "([^"]+)"', runtime)
    parallel_version = _re.search(r'(?m)^\\s+parallel:\\s*\\n\\s+package: "[^"]+"\\s*\\n\\s+version: "([^"]+)"', runtime)
    if not openclaw_version or not parallel_version:
        raise ValueError("versions npm attendues absentes")
    expected = {
        "openclaw": openclaw_version.group(1),
        "@openclaw/parallel-plugin": parallel_version.group(1),
    }
    packages = lock.get("packages")
    if lock.get("lockfileVersion") != 3 or not isinstance(packages, dict):
        raise ValueError("format lock npm incorrect")
    if manifest.get("dependencies") != expected or packages.get("", {}).get("dependencies") != expected:
        raise ValueError("verrou npm divergent des pins versionnés")
    if manifest.get("private") is not True or lock.get("name") != manifest.get("name"):
        raise ValueError("manifest npm non privé ou divergent")
    downloaded = bundled = 0
    for path, entry in packages.items():
        if not path:
            continue
        if not path.startswith("node_modules/") or not isinstance(entry, dict):
            raise ValueError("package npm non attendu")
        sri, uri = entry.get("integrity"), entry.get("resolved")
        if entry.get("inBundle") is True and sri is None and uri is None:
            bundled += 1
            continue
        if not isinstance(uri, str) or not uri.startswith("https://registry.npmjs.org/"):
            raise ValueError("archive npm de provenance non approuvée")
        if not isinstance(sri, str):
            raise ValueError("archive npm sans intégrité")
        match = SRI.fullmatch(sri)
        if match is None:
            raise ValueError("intégrité npm non SHA512")
        try:
            if len(base64.b64decode(match.group(1), validate=True)) != 64:
                raise ValueError("taille SHA512 npm incorrecte")
        except binascii.Error as exc:
            raise ValueError("intégrité npm encodée invalide") from exc
        downloaded += 1
    if bundled + downloaded != len(packages) - 1:
        raise ValueError("paquet npm non vérifiable")

    # Compare the npm lock's top-level archive digest with the independently
    # pinned official release manifest; reject two conflicting SHA512 values.
    release = json.loads(_read(root / "config/install_artifact_integrity.json"))
    official = release.get("openclaw", {})
    top = packages.get("node_modules/openclaw", {})
    if top.get("version") != expected["openclaw"] or official.get("version") != expected["openclaw"]:
        raise ValueError("version OpenClaw divergente")
    official_hex = official.get("sha512")
    if not isinstance(official_hex, str) or len(official_hex) != 128:
        raise ValueError("empreinte officielle OpenClaw invalide")
    if top.get("integrity") != "sha512-" + base64.b64encode(bytes.fromhex(official_hex)).decode("ascii"):
        raise ValueError("empreinte npm/manifest OpenClaw divergente")
    plugin = packages.get("node_modules/@openclaw/parallel-plugin", {})
    if plugin.get("version") != expected["@openclaw/parallel-plugin"]:
        raise ValueError("version du plugin Parallel divergente")
    return {"npm_downloaded": downloaded, "npm_bundled": bundled}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        report = {**check_npm(args.root), **check_python(args.root)}
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"DEPENDENCY_INTEGRITY=REFUSED reason={type(exc).__name__}")
        return 2
    print("DEPENDENCY_INTEGRITY=PASS " + json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
