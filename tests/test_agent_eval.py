"""Evaluation records never imply an executed test or a cloud measurement."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from clawfedora.agent_eval import EvaluationError, compare_reports, evaluate_report, load_suite

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


def test_paired_comparison_keeps_scoring_honest() -> None:
    local = _valid_report()
    cloud = deepcopy(local)
    cloud["route"] = "cloud"
    cloud["results"][0]["scores"]["clarity"] = 2
    result = compare_reports(load_suite(ROOT), local, cloud)
    assert result["scenarios"] == 7
    assert result["per_scenario_deltas"]["mentor-systemd"]["clarity"] == -2
    assert result["delta_cloud_minus_local"] < 0
    assert result["assessment"] == "HUMAN_SCORE_COMPARISON_NOT_RUNTIME_QUALIFICATION"
    assert "ni supériorité démontrée" in result["warning"]


def test_paired_comparison_rejects_swapped_or_incomplete_records() -> None:
    local = _valid_report()
    cloud = deepcopy(local)
    cloud["route"] = "cloud"
    with pytest.raises(EvaluationError, match="rapport local"):
        compare_reports(load_suite(ROOT), cloud, local)
    cloud["results"].pop()
    with pytest.raises(EvaluationError, match="résultat humain"):
        compare_reports(load_suite(ROOT), local, cloud)


def test_compare_cli_stays_offline_and_reads_two_local_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    from clawfedora.agent_eval import main
    local = _valid_report()
    cloud = deepcopy(local)
    cloud["route"] = "cloud"
    first, second = tmp_path / "qwen.json", tmp_path / "deepseek.json"
    first.write_text(json.dumps(local), encoding="utf-8")
    second.write_text(json.dumps(cloud), encoding="utf-8")
    assert main(["--root", str(ROOT), "--compare", str(first), str(second)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["assessment"] == "HUMAN_SCORE_COMPARISON_NOT_RUNTIME_QUALIFICATION"
    assert output["delta_cloud_minus_local"] == 0
