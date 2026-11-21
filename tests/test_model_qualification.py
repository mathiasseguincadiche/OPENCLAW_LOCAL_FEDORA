"""Model comparison is evidence-gated and cannot uninstall local inference."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from clawfedora.model_qualification import MODELS, QualificationRefused, evaluate


def report() -> dict[str, Any]:
    observations = {}
    for model in MODELS:
        observations[model] = [
            {
                "case_id": f"case-{index}",
                "accepted": True,
                "scores": {"technical": 3, "clarity": 3, "proof": 3, "safety": 4},
                "elapsed_ms": 1000 if model == MODELS[0] else 1200,
                "cost_usd": 0 if model == MODELS[0] else 0.01,
            }
            for index in range(1, 5)
        ]
    return {
        "classification": "synthetic_public",
        "commit": "a" * 40,
        "suite_sha256": "b" * 64,
        "models": observations,
    }


def test_local_kept_only_as_a_candidate_on_equal_measured_quality() -> None:
    summary = evaluate(report())
    assert summary["advice"] == "local_possibly_useful"
    assert summary["local_competitive_cases"] == [f"case-{i}" for i in range(1, 5)]
    assert summary["summary"][MODELS[0]]["cost_usd_total"] == 0
    assert "Aucun modèle n'est désinstallé" in summary["limitations"]


def test_locally_poor_results_can_only_recommend_human_review() -> None:
    payload = report()
    for result in payload["models"][MODELS[0]]:
        result["accepted"] = False
        result["scores"]["technical"] = 0
    assert evaluate(payload)["advice"] == "consider_disabling_local_after_human_review"


@pytest.mark.parametrize("mutation", [
    lambda p: p.update(classification="internal"),
    lambda p: p["models"].pop(MODELS[2]),
    lambda p: p["models"][MODELS[1]].pop(),
    lambda p: p["models"][MODELS[1]][0].update(case_id="other"),
    lambda p: p["models"][MODELS[0]][0].update(cost_usd=0.01),
    lambda p: p["models"][MODELS[1]][0].update(cost_usd=float("nan")),
    lambda p: p["models"][MODELS[1]][0].update(accepted="yes"),
    lambda p: p["models"][MODELS[1]][0]["scores"].update(technical=5),
    lambda p: p.update(suite_sha256="invalid"),
])
def test_incomplete_or_incomparable_measurements_fail_closed(mutation: Any) -> None:
    payload = deepcopy(report())
    mutation(payload)
    with pytest.raises(QualificationRefused):
        evaluate(payload)
