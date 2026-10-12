from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/linux/14_webui_canary.sh"


def test_canary_browser_flag_dry_run_never_starts_container(tmp_path: Path) -> None:
    runtime = tmp_path / "nonexistent"
    result = subprocess.run(
        ["bash", str(SCRIPT), "--browser", "--with-db-copy"],
        env={**os.environ, "OPENCLAW_LOCAL_FEDORA_ROOT": str(runtime)},
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0
    assert "DRY_RUN=PASS" in result.stdout
    assert "browser=1" in result.stdout
    assert not runtime.exists()


@pytest.mark.skipif(os.geteuid() == 0, reason="real installer refuses root")
def test_browser_canary_refuses_noninteractive_unsafe_apply(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    result = subprocess.run(
        ["bash", str(SCRIPT), "--apply", "--browser", "--with-db-copy"],
        env={**os.environ, "OPENCLAW_LOCAL_FEDORA_ROOT": str(runtime)},
        capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL,
    )
    assert result.returncode == 2
    assert "terminal interactif" in result.stderr
    assert not runtime.exists()
