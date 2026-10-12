"""Evaluation records never imply an executed test or a cloud measurement."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from clawfedora.agent_eval import EvaluationError, evaluate_report, load_suite

ROOT = Path(__file__).resolve().parents[1]


def _valid_report() -> dict[str, object]:
    cases = load_suite(ROOT)["scenarios"]
    return {
        "route": "local",
        "results": [
            {
                "scenario": case["id"],
                "reviewer": "évaluateur-humain",
                "notes": "Constats techniques vérifiés et limites précisées à la main.",
                "evidence": ["notes-locales/cas/" + case["id"]],
                "scores": {"technical": 3, "clarity": 4, "proof": 3, "safety": 4},
            }
            for case in cases
        ],
    }


def test_suite_matches_seven_actual_roles() -> None:
    suite = load_suite(ROOT)
    assert len(suite["scenarios"]) == 7
    assert len({case["role"] for case in suite["scenarios"]}) == 7
    assert suite["data_classification"] == "synthetic_public"


def test_grade_reports_mean_without_claiming_runtime_success() -> None:
    result = evaluate_report(load_suite(ROOT), _valid_report())
    assert result["route"] == "local"
    assert result["scenarios"] == 7
    assert result["mean_out_of_4"] == 3.5
    assert result["assessment"] == "HUMAN_REVIEWED_UNVERIFIED_BY_RUNTIME"
    assert "ni l'exécution" in result["warning"]


def test_synthetic_suite_can_be_graded_for_cloud_with_same_rubric() -> None:
    report = _valid_report()
    report["route"] = "cloud"
    assert evaluate_report(load_suite(ROOT), report)["route"] == "cloud"


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ("missing_result", "résultat humain"),
        ("duplicate", "répété"),
        ("missing_evidence", "références"),
        ("missing_reviewer", "évaluateur"),
        ("empty_notes", "explication"),
        ("fake_float", "entier"),
        ("bool_score", "entier"),
        ("invalid_route", "route"),
        ("invalid_dimension", "grille"),
    ],
)
def test_reject_incomplete_or_misleading_reports(change: str, match: str) -> None:
    report = deepcopy(_valid_report())
    results = report["results"]
    assert isinstance(results, list)
    if change == "missing_result":
        results.pop()
    elif change == "duplicate":
        results[1]["scenario"] = results[0]["scenario"]
    elif change == "missing_evidence":
        results[0]["evidence"] = []
    elif change == "missing_reviewer":
        results[0]["reviewer"] = ""
    elif change == "empty_notes":
        results[0]["notes"] = "ok"
    elif change == "fake_float":
        results[0]["scores"]["proof"] = 3.5
    elif change == "bool_score":
        results[0]["scores"]["safety"] = True
    elif change == "invalid_route":
        report["route"] = "auto"
    elif change == "invalid_dimension":
        del results[0]["scores"]["proof"]
    with pytest.raises(EvaluationError, match=match):
        evaluate_report(load_suite(ROOT), report)
