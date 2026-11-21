"""Validate the InfraOps reference suite without executing any model."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from clawfedora.agent_eval import EvaluationError, load_suite, main, suite_digest
from clawfedora.agents import validate_agent_assets

ROOT = Path(__file__).resolve().parents[1]


def test_reference_suite_covers_all_roles_and_realistic_infraops_boundaries() -> None:
    suite = load_suite(ROOT, "infraops")
    standard = load_suite(ROOT)
    assert suite["data_classification"] == "synthetic_public"
    assert suite_digest(suite) != suite_digest(standard)
    scenarios = suite["scenarios"]
    assert len(scenarios) == len(standard["scenarios"]) == 7
    assert len({case["role"] for case in scenarios}) == 7
    all_text = " ".join(case["prompt"] for case in scenarios).lower()
    for subject in ("libvirt", "ansible", "docker", "k3s", "postgresql", "selinux", "firewalld"):
        assert subject in all_text
    assert "copie d'essai" in all_text
    assert "ne pas" in all_text


def test_cli_plan_can_select_infraops_without_model_calls(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--root", str(ROOT), "--suite", "infraops", "--plan"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "PLAN_ONLY_NO_MODEL_CALLS"
    assert payload["suite"] == "qualification-infraops-laboratoire"
    assert len(payload["suite_sha256"]) == 64
    assert len(payload["scenarios"]) == 7


def test_unknown_suite_is_refused_without_arbitrary_file_access() -> None:
    with pytest.raises(EvaluationError, match="Suite inconnue"):
        load_suite(ROOT, "../../private")


def test_prompts_still_fit_bootstrap_limits() -> None:
    assert validate_agent_assets(ROOT) == ()
