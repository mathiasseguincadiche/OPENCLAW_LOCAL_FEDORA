"""Immutable dependency closures must fail closed on silent version/hash drift."""

from __future__ import annotations

import json
import runpy
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
lock = runpy.run_path(str(ROOT / "scripts/validation/check_dependency_artifact_locks.py"))


def test_production_hashes_exactly_match_pins() -> None:
    assert lock["check_python"](ROOT) == 23


def test_build_backend_is_pinned_and_sha256_verified() -> None:
    assert lock["check_build"](ROOT) == 2


def test_build_hash_removal_is_refused(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "python-build-constraints.txt").write_text(
        (ROOT / "config/python-build-constraints.txt").read_text()
    )
    lock_file = (ROOT / "config/python-build-hashes.txt").read_text()
    (config / "python-build-hashes.txt").write_text(
        lock_file.replace("--hash=sha256:", "--sha256:", 1)
    )
    with pytest.raises(ValueError, match="SHA256|option"):
        lock["check_build"](tmp_path)


def test_speech_artifacts_are_locked_for_python_313() -> None:
    assert lock["check_speech"](ROOT) == 21


def test_locked_npm_packages_come_from_registry_or_verified_bundle() -> None:
    direct, bundled = lock["check_npm"](ROOT)
    assert direct >= 400
    assert bundled >= 100


def test_python_hash_replacement_cannot_pass(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    original = (ROOT / "config/python-runtime-constraints.txt").read_text()
    hashes = (ROOT / "config/python-runtime-hashes.txt").read_text()
    (tmp_path / "config/python-runtime-constraints.txt").write_text(original)
    (tmp_path / "config/python-runtime-hashes.txt").write_text(
        hashes.replace("--hash=sha256:", "--sha256:", 1)
    )
    with pytest.raises(ValueError, match="SHA256|directive"):
        lock["check_python"](tmp_path)


def test_npm_dependency_integrity_cannot_be_removed(tmp_path: Path) -> None:
    original = json.loads((ROOT / "config/npm-runtime/package-lock.json").read_text())
    original["packages"]["node_modules/openclaw"].pop("integrity")
    for path in (
        "config/npm-runtime",
        "config",
    ):
        (tmp_path / path).mkdir(parents=True, exist_ok=True)
    (tmp_path / "config/npm-runtime/package-lock.json").write_text(json.dumps(original))
    (tmp_path / "config/npm-runtime/package.json").write_text(
        (ROOT / "config/npm-runtime/package.json").read_text()
    )
    (tmp_path / "config/install_artifact_integrity.json").write_text(
        (ROOT / "config/install_artifact_integrity.json").read_text()
    )
    (tmp_path / "config/runtime_versions.yaml").write_text(
        (ROOT / "config/runtime_versions.yaml").read_text()
    )
    with pytest.raises(ValueError, match="without integrity"):
        lock["check_npm"](tmp_path)


def test_locked_npm_installer_preserves_verified_archive_and_cli() -> None:
    scripts = (ROOT / "scripts/linux/15_verified_installer.sh").read_text()
    closure = (ROOT / "scripts/linux/18_npm_closure.sh").read_text()
    configure = (ROOT / "scripts/linux/03_configure_openclaw.sh").read_text()
    assert '"$PYTHON" "$VERIFY" verify "$KIND" "$PIN" "$ARCHIVE"' in scripts
    assert 'bash "$SCRIPT_DIR/18_npm_closure.sh" --apply' in scripts
    assert 'npm ci --prefix "$STAGE"' in closure
    assert "--engine-strict" in closure and "--ignore-scripts" in closure
    assert 'npm ls --global --all --prefix "$PREFIX"' in closure
    assert "plugins install --link" in configure
    assert "plugins update" not in configure


def test_speech_hash_tampering_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config/python-speech-constraints.txt").write_text(
        (ROOT / "config/python-speech-constraints.txt").read_text()
    )
    original = (ROOT / "config/python-speech-hashes.txt").read_text()
    (tmp_path / "config/python-speech-hashes.txt").write_text(
        original.replace("--hash=sha256:", "--sha256:", 1)
    )
    with pytest.raises(ValueError, match="SHA256|directive"):
        lock["check_speech"](tmp_path)

def test_runtime_installers_never_build_unhashed_source_distributions() -> None:
    bootstrap = (ROOT / "scripts/linux/00_bootstrap.sh").read_text()
    voice = (ROOT / "scripts/linux/13_openwebui.sh").read_text()
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    for source in (bootstrap, voice, ci):
        assert "python-build-hashes.txt" in source
        assert "--require-hashes --only-binary=:all:" in source
        assert "--no-build-isolation --no-deps -e" in source



def _npm_sandbox(tmp_path: Path) -> Path:
    for name in ("npm-runtime/package-lock.json", "npm-runtime/package.json",
                 "install_artifact_integrity.json", "runtime_versions.yaml"):
        target = tmp_path / "config" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((ROOT / "config" / name).read_text())
    return tmp_path


def test_reviewed_security_overrides_are_exact_and_applied_in_the_lock() -> None:
    versions = (ROOT / "config/runtime_versions.yaml").read_text()
    manifest = json.loads((ROOT / "config/npm-runtime/package.json").read_text())
    assert lock["reviewed_overrides"](versions) == manifest["overrides"]
    assert set(manifest["overrides"]) == {"npm", "undici", "zod"}
    packages = json.loads((ROOT / "config/npm-runtime/package-lock.json").read_text())["packages"]
    assert lock["check_overrides"](manifest, packages, versions) == 3


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda m, _l: m["overrides"].__setitem__("zod", "^4.6.7"), "differ|exact"),
        (lambda m, _l: m["overrides"].pop("undici"), "differ"),
        (lambda m, _l: m["overrides"].__setitem__("minimatch", "11.0.4"), "differ"),
        (lambda _m, locked: locked["packages"]["node_modules/zod"].__setitem__("version", "4.6.5"),
         "not applied"),
    ],
)
def test_unreviewed_or_unapplied_npm_overrides_are_refused(
    tmp_path: Path, mutate: Any, message: str
) -> None:
    root = _npm_sandbox(tmp_path)
    manifest_path = root / "config/npm-runtime/package.json"
    lock_path = root / "config/npm-runtime/package-lock.json"
    manifest, locked = json.loads(manifest_path.read_text()), json.loads(lock_path.read_text())
    mutate(manifest, locked)
    manifest_path.write_text(json.dumps(manifest))
    lock_path.write_text(json.dumps(locked))
    with pytest.raises(ValueError, match=message):
        lock["check_npm"](root)


def test_bundled_copies_are_not_counted_as_overridden() -> None:
    packages = json.loads((ROOT / "config/npm-runtime/package-lock.json").read_text())["packages"]
    bundled = packages["node_modules/npm/node_modules/undici"]
    # The npm tarball ships its own undici: an override cannot reach it, the audit reports it.
    assert bundled.get("inBundle") is True and bundled["version"] != "8.12.3"
