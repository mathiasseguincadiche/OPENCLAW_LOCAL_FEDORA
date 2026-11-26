"""Offline tests: fake inference only, no downloads or external operations."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from clawfedora import excellence_screening as es

ROOT = Path(__file__).resolve().parents[1]


def _answer(case, **updates):
    fields = {**case["fields"], "reason": "Justification synthétique de test.", "executed": False}
    fields.update(updates)
    return {"content": json.dumps(fields), "done_reason": "stop"}


def _row(case, **updates):
    reply = _answer(case, **updates)
    return {"response": reply, "validation": es.tm.validate(case, reply)}


def test_seven_roles_and_four_exact_candidates():
    suite = es.load(ROOT)
    assert tuple(case["role"] for case in suite["cases"]) == es.mc.ROLES
    assert set(es.CANDIDATES) == {"qwen", "ornith", "gemma", "lfm"}
    assert sum(es.CRITERIA.values()) == 100
    for case in suite["cases"]:
        assert _row(case)["validation"]["state"] == "PASS_FACT_CONTRACT_ONLY"
        prompt = es.messages(ROOT, case)
        assert prompt[-1]["content"] == case["question"]
        assert "aucun outil réel" in prompt[0]["content"]


def test_promotion_protects_passing_draft():
    case = es.load(ROOT)["cases"][0]
    correct = _row(case)
    wrong = _row(case, ssh_proven=True)
    worse = _row(case, award_l2=True)
    assert es.promotion(correct, wrong) == "KEEP_INITIAL"
    assert es.promotion(wrong, correct) == "CORRECTED_FACT_CONTRACT_ONLY"
    assert es.promotion(wrong, worse) == "BLOCK_UNRESOLVED"
    assert es.promotion(wrong, wrong) == "BLOCK_UNRESOLVED"


def test_screening_skips_unnecessary_revisions_and_retains_evidence(tmp_path, monkeypatch):
    cases = es.load(ROOT)["cases"]
    monkeypatch.setattr(es, "identity", lambda *_: {"digest": "a" * 64})
    seen = []

    def ask(model, case, prompt):
        seen.append((model, case["id"], len(prompt)))
        if case["id"] == "mentor" and len(prompt) == 2:
            return _row(case, ssh_proven=True)
        if case["id"] == "security":
            return _row(case, disable_selinux=True)
        return _row(case)

    monkeypatch.setattr(es, "ask", ask)
    monkeypatch.setattr(es.mc, "_tool_probe", lambda _: {"state": "PASS_FIXTURE_ONLY"})
    monkeypatch.setattr(es.mc, "_code_probe", lambda _: {"state": "PASS_STATIC_ONLY"})
    out = tmp_path / "report.json"
    result = es.run(ROOT, "gemma", "a" * 40, out)
    assert len(cases) == 7
    assert len(seen) == 9
    assert result["summary"] == {"roles": 7, "initial_pass": 5, "corrected": 1, "blocked": 1}
    assert result["results"][0]["selection"] == "CORRECTED_FACT_CONTRACT_ONLY"
    assert result["results"][4]["selection"] == "BLOCK_UNRESOLVED"
    assert result["native_excellence_certified"] is False
    assert result["production_routing_changed"] is False
    assert json.loads(out.read_text()) == result


def test_review_gate_requires_bound_human_assessment():
    case = es.load(ROOT)["cases"][0]
    row = {"selection": "KEEP_INITIAL", "initial": _row(case)}
    review = {
        "row_sha256": es.mc._digest(row), "scores": dict.fromkeys(es.CRITERIA, 4),
        "blockers": [], "notes": "Notes humaines de test liées au livrable synthétique.",
    }
    result = es.review_score(row, review)
    assert result["declared_score"] == 100
    assert result["assessment"] == "SCREENING_EXCELLENCE_CANDIDATE"
    assert result["native_excellence_certified"] is False
    review["blockers"] = ["fabricated_evidence"]
    assert es.review_score(row, review)["assessment"] == "BLOCKED"
    review["row_sha256"] = "a" * 64
    with pytest.raises(ValueError, match="revue humaine"):
        es.review_score(row, review)


def test_factual_failure_cannot_be_overridden_by_a_good_score():
    case = es.load(ROOT)["cases"][0]
    row = {"selection": "BLOCK_UNRESOLVED", "initial": _row(case, ssh_proven=True)}
    review = {
        "row_sha256": es.mc._digest(row), "scores": dict.fromkeys(es.CRITERIA, 4),
        "blockers": [], "notes": "Notes humaines de test liées au livrable synthétique.",
    }
    assert es.review_score(row, review)["assessment"] == "BLOCKED"


def test_identity_refuses_changed_baseline(tmp_path, monkeypatch):
    def request(url):
        if url.endswith("/version"):
            return {"version": "0.40.6"}
        return {"models": [{"name": es.CANDIDATES["qwen"], "digest": "a" * 64,
                            "size": 6_550_000_000, "details": {"quantization_level": "Q4_K_M"}}]}

    monkeypatch.setattr(es.ollama_api, "request_json", request)
    with pytest.raises(ValueError, match="digest"):
        es.identity(ROOT, "qwen")
    assert not list(tmp_path.iterdir())


def test_workflow_keeps_candidates_outside_production_catalog():
    import yaml

    workflow = yaml.load(
        (ROOT / ".github/workflows/excellence-model-screening.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    job = workflow["jobs"]["compare"]
    assert job["strategy"]["matrix"]["model"] == list(es.CANDIDATES)
    assert job["runs-on"] == "ubuntu-latest"
    assert all("runner." not in value for value in job["env"].values())
    catalog = yaml.safe_load((ROOT / "config/model_catalog.yaml").read_text())
    assert set(catalog["models"]) == {"qwen-max", "ornith-code"}
