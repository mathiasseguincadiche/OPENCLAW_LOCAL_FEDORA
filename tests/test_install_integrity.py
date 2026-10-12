from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/validation/verify_install_artifact.py"
spec = importlib.util.spec_from_file_location("verify_install_artifact", SCRIPT)
assert spec is not None and spec.loader is not None
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


def test_release_manifest_matches_exact_runtime_pins() -> None:
    versions = yaml.safe_load((ROOT / "config/runtime_versions.yaml").read_text())
    for kind in ("openclaw", "ollama"):
        pin = versions[kind]["version"]
        entry = verifier.checked_entry(kind, pin)
        assert pin in entry["url"]
        assert entry["version"] == pin
        assert "latest" not in entry["url"]


def test_verifier_fails_closed_on_tampering_version_url_and_missing_digest(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "release.tgz"
    archive.write_bytes(b"known signed release sample")
    manifest = {
        "schema": 1,
        "openclaw": {
            "version": "2026.10.2",
            "url": "https://registry.npmjs.org/openclaw/-/openclaw-2026.10.2.tgz",
            "sha512": hashlib.sha512(archive.read_bytes()).hexdigest(),
        },
    }
    record = tmp_path / "integrity.json"
    record.write_text(json.dumps(manifest))
    verifier.verify("openclaw", "2026.10.2", archive, record)
    archive.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="hash mismatch"):
        verifier.verify("openclaw", "2026.10.2", archive, record)
    with pytest.raises(ValueError, match="URL/version mismatch"):
        verifier.checked_entry("openclaw", "2026.10.20", record)
    manifest["openclaw"]["url"] = "https://evil.example/openclaw-2026.10.2.tgz"
    record.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="URL/version mismatch"):
        verifier.checked_entry("openclaw", "2026.10.2", record)
    manifest["openclaw"].pop("sha512")
    record.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="incomplete"):
        verifier.checked_entry("openclaw", "2026.10.2", record)


@pytest.mark.parametrize("kind", ["openclaw", "ollama"])
def test_verified_installer_dry_run_is_non_mutating(tmp_path: Path, kind: str) -> None:
    runtime = tmp_path / "uncreated"
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/linux/15_verified_installer.sh"), kind],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "OPENCLAW_LOCAL_FEDORA_ROOT": str(runtime)},
    )
    assert result.returncode == 0, result.stderr
    assert "VERIFIED_INSTALL_DRY_RUN=PASS" in result.stdout
    assert "sha_required=true" in result.stdout
    assert not runtime.exists()


def test_verified_installer_refuses_unlisted_versions() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "url", "openclaw", "2026.10.99"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 2
    assert "REFUSED" in result.stderr
