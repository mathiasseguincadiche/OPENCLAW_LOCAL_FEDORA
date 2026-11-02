"""A03: a late cloud answer for project A must never draw or act on A inside project B.

The scenario runs the real dashboard.js under Node with a minimal DOM and simulated API
answers (tests/js/dashboard_cloud_race.mjs): no browser, network, model or cloud call.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tests/js/dashboard_cloud_race.mjs"
SCRIPT = ROOT / "src/clawfedora/web/dashboard.js"


def test_cloud_consent_follows_the_opened_project_only() -> None:
    node = shutil.which("node")
    if node is None:
        # The quality job installs Node and sets this flag: there the scenario may not be
        # skipped. Fedora containers without Node still run the rest of the suite.
        if os.environ.get("CLAWFEDORA_REQUIRE_NODE") == "1":
            pytest.fail("Node est requis dans ce job pour le scénario navigateur A03")
        pytest.skip("Node absent: scénario navigateur A03 non exécuté")
    result = subprocess.run(
        [node, str(HARNESS), str(SCRIPT)],
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert "DASHBOARD_CLOUD_RACE=PASS" in result.stdout
