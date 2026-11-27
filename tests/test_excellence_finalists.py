"""Offline tests for the independent finalist trials."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from clawfedora import excellence_finalists as ef

ROOT = Path(__file__).resolve().parents[1]


def _answer(case, **updates):
    value = {**case["fields"], "reason": "Justification concise.", "executed": False}
    value.update(updates)
    return {"content": json.dumps(value), "done_reason": "stop", "tool_calls": []}


def test_precise_diagnostics_preserve_correct_facts():
    case = ef.load(ROOT)["cases"][3]
    response = _answer(case, reason="x" * 1201)
    result = ef.validate(case, response)
    assert result["issues"] == ["reason_length"]
    assert result["correct"] == 4
    assert result["state"] == "BLOCKED"
    result = ef.validate(case, _answer(case, plan_error=True, executed=True))
    assert result["issues"] == ["execution_claim"]
    assert result["failed_fields"] == ["plan_error"]
    assert result["correct"] == 3
    response = _answer(case, plan_error="false")
    response["done_reason"] = "length"
    assert ef.validate(case, response)["issues"] == ["type:plan_error", "completion"]
    assert ef.validate(case, {"content": "{", "done_reason": "stop"})["issues"] == [
        "invalid_json_object"
    ]


def test_no_automatic_semantic_certification():
    for case in ef.load(ROOT)["cases"]:
        result = ef.validate(case, _answer(case, reason="Texte à relire indépendamment."))
        assert result["state"] == "PASS_FACT_CONTRACT_ONLY"
        assert result["semantic_review"] == "REQUIRED"


@pytest.mark.parametrize("shard, count", [("core", 4), ("review", 3)])
def test_independent_trials_and_bounded_correction(tmp_path, monkeypatch, shard, count):
    monkeypatch.setattr(ef.es, "identity", lambda *_: {"digest": ef.DIGESTS["gemma"]})
    monkeypatch.setattr(ef, "capabilities", lambda _: ["completion", "thinking"])
    seen = []

    def ask(model, case, prompt, seed, think):
        seen.append((case["id"], len(prompt), seed, think))
        response = _answer(case, reason="x" * 1201) if len(seen) == 1 else _answer(case)
        return {"response": response, "validation": ef.validate(case, response)}

    monkeypatch.setattr(ef, "ask", ask)
    output = tmp_path / "report.json"
    result = ef.run(ROOT, "gemma", "a" * 40, output, 73, shard)
    assert len(seen) == count + 1
    assert all(x[2:] == (73, True) for x in seen)
    assert seen[0][1] == 2 and seen[1][1] == 4
    assert all(x[1] == 2 for x in seen[2:])
    assert result["summary"] == {"initial_pass": count - 1, "corrected": 1, "blocked": 0}
    assert result["native_excellence_certified"] is False
    assert json.loads(output.read_text()) == result


def test_digest_mismatch_fails_before_inference(tmp_path, monkeypatch):
    monkeypatch.setattr(ef.es, "identity", lambda *_: {"digest": "a" * 64})
    with pytest.raises(ValueError, match="digest"):
        ef.run(ROOT, "gemma", "a" * 40, tmp_path / "report.json", 42, "core")
    assert not list(tmp_path.iterdir())


def test_matrix_and_catalog_unchanged():
    workflow = yaml.load(
        (ROOT / ".github/workflows/excellence-finalists.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    job = workflow["jobs"]["compare"]
    matrix = job["strategy"]["matrix"]
    assert matrix["model"] == list(ef.MODELS)
    assert tuple(map(int, matrix["seed"])) == ef.SEEDS
    assert tuple(matrix["shard"]) == ef.SHARDS
    assert all("runner." not in value for value in job["env"].values())
    assert job["runs-on"] == "ubuntu-latest"
    catalog = yaml.safe_load((ROOT / "config/model_catalog.yaml").read_text())
    assert set(catalog["models"]) == {"qwen-max", "ornith-code", "gemma-expert"}
