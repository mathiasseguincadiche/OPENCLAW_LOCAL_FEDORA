from __future__ import annotations

from pathlib import Path

import pytest

from clawfedora.cli import main

ROOT = Path(__file__).resolve().parents[1]


def test_project_selftest_runs_complete_offline_cycle(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--root", str(ROOT), "project", "selftest"]) == 0
    output = capsys.readouterr().out
    assert '"verdict": "PASS"' in output
    assert '"status": "COMPLETE"' in output
