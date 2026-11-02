"""A06: commands find the OpenClaw CLI installed in ~/.openclaw/bin from a fresh terminal.

The installer adds ~/.openclaw/bin to its own PATH only and never edits shell profiles. A new
terminal therefore lacks it: diagnosis and repair must still find the managed CLI.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from clawfedora.core_config import openclaw_path

ROOT = Path(__file__).resolve().parents[1]
FRESH_PATH = "/usr/bin:/bin"


def _managed_cli(home: Path) -> Path:
    cli = home / ".openclaw/bin/openclaw"
    cli.parent.mkdir(parents=True)
    cli.write_text("#!/bin/sh\necho 'OpenClaw test'\n")
    cli.chmod(0o755)
    return cli


def test_python_resolution_finds_the_managed_cli_without_profile_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cli = _managed_cli(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PATH", FRESH_PATH)
    assert shutil.which("openclaw") is None  # what the old health check saw
    assert shutil.which("openclaw", path=openclaw_path()) == str(cli)
    assert openclaw_path().endswith(FRESH_PATH)  # inherited PATH kept after managed dirs


def test_shell_resolution_finds_the_managed_cli_from_a_fresh_terminal(tmp_path: Path) -> None:
    cli = _managed_cli(tmp_path)
    result = subprocess.run(
        ["bash", "-c", 'source "$1"; claw_openclaw_bin', "bash",
         str(ROOT / "scripts/linux/lib/runtime.sh")],
        capture_output=True, text=True, check=False, timeout=30,
        env={"HOME": str(tmp_path), "PATH": FRESH_PATH},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(cli)


@pytest.mark.parametrize("script", ["09_repair.sh", "03_configure_openclaw.sh"])
def test_repair_and_configuration_use_the_managed_cli(script: str) -> None:
    text = (ROOT / "scripts/linux" / script).read_text(encoding="utf-8")
    assert "command -v openclaw" not in text
    assert "claw_openclaw_bin" in text
    bare = [line for line in text.splitlines() if line.lstrip().startswith("openclaw ")]
    assert bare == []


def test_health_check_resolves_the_cli_with_the_managed_path() -> None:
    text = (ROOT / "src/clawfedora/lifecycle.py").read_text(encoding="utf-8")
    assert 'shutil.which("openclaw", path=openclaw_path())' in text
    assert '"6 managed"' not in text
