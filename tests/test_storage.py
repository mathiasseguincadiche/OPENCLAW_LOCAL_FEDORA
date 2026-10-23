"""Storage regressions use a simulated mount, never a real disk or privileged mount."""
from __future__ import annotations

import json
import os
import runpy
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from clawfedora import storage
from clawfedora.webui_setup import render

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def settings(tmp_path: Path) -> storage.StorageSettings:
    return storage.StorageSettings(tmp_path, tmp_path / "IA/Openclaw", "ext4", "", 15, 8)


@pytest.fixture
def mounted(settings: storage.StorageSettings, monkeypatch: pytest.MonkeyPatch) -> None:
    original_stat = Path.stat
    original_mount = Path.is_mount

    def stat(path: Path, *args: Any, **kwargs: Any) -> os.stat_result:
        record = original_stat(path, *args, **kwargs)
        if path == settings.mountpoint or settings.mountpoint in path.parents:
            fields = list(record)
            fields[2] += 1
            return os.stat_result(fields)
        return record

    monkeypatch.setattr(Path, "stat", stat)
    monkeypatch.setattr(Path, "is_mount", lambda p: p == settings.mountpoint or original_mount(p))
    monkeypatch.setattr(storage, "mount_details", lambda _p: ("ext4", {"rw"}, "aaaa-bbbb"))


def test_bash_python_and_contract_use_the_same_default() -> None:
    from clawfedora.core_config import resolve_runtime_root

    settings = storage.load_settings(ROOT, use_environment=False)
    assert settings.mountpoint == Path("/data")
    assert settings.runtime_root == Path("/data/IA/Openclaw")
    assert resolve_runtime_root() == settings.runtime_root
    result = subprocess.run(
        ["bash", "-c", "source scripts/linux/lib/runtime.sh; claw_runtime_root; claw_mountpoint"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    assert result.stdout.splitlines() == [str(settings.runtime_root), str(settings.mountpoint)]


def test_missing_disk_refuses_every_root_without_creating_it(
    tmp_path: Path, settings: storage.StorageSettings, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Path, "is_mount", lambda _p: False)
    for runtime in (settings.runtime_root, tmp_path.parent / "escape"):
        with pytest.raises(ValueError):
            storage.require_storage(runtime, settings)
        assert not runtime.exists()
    env = {**os.environ, "OPENCLAW_LOCAL_FEDORA_ROOT": str(settings.runtime_root),
           "OPENCLAW_LOCAL_FEDORA_MOUNT": str(settings.mountpoint)}
    result = subprocess.run(
        ["bash", "-c", 'source scripts/linux/lib/runtime.sh; claw_require_storage "$1"',
         "_", str(settings.runtime_root)],
        cwd=ROOT, env=env, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 2 and "STORAGE_RESULT=REFUSED" in result.stderr
    assert not settings.runtime_root.exists()


def test_fresh_runtime_is_valid_on_the_expected_volume(
    settings: storage.StorageSettings, mounted: None,
) -> None:
    storage.require_storage(settings.runtime_root, settings)
    assert not settings.runtime_root.exists()


def test_mount_on_system_filesystem_is_refused(
    settings: storage.StorageSettings, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Path, "is_mount", lambda _p: True)
    # Do not depend on whether pytest uses a tmpfs with a different real st_dev.
    original = Path.stat

    def stat(path: Path, *args: Any, **kwargs: Any) -> os.stat_result:
        record = list(original(path, *args, **kwargs))
        record[2] = 123
        return os.stat_result(record)

    monkeypatch.setattr(Path, "stat", stat)
    with pytest.raises(ValueError, match="distinct"):
        storage.require_storage(settings.runtime_root, settings)


@pytest.mark.parametrize("filesystem,options", [("xfs", {"rw"}), ("ext4", {"ro"}),
                                               ("ext4", {"rw", "noexec"})])
def test_invalid_mount_properties_are_refused(
    settings: storage.StorageSettings, mounted: None, monkeypatch: pytest.MonkeyPatch,
    filesystem: str, options: set[str],
) -> None:
    monkeypatch.setattr(storage, "mount_details", lambda _p: (filesystem, options, ""))
    with pytest.raises(ValueError):
        storage.require_storage(settings.runtime_root, settings)


def test_recorded_volume_uuid_cannot_silently_change(
    settings: storage.StorageSettings, mounted: None,
) -> None:
    storage.require_storage(settings.runtime_root, replace(settings, volume_uuid="AAAA-BBBB"))
    with pytest.raises(ValueError, match="UUID"):
        storage.require_storage(settings.runtime_root, replace(settings, volume_uuid="cccc-dddd"))


@pytest.mark.parametrize("component", storage.SENSITIVE_DIRECTORIES)
def test_sensitive_directory_redirect_is_refused(
    settings: storage.StorageSettings, component: str,
) -> None:
    target = settings.runtime_root / component
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(settings.mountpoint / "unrelated", target_is_directory=True)
    with pytest.raises(ValueError, match="lié"):
        storage.validate_layout(settings.runtime_root, settings)


def test_intermediate_parent_symlink_and_traversal_are_refused(
    settings: storage.StorageSettings,
) -> None:
    (settings.mountpoint / "IA").symlink_to(settings.mountpoint / "elsewhere")
    with pytest.raises(ValueError, match="lié"):
        storage.validate_layout(settings.runtime_root, settings)
    with pytest.raises(ValueError, match="canonique"):
        storage.validate_layout(settings.mountpoint / "IA/../escape", settings)


def test_precheck_reports_data_and_system_capacity(
    settings: storage.StorageSettings, mounted: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    ns = runpy.run_path(str(ROOT / "scripts/validation/preinstall_host.py"))
    monkeypatch.setitem(ns["collect"].__globals__, "cmd", lambda *_args: (0, ""))
    monkeypatch.setattr(storage, "load_settings", lambda: settings)
    monkeypatch.setattr(storage, "free_bytes", lambda _p: 0)
    values = {name: status for name, status, _note in ns["collect"]()}
    assert values["storage"] == "PASS"
    assert values["disk-free"] == values["system-free"] == "FAIL"
    assert not settings.runtime_root.exists()


def test_all_webui_services_keep_the_mount_and_private_podman_store(
    settings: storage.StorageSettings, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = settings.runtime_root
    runtime.mkdir(parents=True)
    (runtime / ".openclaw-fedora-runtime").touch()
    monkeypatch.setenv("OPENCLAW_LOCAL_FEDORA_MOUNT", str(settings.mountpoint))
    monkeypatch.setenv("OPENCLAW_LOCAL_FEDORA_ROOT", str(runtime))
    units = settings.mountpoint / "units"
    render(ROOT, runtime, units,
           image_digest="ghcr.io/open-webui/open-webui@sha256:" + "a" * 64)
    for unit in units.glob("*.service"):
        text = unit.read_text()
        assert f"ConditionPathIsMountPoint={settings.mountpoint}" in text
        assert "ExecStartPre=/usr/bin/python3 -I -S" in text
    service = (units / "clawfedora-webui.service").read_text()
    config = storage.podman_config(runtime)
    assert f"Environment=CONTAINERS_STORAGE_CONF={config}" in service
    assert str(runtime / "runtime/podman/storage") in config.read_text()
    assert str(runtime / "runtime/podman/tmp") in service
    assert config.stat().st_mode & 0o077 == 0
    assert "--remote=false" in service


def test_missing_or_invalid_storage_contract_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    for value in ({}, {"schema_version": 99}):
        (tmp_path / "config/storage.json").write_text(json.dumps(value))
        with pytest.raises(ValueError):
            storage.load_settings(tmp_path)


@pytest.mark.parametrize("entrypoint", ["agents", "project", "backup", "cloud"])
def test_public_commands_cannot_write_outside_the_declared_mount(
    tmp_path: Path, entrypoint: str,
) -> None:
    from clawfedora import cli, cloud_cli, ops_cli

    runtime = tmp_path / "must-not-be-created"
    common = ["--root", str(ROOT)]
    if entrypoint == "agents":
        result = cli.main([*common, "agents", "deploy", "--runtime-root", str(runtime)])
    elif entrypoint == "project":
        result = cli.main([*common, "project", "create", "--runtime-root", str(runtime),
                           "--project-id", "test-project", "--title", "Read-only check"])
    elif entrypoint == "backup":
        result = ops_cli.main([*common, "--runtime-root", str(runtime), "backup"])
    else:
        result = cloud_cli.main([*common, "--runtime-root", str(runtime),
                                 "reconcile", "--eur", "1"])
    assert result == 2
    assert not runtime.exists()


def test_podman_renderer_refuses_linked_storage(settings: storage.StorageSettings) -> None:
    runtime = settings.runtime_root
    (runtime / "runtime").mkdir(parents=True)
    (runtime / "runtime/podman").symlink_to(settings.mountpoint / "other-containers")
    with pytest.raises(ValueError, match="lié"):
        storage.render_podman_storage(runtime)
    assert not (settings.mountpoint / "other-containers").exists()
