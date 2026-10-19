"""Check versioned Python artifact hashes and npm package-lock integrity, offline.

This proves the reviewed manifest is complete enough for hash-mode pip and
npm ci; real RPM/PEP517 build dependencies remain out of scope.
"""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)==([A-Za-z0-9][A-Za-z0-9_.+!-]*)")
HASH = re.compile(r"--hash=sha256:([a-f0-9]{64})(?=\s|$)")


def canonical(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def check_python(root: Path) -> int:
    pins = {}
    for line in (root / "config/python-runtime-constraints.txt").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            match = PIN.fullmatch(line)
            if match is None:
                raise ValueError("invalid Python production version")
            pins[canonical(match[1])] = match[2]
    hashed = (root / "config/python-runtime-hashes.txt").read_text()
    logical = hashed.replace("\\\n", " ").splitlines()
    checks: dict[str, str] = {}
    for line in logical:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = PIN.match(line)
        if match is None:
            raise ValueError("unhashed Python requirement")
        key = canonical(match[1])
        if key in checks:
            raise ValueError("duplicate Python requirement")
        if not HASH.search(line):
            raise ValueError("Python artifact without SHA256")
        remaining = HASH.sub("", line[match.end():]).strip()
        if remaining:
            raise ValueError("unexpected Python lock directive")
        checks[key] = match[2]
    if not pins or checks != pins:
        raise ValueError("Python hashes differ from pinned versions")
    return len(pins)


def check_build(root: Path) -> int:
    """Require exact reviewed SHA256 artifacts for the isolated PEP517 backend."""
    config = root / "config"
    pins: dict[str, str] = {}
    for line in (config / "python-build-constraints.txt").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = PIN.fullmatch(line)
        if match is None:
            raise ValueError("invalid pinned Python build backend")
        key = canonical(match[1])
        if key in pins:
            raise ValueError("duplicate Python build pin")
        pins[key] = match[2]
    logical = (config / "python-build-hashes.txt").read_text().replace("\\\n", " ").splitlines()
    hashes: dict[str, str] = {}
    for line in logical:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = PIN.match(line)
        if match is None or not HASH.search(line):
            raise ValueError("Python build backend missing SHA256")
        if HASH.sub("", line[match.end():]).strip():
            raise ValueError("unexpected Python build lock option")
        key = canonical(match[1])
        if key in hashes:
            raise ValueError("duplicate Python build hash")
        hashes[key] = match[2]
    if pins != hashes or set(pins) != {"setuptools", "wheel"}:
        raise ValueError("Python build hash list diverges from exact backend pins")
    return len(hashes)


def check_speech(root: Path) -> int:
    config = root / "config"
    pins = {}
    for line in (config / "python-speech-constraints.txt").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            match = PIN.fullmatch(line)
            if match is None:
                raise ValueError("invalid speech version pin")
            pins[canonical(match[1])] = match[2]
    hashed = (config / "python-speech-hashes.txt").read_text()
    rows = hashed.replace("\\\n", " ").splitlines()
    checked = {}
    for line in rows:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = PIN.match(line)
        if match is None or not HASH.search(line):
            raise ValueError("speech package without version or SHA256")
        if HASH.sub("", line[match.end():]).strip():
            raise ValueError("unexpected speech lock directive")
        key = canonical(match[1])
        if key in checked:
            raise ValueError("duplicate speech package")
        checked[key] = match[2]
    if checked != pins or len(pins) < 15:
        raise ValueError("speech SHA256 hashes do not cover reviewed closure")
    if pins.get("faster-whisper") != "1.2.1" or "ctranslate2" not in pins:
        raise ValueError("required speech packages not pinned")
    return len(pins)


def check_npm(root: Path) -> tuple[int, int]:
    base = root / "config/npm-runtime"
    lock = json.loads((base / "package-lock.json").read_text())
    manifest = json.loads((base / "package.json").read_text())
    releases = json.loads((root / "config/install_artifact_integrity.json").read_text())
    versions = (root / "config/runtime_versions.yaml").read_text()
    if lock.get("lockfileVersion") != 3:
        raise ValueError("invalid npm lockfile version")
    if lock.get("name") != manifest.get("name"):
        raise ValueError("npm lock and manifest name differ")
    pkgs: dict[str, Any] = lock["packages"]
    expected = manifest["dependencies"]
    if set(expected) != {"openclaw", "@openclaw/parallel-plugin"}:
        raise ValueError("unexpected npm root dependencies")
    if pkgs[""].get("dependencies") != expected:
        raise ValueError("npm root spec drift")
    for package, version in expected.items():
        if not re.search(r"(?m)^  version: \"" + re.escape(version) + r"\"$", versions):
            raise ValueError("npm version does not match runtime policy")
        if pkgs["node_modules/" + package]["version"] != version:
            raise ValueError("npm resolved version drift")
    if releases["openclaw"]["version"] != expected["openclaw"]:
        raise ValueError("OpenClaw tarball manifest version mismatch")
    count = 0
    bundled = 0
    for path, value in pkgs.items():
        if not path:
            continue
        digest = value.get("integrity")
        if digest:
            if not value.get("resolved", "").startswith("https://registry.npmjs.org/"):
                raise ValueError("npm registry source unexpected")
            if not re.fullmatch(r"sha512-[a-zA-Z0-9+/]+=*", digest):
                raise ValueError("npm dependency without SHA512 integrity")
            count += 1
        elif value.get("inBundle") is True:
            # npm bundles nested packages in the already-hashed parent archive.
            parents = [p for p in pkgs if p and path.startswith(p + "/node_modules/")]
            if not any(pkgs[p].get("integrity") for p in parents):
                raise ValueError("npm bundled package lacks hashed enclosing tarball")
            bundled += 1
        else:
            raise ValueError("npm dependency without integrity")
    direct = pkgs["node_modules/openclaw"]["integrity"]
    recorded = base64.b64decode(direct.removeprefix("sha512-")).hex()
    if recorded != releases["openclaw"]["sha512"]:
        raise ValueError("npm OpenClaw digest differs from signed manifest")
    return count, bundled


def main() -> int:
    try:
        python_count = check_python(ROOT)
        build_count = check_build(ROOT)
        speech_count = check_speech(ROOT)
        npm_count, bundled = check_npm(ROOT)
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print("DEPENDENCY_LOCK_RESULT=REFUSED " + type(exc).__name__)
        return 2
    print(
        f"DEPENDENCY_LOCK_RESULT=PASS python={python_count} "
        f"build={build_count} speech={speech_count} npm_hashed={npm_count} npm_bundled={bundled}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
