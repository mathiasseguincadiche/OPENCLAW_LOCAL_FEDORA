from __future__ import annotations

import fcntl
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_ollama_pin_never_accepts_a_neighbor_version() -> None:
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; claw_extract_ollama_version "$2"',
            "bash",
            str(ROOT / "scripts/linux/lib/runtime.sh"),
            "ollama version is 0.35.10",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0 and result.stdout.strip() == "0.35.10"
    assert result.stdout.strip() != "0.35.1"


def test_upgrade_dry_run_makes_no_runtime_changes(tmp_path: Path) -> None:
    runtime = tmp_path / "absent"
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/linux/12_upgrade.sh")],
        env={**os.environ, "OPENCLAW_LOCAL_FEDORA_ROOT": str(runtime)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0 and "UPGRADE_DRY_RUN=PASS" in result.stdout
    assert "openclaw=2026.9.8 ollama=0.35.1" in result.stdout and not runtime.exists()


@pytest.mark.skipif(os.geteuid() == 0, reason="operator script deliberately refuses root")
def test_upgrade_refuses_to_interrupt_worker(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    (runtime / "state").mkdir(parents=True)
    (runtime / ".openclaw-fedora-runtime").touch()
    with (runtime / "state/worker.lock").open("w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        result = subprocess.run(
            ["bash", str(ROOT / "scripts/linux/12_upgrade.sh"), "--apply"],
            env={**os.environ, "OPENCLAW_LOCAL_FEDORA_ROOT": str(runtime)},
            capture_output=True,
            text=True,
        )
    assert result.returncode == 2 and "worker actif" in result.stderr


@pytest.mark.skipif(os.geteuid() == 0, reason="operator script deliberately refuses root")
def test_upgrade_backs_up_before_install_and_stops_on_failure(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    scripts = repo / "scripts/linux"
    (scripts / "lib").mkdir(parents=True)
    (repo / "config").mkdir()
    for name in ("12_upgrade.sh", "lib/runtime.sh"):
        shutil.copy2(ROOT / "scripts/linux" / name, scripts / name)
    shutil.copy2(ROOT / "config/runtime_versions.yaml", repo / "config/runtime_versions.yaml")
    log = tmp_path / "events"
    for name, text in {
        "08_backup_restore.sh": 'echo backup >> "$UPGRADE_TEST_LOG"',
        "06_install.sh": 'echo install >> "$UPGRADE_TEST_LOG"; exit 7',
    }.items():
        path = scripts / name
        path.write_text("#!/bin/bash\n" + text + "\n")
        path.chmod(0o755)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("systemctl", "sudo"):
        path = bin_dir / name
        path.write_text('#!/bin/bash\necho "service $*" >> "$UPGRADE_TEST_LOG"\n')
        path.chmod(0o755)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / ".openclaw-fedora-runtime").touch()
    result = subprocess.run(
        ["bash", str(scripts / "12_upgrade.sh"), "--apply"],
        env={
            **os.environ,
            "PATH": str(bin_dir) + ":" + os.environ["PATH"],
            "OPENCLAW_LOCAL_FEDORA_ROOT": str(runtime),
            "UPGRADE_TEST_LOG": str(log),
        },
        capture_output=True,
        text=True,
    )
    events = log.read_text().splitlines()
    assert events.index("backup") < events.index("install")
    assert result.returncode == 7 and "UPGRADE_RESULT=FAIL" in result.stderr
    assert "stop ollama.service" in events[-1]
