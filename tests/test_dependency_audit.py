"""Weekly dependency audit: new serious advisories fail, reviewed residuals pass until expiry.

Synthetic reports only: no network, no npm or pip-audit run.
"""

from __future__ import annotations

import datetime as dt
import json
import runpy
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
audit = runpy.run_path(str(ROOT / "scripts/validation/check_dependency_audit.py"))
TODAY = dt.date(2026, 11, 3)


def npm_report(*vias: dict[str, Any]) -> dict[str, Any]:
    return {"metadata": {"vulnerabilities": {}},
            "vulnerabilities": {"pkg": {"via": [*vias, "aggregate-name"]}}}


def via(advisory: str, severity: str, name: str = "undici") -> dict[str, Any]:
    return {"url": f"https://github.com/advisories/{advisory}", "severity": severity,
            "name": name, "title": "titre"}


def run(tmp_path: Path, ecosystem: str, report: Any, today: dt.date = TODAY) -> int:
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report))
    return int(audit["main"]([ecosystem, str(path), "--today", today.isoformat()]))


def test_the_reviewed_undici_residual_passes_until_its_expiry(tmp_path: Path) -> None:
    report = npm_report(via("GHSA-xjj6-f33q-929c", "high"), via("GHSA-3g3m-2fjr-6pw4", "moderate"))
    assert run(tmp_path, "npm", report) == 0
    assert run(tmp_path, "npm", report, dt.date(2027, 2, 2)) == 1  # expired: re-review


def test_a_new_high_or_critical_npm_advisory_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(tmp_path, "npm", npm_report(via("GHSA-aaaa-bbbb-cccc", "critical", "zod"))) == 1
    assert "NOUVEAU critical GHSA-aaaa-bbbb-cccc zod" in capsys.readouterr().out


def test_moderate_advisories_are_reported_without_failing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(tmp_path, "npm", npm_report(via("GHSA-mmmm-nnnn-oooo", "moderate"))) == 0
    assert "INFO moderate GHSA-mmmm-nnnn-oooo" in capsys.readouterr().out


def test_the_highest_severity_of_an_advisory_wins(tmp_path: Path) -> None:
    report = npm_report(via("GHSA-dddd-eeee-ffff", "moderate"), via("GHSA-dddd-eeee-ffff", "high"))
    assert run(tmp_path, "npm", report) == 1
    unknown = npm_report(via("GHSA-gggg-hhhh-iiii", "surprise"))
    assert run(tmp_path, "npm", unknown) == 1  # an unknown severity is never under-rated


def test_every_python_advisory_fails_unless_reviewed(tmp_path: Path) -> None:
    clean = {"dependencies": [{"name": "pypdf", "version": "6.21.4", "vulns": []}]}
    assert run(tmp_path, "python", clean) == 0
    vulnerable = {"dependencies": [{"name": "pypdf", "version": "6.21.2", "vulns": [
        {"id": "PYSEC-2026-1", "fix_versions": ["6.21.4"], "aliases": []}]}]}
    assert run(tmp_path, "python", vulnerable) == 1


@pytest.mark.parametrize("report", [{}, {"vulnerabilities": []}, "texte", None])
def test_an_unreadable_report_fails_closed(tmp_path: Path, report: Any) -> None:
    assert run(tmp_path, "npm", report) == 2
    assert run(tmp_path, "python", report) == 2


def test_the_exception_file_is_complete_and_dated() -> None:
    exceptions = audit["load_exceptions"]()
    assert {key[1] for key in exceptions} == {
        "GHSA-xjj6-f33q-929c", "GHSA-2m5v-pch6-74hx", "GHSA-qrxm-fqhp-jwvm",
    }
    for item in exceptions.values():
        assert (ROOT / item["doc"]).is_file()
        assert dt.date.fromisoformat(item["expires"]) > dt.date.fromisoformat(item["reviewed"])


def test_the_weekly_audit_and_dependabot_are_configured() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/dependency-audit.yml").read_text(encoding="utf-8")
    )
    triggers = workflow[True] if True in workflow else workflow["on"]  # YAML reads "on" as True
    assert "schedule" in triggers and "workflow_dispatch" in triggers
    assert workflow["permissions"] == {"contents": "read"}
    text = (ROOT / ".github/workflows/dependency-audit.yml").read_text(encoding="utf-8")
    assert "check_dependency_audit.py npm" in text and "check_dependency_audit.py python" in text
    assert "pip-audit==" in text
    dependabot = yaml.safe_load((ROOT / ".github/dependabot.yml").read_text(encoding="utf-8"))
    ecosystems = {item["package-ecosystem"]: item for item in dependabot["updates"]}
    assert set(ecosystems) == {"github-actions", "npm", "pip"}
    assert ecosystems["npm"]["directory"] == "/config/npm-runtime"


def test_an_artifact_listed_by_several_locks_is_reported_once() -> None:
    vuln = {"id": "PYSEC-2026-3447", "fix_versions": ["83.0.0"], "aliases": []}
    report = {"dependencies": [
        {"name": "setuptools", "version": "80.9.0", "vulns": [vuln]},
        {"name": "setuptools", "version": "80.9.0", "vulns": [vuln]},
    ]}
    assert len(audit["python_advisories"](report)) == 1


def test_the_build_backend_no_longer_carries_the_audited_advisories() -> None:
    constraints = (ROOT / "config/python-build-constraints.txt").read_text(encoding="utf-8")
    assert "setuptools==84.2.1" in constraints and "wheel==" not in constraints
