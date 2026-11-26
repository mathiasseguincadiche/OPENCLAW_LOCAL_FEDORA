"""Replay historic calls and verify held-out case isolation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from clawfedora import excellence_finalists as ef
from clawfedora import excellence_role_tools as rt

ROOT = Path(__file__).resolve().parents[1]


def test_archive_and_first_call_replay():
    suite = ef.load(ROOT)
    cases = {case["id"]: case for case in suite["cases"]}
    counts = {}
    calls = {}
    paths = sorted((ROOT / "tests/fixtures").glob("boreal_45893686907_*.json"))
    assert len(paths) == 12
    for path in paths:
        r = json.loads(path.read_text(encoding="utf-8"))
        assert r["commit"] == "c8caccea4769efd699e39c1ee9b2b72ef7530819"
        assert r["suite_sha256"] == ef.mc._digest(suite)
        alias = r["model"]["alias"]
        assert r["model"]["digest"].removeprefix("sha256:") == ef.DIGESTS[alias]
        assert r["profile"] == "coached"
        assert r["classification"] == "synthetic_public"
        assert r["native_excellence_certified"] is False
        count = counts.setdefault(alias, [0, 0, 0])
        for row in r["results"]:
            for stage in ("initial", "correction"):
                if stage in row:
                    attempt = row[stage]
                    assert ef.validate(cases[row["id"]], attempt["response"]) == (
                        attempt["validation"]
                    )
            count[["KEEP_INITIAL", "CORRECTED_FACT_CONTRACT_ONLY",
                   "BLOCK_UNRESOLVED"].index(row["selection"])] += 1
        for probe in r["role_tool_probes"]:
            assert probe["state"] == "FAIL_TOOL_CALL"
            assert "second" not in probe
            name, key, _ = rt.FIXTURES[probe["role"]]
            calls.setdefault(alias, []).append(
                rt.valid_call(probe["first"]["tool_calls"], name, key)
            )
    assert counts == {"qwen": [8, 2, 4], "ornith": [10, 0, 4], "gemma": [9, 0, 5]}
    assert {alias: (sum(v), len(v)) for alias, v in calls.items()} == {
        "qwen": (4, 7), "ornith": (7, 7), "gemma": (7, 7),
    }


@pytest.mark.parametrize("index", [1, -1, True, "0", None])
def test_call_metadata_is_not_an_authorization(index):
    call = {"function": {"name": "fixture_learning", "arguments": {"key": "x"},
                         "index": index}}
    assert not rt.valid_call([call], "fixture_learning", "x")


def test_call_exact_arguments_and_index():
    good = {"id": "synthetic", "function": {"name": "fixture_learning",
                                           "arguments": {"key": "x"}, "index": 0}}
    assert rt.valid_call([good], "fixture_learning", "x")
    assert not rt.valid_call([good, good], "fixture_learning", "x")
    good["function"]["arguments"]["extra"] = "y"
    assert not rt.valid_call([good], "fixture_learning", "x")


def test_holdout_matrix_and_no_answer_leak():
    old = ef.load(ROOT)
    new = ef.load(ROOT, holdout=True)
    assert not {c["id"] for c in old["cases"]} & {c["id"] for c in new["cases"]}
    for case in new["cases"]:
        prompt = ef.messages(ROOT, case)
        assert prompt[-1]["content"] == case["question"]
        assert case["review"] not in prompt[-1]["content"]
    wf = yaml.load(
        (ROOT / ".github/workflows/excellence-holdout.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    matrix = wf["jobs"]["compare"]["strategy"]["matrix"]["include"]
    assert len(matrix) == 12
    assert {(r["model"], int(r["seed"]), r["shard"], r["profile"]) for r in matrix} == {
        (m, 42, h, p) for m in ef.MODELS for h in ef.SHARDS
        for p in ("holdout-direct", "holdout-coached")
    }


@pytest.mark.parametrize("profile", ["holdout-direct", "holdout-coached"])
def test_holdout_run_selects_new_suite(tmp_path, monkeypatch, profile):
    monkeypatch.setattr(ef.es, "identity", lambda *_: {"digest": ef.DIGESTS["ornith"]})
    monkeypatch.setattr(ef, "capabilities", lambda _: ["completion", "tools"])
    seen = []

    def ask(model, case, prompt, seed, think, *, profile):
        assert case["id"].startswith("silex-")
        assert case["review"] not in prompt[-1]["content"]
        seen.append(case["id"])
        value = {**case["fields"], "reason": "Justification concise.", "executed": False}
        response = {"content": json.dumps(value), "done_reason": "stop", "tool_calls": []}
        return {"response": response, "validation": ef.validate(case, response)}

    monkeypatch.setattr(ef, "ask", ask)
    monkeypatch.setattr(rt, "probe", lambda *_: {"state": "PASS_FIXTURE_ONLY"})
    r = ef.run(ROOT, "ornith", "a" * 40, tmp_path / "out.json", 42, "review",
               profile=profile)
    assert r["suite"] == "silex" and len(seen) == 3
    assert r["suite_sha256"] == ef.mc._digest(ef.load(ROOT, holdout=True))
    assert r["summary"]["initial_pass"] == 3
    assert ("role_tool_probes" in r) == (profile == "holdout-coached")
    assert r["native_excellence_certified"] is False
