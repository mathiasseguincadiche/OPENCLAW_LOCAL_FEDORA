"""Supply-chain locks are exact, hash-verified, and fail when tampered with."""
from __future__ import annotations

import base64
import hashlib
import json
import runpy
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
lock = SimpleNamespace(**runpy.run_path(str(ROOT / "scripts/validation/check_supply_chain_locks.py")))
npm = SimpleNamespace(**runpy.run_path(str(ROOT / "scripts/validation/verify_npm_artifact.py")))


def test_reviewed_closures_are_consistent_with_pins() -> None:
    result = lock.verify(ROOT)
    assert result["npm_packages"] >= 200
    assert result["python_production"] >= 23
    assert result["python_speech_extra"] >= 10
    assert result["npm_bundled"] > 0
    production = lock.read_python_hashes(ROOT / "config/python-runtime-hashes.txt")
    assert production["pyyaml"][0] == "6.0.3"
    assert production["pillow"][0] == "12.3.0"
    speech = lock.read_python_hashes(ROOT / "config/python-speech-hashes.txt")
    assert speech["faster-whisper"][0] == "1.2.1"
    assert set(production).isdisjoint(speech)


def make_temp_root(tmp_path: Path) -> Path:
    for path in (
        "config/npm-runtime/package-lock.json",
        "config/npm-runtime/package.json",
        "config/runtime_versions.yaml",
        "config/install_artifact_integrity.json",
        "config/python-runtime-constraints.txt",
        "config/python-runtime-hashes.txt",
        "config/python-speech-hashes.txt",
    ):
        destination = tmp_path / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / path, destination)
    return tmp_path


def test_npm_transitive_integrity_tampering_is_refused(tmp_path: Path) -> None:
    root = make_temp_root(tmp_path)
    path = root / "config/npm-runtime/package-lock.json"
    data = json.loads(path.read_text())
    entry = data["packages"]["node_modules/openclaw"]
    entry["integrity"] = "sha512-" + base64.b64encode(bytes(64)).decode()
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="différent"):
        lock.verify(root)


def test_python_wheel_hashes_and_constraints_must_be_exact(tmp_path: Path) -> None:
    root = make_temp_root(tmp_path)
    path = root / "config/python-runtime-hashes.txt"
    original = path.read_text()
    path.write_text(original.replace("--hash=sha256:", "--hash=md5:", 1))
    with pytest.raises(ValueError, match="directive|empreinte"):
        lock.verify(root)
    path.write_text(original.replace("pyyaml==6.0.3", "pyyaml==6.0.2"))
    with pytest.raises(ValueError, match="contraintes"):
        lock.verify(root)


def test_npm_tarball_hash_mismatch_fails_closed(tmp_path: Path) -> None:
    archive = tmp_path / "reviewed.tgz"
    archive.write_bytes(b"expected upstream tarball")
    hashed = "sha512-" + base64.b64encode(
        hashlib.sha512(archive.read_bytes()).digest()
    ).decode()
    root = tmp_path / "repo"
    target = root / "config/npm-runtime/package-lock.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"packages": {"node_modules/@openclaw/parallel-plugin": {
        "resolved": "https://registry.npmjs.org/@openclaw/parallel-plugin/-/parallel-plugin.tgz",
        "integrity": hashed,
    }}}))
    npm.verify("parallel", archive, root)
    archive.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="différente"):
        npm.verify("parallel", archive, root)
    target.write_text(target.read_text().replace("https://", "http://"))
    with pytest.raises(ValueError, match="officielle"):
        npm.checked("parallel", root)
