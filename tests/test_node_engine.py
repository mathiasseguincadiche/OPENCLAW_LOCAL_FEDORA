"""OpenClaw's Node.js engine is checked before npm ci, with Fedora 45's real packages.

Fedora 45 ships Node 22 as ``nodejs`` (refused by OpenClaw), 24.18.0 as ``nodejs24`` and
26.3.1 as ``nodejs26`` (observed in the Fedora 45 CI container on 2 November 2026).
"""

from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
engine = runpy.run_path(str(ROOT / "scripts/validation/check_node_engine.py"))
OPENCLAW_RANGE = ">=24.16.0 <25 || >=26.1.0"


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("v22.23.1", False),  # Fedora 45 default `nodejs`
        ("v24.18.0", True),   # Fedora 45 `nodejs24`
        ("v26.3.1", True),    # Fedora 45 `nodejs26`
        ("v24.15.9", False), ("v24.16.0", True), ("v25.0.0", False), ("v26.0.9", False),
    ],
)
def test_openclaw_range_matches_npm_semantics(version: str, expected: bool) -> None:
    parsed = engine["parse_version"](version)
    assert engine["satisfies"](parsed, OPENCLAW_RANGE) is expected


@pytest.mark.parametrize(
    ("expression", "version", "expected"),
    [(">24", "24.9.9", False), (">24", "25.0.0", True), ("<=24", "24.9.9", True),
     ("=24", "24.1.0", True), (">= 24.16.0", "24.16.0", True), ("24.18.0", "24.18.0", True)],
)
def test_partial_and_spaced_comparators(expression: str, version: str, expected: bool) -> None:
    assert engine["satisfies"](engine["parse_version"](version), expression) is expected


@pytest.mark.parametrize("expression", ["", "^24.16.0", "24.x", ">=24 ||", "1.2.3 - 2.0.0"])
def test_unsupported_ranges_are_refused_not_guessed(expression: str) -> None:
    with pytest.raises(ValueError):
        engine["satisfies"]((24, 18, 0), expression)


def test_engine_is_read_from_the_reviewed_lock_and_reported(
    capsys: pytest.CaptureFixture[str],
) -> None:
    version, required = engine["required_engine"]()
    lock = json.loads((ROOT / "config/npm-runtime/package-lock.json").read_text())
    assert lock["packages"]["node_modules/openclaw"]["version"] == version
    assert required == OPENCLAW_RANGE
    assert engine["main"](["--node-version", "v24.18.0"]) == 0
    assert "NODE_ENGINE_RESULT=PASS" in capsys.readouterr().out
    assert engine["main"](["--node-version", "v22.23.1"]) == 2
    refused = capsys.readouterr().out
    assert "NODE_ENGINE_RESULT=REFUSED" in refused and "nodejs24" in refused


def test_installers_use_nodejs24_and_check_the_engine_before_npm_ci() -> None:
    runtime = (ROOT / "scripts/linux/lib/runtime.sh").read_text(encoding="utf-8")
    bootstrap = (ROOT / "scripts/linux/00_bootstrap.sh").read_text(encoding="utf-8")
    closure = (ROOT / "scripts/linux/18_npm_closure.sh").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "CLAW_NODE_PACKAGES=(nodejs24 nodejs24-npm nodejs24-bin nodejs24-npm-bin)" in runtime
    assert " nodejs npm " not in bootstrap
    assert '"${CLAW_NODE_PACKAGES[@]}"' in bootstrap
    install = bootstrap.index('install -y "${PACKAGES[@]}"')
    assert install < bootstrap.index("check_node_engine.py")
    assert closure.index("check_node_engine.py") < closure.index("npm ci")
    # The Fedora 45 job installs exactly the installer's Node packages, then npm ci.
    assert 'dnf install -y "${CLAW_NODE_PACKAGES[@]}"' in workflow
    assert workflow.index("check_node_engine.py") < workflow.index(
        'npm ci --ignore-scripts --no-audit --no-fund --engine-strict --prefix "$NPM_ROOT"'
    )
    assert 'node-version: "24.18.0"' in workflow
