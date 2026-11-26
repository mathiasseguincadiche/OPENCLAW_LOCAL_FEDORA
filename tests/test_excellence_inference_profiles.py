"""Offline checks of profile selection and archived public Boréal reports."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from clawfedora import excellence_finalists as ef

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("alias", sorted(ef.MODELS))
def test_archived_baseline(alias):
    suite = ef.load(ROOT)
    cases = {case["id"]: case for case in suite["cases"]}
    counts = [0, 0, 0, 0]
    for seed in ef.SEEDS:
        for shard in ef.SHARDS:
            path = ROOT / f"tests/fixtures/boreal_45781161395_{alias}_{seed}_{shard}.json"
            report = json.loads(path.read_text(encoding="utf-8"))
            assert report["commit"] == "eaa704b09fce7915c078e56aea1efa2d14ce56b7"
            assert report["suite_sha256"] == ef.mc._digest(suite)
            assert report["model"]["digest"].removeprefix("sha256:") == ef.DIGESTS[alias]
            assert report["options"]["seed"] == seed and report["shard"] == shard
            assert report["classification"] == "synthetic_public"
            assert report["native_excellence_certified"] is False
            assert report["production_routing_changed"] is False
            counts[3] += report["planned"] - len(report["results"])
            for row in report["results"]:
                for name in ("initial", "correction"):
                    if name in row:
                        attempt = row[name]
                        assert ef.validate(cases[row["id"]], attempt["response"]) == (
                            attempt["validation"]
                        )
                counts[["KEEP_INITIAL", "CORRECTED_FACT_CONTRACT_ONLY",
                        "BLOCK_UNRESOLVED"].index(row["selection"])] += 1
            if alias == "gemma":
                assert report["error"]["type"] == "TimeoutError"
    assert counts == {
        "qwen": [7, 3, 4, 0],
        "ornith": [3, 5, 6, 0],
        "gemma": [0, 0, 0, 14],
    }[alias]


def test_profiles_are_explicit_and_bounded():
    assert ef.select_profile("qwen", "baseline") is None
    assert ef.select_profile("ornith", "direct") == ef.Profile(False, 1200, 1200)
    assert ef.select_profile("gemma", "gemma-think-probe") == ef.Profile(True, 900, 1500)
    with pytest.raises(ValueError, match="réservée"):
        ef.select_profile("qwen", "gemma-think-probe")
    with pytest.raises(ValueError, match="inconnu"):
        ef.select_profile("lfm", "direct")


@pytest.mark.parametrize("name, think, planned", [("direct", False, 4),
                                                ("gemma-think-probe", True, 1)])
def test_profile_run_and_report(tmp_path, monkeypatch, name, think, planned):
    monkeypatch.setattr(ef.es, "identity", lambda *_: {"digest": ef.DIGESTS["gemma"]})
    monkeypatch.setattr(ef, "capabilities", lambda _: ["completion", "thinking"])
    seen = []

    def ask(model, case, prompt, seed, active, *, profile):
        seen.append((seed, active, profile))
        value = {**case["fields"], "reason": "Justification concise.", "executed": False}
        response = {"content": json.dumps(value), "done_reason": "stop", "tool_calls": []}
        return {"response": response, "validation": ef.validate(case, response)}

    monkeypatch.setattr(ef, "ask", ask)
    report = ef.run(ROOT, "gemma", "a" * 40, tmp_path / "out.json", 42, "core",
                    profile=name)
    assert len(seen) == planned
    assert all(x == (42, think, ef.Profile(think, 900, 1500)) for x in seen)
    assert report["profile"] == name and report["think_requested"] is think
    assert report["options"]["num_predict"] == 900
    assert report["socket_timeout_seconds"] == 1500
    assert report["summary"]["initial_pass"] == planned


def test_profile_chat_parameters(monkeypatch):
    case = ef.load(ROOT)["cases"][0]
    value = {**case["fields"], "reason": "Justification concise.", "executed": False}

    def chat(payload, *, timeout):
        assert timeout == 1500
        assert payload["think"] is False
        assert payload["options"]["num_predict"] == 900
        return {
            "model": ef.MODELS["gemma"], "done": True, "done_reason": "stop",
            "message": {"content": json.dumps(value)},
            **dict.fromkeys(("total_duration", "load_duration", "prompt_eval_count",
                            "prompt_eval_duration", "eval_count", "eval_duration"), 1),
        }

    monkeypatch.setattr(ef.mc, "_chat", chat)
    result = ef.ask(ef.MODELS["gemma"], case, [], 42, False, profile=ef.DIRECT["gemma"])
    assert result["validation"]["state"] == "PASS_FACT_CONTRACT_ONLY"
    assert result["thinking_observed"] is False


def test_profile_matrix():
    workflow = yaml.load(
        (ROOT / ".github/workflows/excellence-inference-profiles.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    matrix = workflow["jobs"]["compare"]["strategy"]["matrix"]["include"]
    direct = {(x["model"], int(x["seed"]), x["shard"]) for x in matrix
              if x["profile"] == "direct"}
    assert direct == {(m, s, h) for m in ef.MODELS for s in ef.SEEDS for h in ef.SHARDS}
    probes = [x for x in matrix if x["profile"] == "gemma-think-probe"]
    assert len(matrix) == 14 and len(probes) == 2
    assert {(x["model"], x["seed"], x["shard"]) for x in probes} == {
        ("gemma", "42", "core"), ("gemma", "42", "review"),
    }
