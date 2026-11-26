"""Replay inference profiles and test candidate role guidance and mock tool boundaries."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from clawfedora import excellence_finalists as ef
from clawfedora import excellence_role_tools as rt

ROOT = Path(__file__).resolve().parents[1]


def test_archived_profiles():
    suite = ef.load(ROOT)
    cases = {case["id"]: case for case in suite["cases"]}
    counts = {}
    paths = sorted((ROOT / "tests/fixtures").glob("boreal_45790472002_*.json"))
    assert len(paths) == 14
    for path in paths:
        r = json.loads(path.read_text(encoding="utf-8"))
        assert r["commit"] == "1f186d1d7dab7d1966b628aadadb9d460f2ce373"
        assert r["suite_sha256"] == ef.mc._digest(suite)
        assert r["model"]["digest"].removeprefix("sha256:") == ef.DIGESTS[r["model"]["alias"]]
        assert r["classification"] == "synthetic_public"
        assert r["native_excellence_certified"] is False
        assert r["production_routing_changed"] is False
        key = (r["model"]["alias"], r["profile"])
        count = counts.setdefault(key, [0, 0, 0])
        assert len(r["results"]) == r["planned"]
        for row in r["results"]:
            for stage in ("initial", "correction"):
                if stage in row:
                    attempt = row[stage]
                    assert ef.validate(cases[row["id"]], attempt["response"]) == (
                        attempt["validation"]
                    )
            count[["KEEP_INITIAL", "CORRECTED_FACT_CONTRACT_ONLY",
                   "BLOCK_UNRESOLVED"].index(row["selection"])] += 1
    assert counts == {
        ("qwen", "direct"): [7, 1, 6],
        ("ornith", "direct"): [11, 0, 3],
        ("gemma", "direct"): [8, 0, 6],
        ("gemma", "gemma-think-probe"): [0, 0, 2],
    }


def test_guidance_and_workflow():
    assert set(rt.ROLE_GUIDANCE) == set(ef.mc.ROLES) == set(rt.FIXTURES)
    assert all(rt.COMMON in rt.guidance(role) for role in ef.mc.ROLES)
    for alias in ef.MODELS:
        assert ef.select_profile(alias, "coached") == ef.select_profile(alias, "direct")
    wf = yaml.load(
        (ROOT / ".github/workflows/excellence-role-coaching.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    matrix = wf["jobs"]["compare"]["strategy"]["matrix"]["include"]
    assert len(matrix) == 12
    assert {(r["model"], int(r["seed"]), r["shard"], r["profile"]) for r in matrix} == {
        (m, s, h, "coached") for m in ef.MODELS for s in ef.SEEDS for h in ef.SHARDS
    }


def _reply(model, content, calls):
    return {
        "model": model, "done": True, "done_reason": "stop",
        "message": {"content": content, "tool_calls": calls},
        **dict.fromkeys(("total_duration", "load_duration", "prompt_eval_count",
                        "prompt_eval_duration", "eval_count", "eval_duration"), 1),
    }


@pytest.mark.parametrize("role", ef.mc.ROLES)
def test_probe_only_returns_fixture(role, monkeypatch):
    model = ef.MODELS["ornith"]
    name, key, status = rt.FIXTURES[role]
    seen = []

    def chat(payload, *, timeout):
        assert timeout == 1200
        seen.append(payload)
        if len(seen) == 1:
            return _reply(model, "", [{"function": {"name": name, "arguments": {"key": key}}}])
        receipt = json.loads(payload["messages"][-1]["content"])
        assert receipt == {"key": key, "status": status, "scope": "synthetic"}
        return _reply(model, status, [])

    monkeypatch.setattr(rt.mc, "_chat", chat)
    assert rt.probe(model, role, ef.OPTIONS, 1200)["state"] == "PASS_FIXTURE_ONLY"
    assert len(seen) == 2


@pytest.mark.parametrize("wrong_name, wrong_key", [("fixture_mutation", "learning-card"),
                                                  ("fixture_learning", "other")])
def test_probe_rejects_unauthorized_calls(wrong_name, wrong_key, monkeypatch):
    model = ef.MODELS["ornith"]
    seen = []

    def chat(payload, *, timeout):
        seen.append(payload)
        return _reply(model, "", [{"function": {"name": wrong_name,
                                               "arguments": {"key": wrong_key}}}])

    monkeypatch.setattr(rt.mc, "_chat", chat)
    assert rt.probe(model, "chef-operations", ef.OPTIONS, 1200)["state"] == "FAIL_TOOL_CALL"
    assert len(seen) == 1


def test_coached_run_keeps_facts_and_probes_separate(tmp_path, monkeypatch):
    monkeypatch.setattr(ef.es, "identity", lambda *_: {"digest": ef.DIGESTS["ornith"]})
    monkeypatch.setattr(ef, "capabilities", lambda _: ["completion", "tools"])
    seen = []

    def ask(model, case, prompt, seed, think, *, profile):
        assert rt.guidance(case["role"]) in prompt[0]["content"]
        assert think is False
        seen.append(case["role"])
        value = {**case["fields"], "reason": "Justification concise.", "executed": False}
        response = {"content": json.dumps(value), "done_reason": "stop", "tool_calls": []}
        return {"response": response, "validation": ef.validate(case, response)}

    monkeypatch.setattr(ef, "ask", ask)
    monkeypatch.setattr(rt, "probe", lambda *_: {"state": "FAIL_TOOL_CALL"})
    r = ef.run(ROOT, "ornith", "a" * 40, tmp_path / "out.json", 42, "review",
               profile="coached")
    assert len(seen) == 3
    assert r["summary"]["initial_pass"] == 3
    assert [p["state"] for p in r["role_tool_probes"]] == ["FAIL_TOOL_CALL"] * 3
    assert r["native_excellence_certified"] is False
