"""Replay Quartz and verify candidate-only qualification evidence."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from clawfedora import excellence_chain as ec
from clawfedora import excellence_finalists as ef
from clawfedora import local_model_comparison as mc

ROOT = Path(__file__).resolve().parents[1]


def test_quartz_archive_and_review():
    suite = ec.load(ROOT)
    review = json.loads(
        (ROOT / "config/evals/excellence_quartz_review.json").read_text(encoding="utf-8")
    )
    assert review["kind"] == "assistant_qualitative_review_not_operator_acceptance"
    assert review["source_run"] == 45912168133
    assert review["native_excellence_certified"] is False
    assert len(review["reports"]) == 6
    seen = set()
    counts = {}
    for item in review["reports"]:
        path = ROOT / item["path"]
        report = json.loads(path.read_text(encoding="utf-8"))
        alias, seed = report["model"]["alias"], report["seed"]
        assert (alias, seed) == (item["model"], item["seed"])
        assert (alias, seed) not in seen
        seen.add((alias, seed))
        assert report["commit"] == "8f7f19d7a329389abb544d556148b619e80ff91b"
        assert report["suite_sha256"] == mc._digest(suite)
        assert report["model"]["digest"].removeprefix("sha256:") == ef.DIGESTS[alias]
        assert report["classification"] == "synthetic_public"
        assert report["native_excellence_certified"] is False
        assert report["production_routing_changed"] is False
        assert len(report["results"]) == len(item["rows"]) == 7
        assert ec.gate(suite["cases"], report["results"]) == report["gate"]
        assert report["gate"]["publication_authorized"] is False
        assert report["gate"]["release_decision"] == "HOLD"
        assert all(i.startswith("blocked:") for i in report["gate"]["issues"])
        for case, row, note in zip(suite["cases"], report["results"], item["rows"], strict=True):
            attempt = row["attempt"]
            assert ef.validate(case, attempt["response"]) == attempt["validation"]
            assert attempt["validation"]["correct"] == 4
            assert set(attempt["validation"]["issues"]) <= {"reason_length"}
            assert note["response_sha256"] == row["response_sha256"]
            assert note["response_sha256"] == mc._digest(attempt["response"])
            assert note["id"] == row["id"] and note["role"] == row["role"]
            assert note["status"] == "REVIEW_REQUIRED" and len(note["notes"]) >= 20
            counts[alias] = counts.get(alias, 0) + (
                attempt["validation"]["state"] == "PASS_FACT_CONTRACT_ONLY"
            )
    assert seen == {(a, s) for a in ef.MODELS for s in ef.SEEDS}
    assert counts == {"qwen": 14, "ornith": 11, "gemma": 12}


def test_native_candidates_and_reference_fleet():
    data = json.loads(
        (ROOT / "config/evals/excellence_native_candidates.json").read_text(encoding="utf-8")
    )
    assert data["status"] == "REFERENCE_SELECTED_NOT_NATIVE_QUALIFIED"
    assert data["production_routing_changed"] is True
    assert data["native_excellence_certified"] is False
    assert data["source_run"] == 45912168133
    assert data["min_repetitions_per_case"] >= 3
    assert data["min_distinct_cases_per_role"] >= 2
    assert data["min_review_score"] == 90
    assert data["critical_blockers_allowed"] == 0
    assert set(data["models"]) == set(ef.MODELS)
    for alias, model in data["models"].items():
        assert model["runtime_id"] == ef.MODELS[alias]
        assert model["digest"] == ef.DIGESTS[alias]
        assert model["thinking"] is False
    assert tuple(r["role"] for r in data["roles"]) == mc.ROLES
    for role in data["roles"]:
        assert role["primary"] in ef.MODELS and role["alternative"] in ef.MODELS
        assert role["primary"] != role["alternative"]
        assert role["status"] == "NOT_RUN"
        assert len(role["rationale"]) >= 20 and len(role["native_test"]) >= 20
    catalog = yaml.safe_load((ROOT / "config/model_catalog.yaml").read_text(encoding="utf-8"))
    assert set(catalog["models"]) == {"qwen-max", "ornith-code", "gemma-expert"}
    assert catalog["fleet_policy"]["exact_required_model_count"] == 3
    assert catalog["fleet_policy"]["local_only"] is True
