"""Offline contract tests for four-dimensional, multi-turn teaching evaluation."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from clawfedora.pedagogy_eval import (
    PedagogyEvaluationError,
    compare,
    evaluate,
    load_suite,
    main,
)

ROOT = Path(__file__).resolve().parents[1]


def report(route: str = "cloud") -> dict[str, object]:
    suite = load_suite(ROOT)
    return {
        "route": route,
        "results": [
            {
                "scenario": scenario["id"],
                "reviewer": "evaluateur",
                "notes": "Observation humaine détaillée avec justification sur trois réponses.",
                "evidence": ["notes/test/" + scenario["id"]],
                "dialogue": [
                    {"user": question, "assistant": "Réponse réellement copiée pour la revue."}
                    for question in scenario["turns"]
                ],
                "scores": {"clarity": 5, "depth": 5, "interaction": 5, "accuracy": 5},
            }
            for scenario in suite["scenarios"]
        ],
    }


def test_suite_is_public_multiturn_and_complete() -> None:
    suite = load_suite(ROOT)
    assert len(suite["scenarios"]) == 4
    assert all(len(s["turns"]) >= 3 for s in suite["scenarios"])
    assert main(["--root", str(ROOT), "--plan"]) == 0


def test_human_report_has_four_dimensions_out_of_twenty() -> None:
    summary = evaluate(load_suite(ROOT), report())
    assert summary["global_out_of_20"] == 20
    assert summary["all_four_at_five"] is True
    assert summary["assessment"] == "HUMAN_DIALOGUE_REVIEW_NOT_RUNTIME_PROOF"
    assert summary["declared_cost_usd"] is None


@pytest.mark.parametrize("mistake", [
    "missing_case", "missing_turn", "changed_question", "short_answer",
    "missing_evidence", "bad_reviewer", "bad_notes", "missing_score",
    "float_score", "negative_score", "bool_score", "duplicate_case",
])
def test_incomplete_or_false_reports_are_rejected(mistake: str) -> None:
    payload = report()
    items = payload["results"]
    assert isinstance(items, list)
    if mistake == "missing_case":
        items.pop()
    elif mistake == "missing_turn":
        items[0]["dialogue"].pop()
    elif mistake == "changed_question":
        items[0]["dialogue"][1]["user"] = "question différente"
    elif mistake == "short_answer":
        items[0]["dialogue"][1]["assistant"] = "ok"
    elif mistake == "missing_evidence":
        items[0]["evidence"] = []
    elif mistake == "bad_reviewer":
        items[0]["reviewer"] = ""
    elif mistake == "bad_notes":
        items[0]["notes"] = "ok"
    elif mistake == "missing_score":
        del items[0]["scores"]["depth"]
    elif mistake == "float_score":
        items[0]["scores"]["depth"] = 4.5
    elif mistake == "negative_score":
        items[0]["scores"]["accuracy"] = -1
    elif mistake == "bool_score":
        items[0]["scores"]["clarity"] = True
    elif mistake == "duplicate_case":
        items[0]["scenario"] = items[1]["scenario"]
    with pytest.raises(PedagogyEvaluationError):
        evaluate(load_suite(ROOT), payload)


def test_evidence_based_comparison_and_cost_do_not_pretend_proof() -> None:
    a = report("cloud")
    b = deepcopy(a)
    b["route"] = "reference"
    b["results"][0]["scores"]["interaction"] = 2
    a["results"][0]["usage"] = {
        "input_tokens": 1234, "output_tokens": 800, "cost_usd": 0.003,
    }
    result = compare(load_suite(ROOT), a, b)
    assert result["global_delta_out_of_20"] < 0
    assert result["assessment"] == "HUMAN_COMPARISON_NOT_MODEL_BENCHMARK"
    assert evaluate(load_suite(ROOT), a)["declared_cost_usd"] == 0.003
    with pytest.raises(PedagogyEvaluationError):
        compare(load_suite(ROOT), a, a)


def test_usage_must_be_nonnegative_and_not_an_invented_measure() -> None:
    p = report()
    p["results"][0]["usage"] = {
        "input_tokens": 10, "output_tokens": 5, "cost_usd": -0.1
    }
    with pytest.raises(PedagogyEvaluationError):
        evaluate(load_suite(ROOT), p)
