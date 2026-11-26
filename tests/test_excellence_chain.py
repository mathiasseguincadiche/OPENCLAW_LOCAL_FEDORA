"""Offline non-regression, archived Silex evidence and synthetic handoff integrity."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from clawfedora import excellence_chain as ec
from clawfedora import excellence_finalists as ef

ROOT = Path(__file__).resolve().parents[1]


def test_silex_replay():
    suite = ef.load(ROOT, holdout=True)
    cases = {c["id"]: c for c in suite["cases"]}
    counts = {}
    tools = {}
    paths = sorted((ROOT / "tests/fixtures").glob("silex_45904363657_*.json"))
    assert len(paths) == 12
    for path in paths:
        r = json.loads(path.read_text(encoding="utf-8"))
        assert r["commit"] == "7a1a21b45454d5a0954f08ce1cd3a420bcbd1567"
        assert r["suite_sha256"] == ef.mc._digest(suite)
        alias = r["model"]["alias"]
        assert r["model"]["digest"].removeprefix("sha256:") == ef.DIGESTS[alias]
        assert r["classification"] == "synthetic_public"
        assert r["native_excellence_certified"] is False
        count = counts.setdefault((alias, r["profile"]), [0, 0, 0])
        for row in r["results"]:
            for stage in ("initial", "correction"):
                if stage in row:
                    attempt = row[stage]
                    assert ef.validate(cases[row["id"]], attempt["response"]) == (
                        attempt["validation"]
                    )
            count[["KEEP_INITIAL", "CORRECTED_FACT_CONTRACT_ONLY",
                   "BLOCK_UNRESOLVED"].index(row["selection"])] += 1
        for probe in r.get("role_tool_probes", []):
            tools.setdefault(alias, []).append(probe["state"] == "PASS_FIXTURE_ONLY")
    assert counts == {
        ("qwen", "holdout-direct"): [7, 0, 0],
        ("qwen", "holdout-coached"): [6, 1, 0],
        ("ornith", "holdout-direct"): [5, 0, 2],
        ("ornith", "holdout-coached"): [5, 0, 2],
        ("gemma", "holdout-direct"): [7, 0, 0],
        ("gemma", "holdout-coached"): [7, 0, 0],
    }
    assert {a: (sum(v), len(v)) for a, v in tools.items()} == {
        "qwen": (4, 7), "ornith": (6, 7), "gemma": (7, 7),
    }


def _attempt(case, **updates):
    value = {**case["fields"], "reason": "Justification concise.", "executed": False}
    value.update(updates)
    response = {"content": json.dumps(value), "done_reason": "stop", "tool_calls": []}
    return {"response": response, "validation": ef.validate(case, response)}


@pytest.mark.parametrize("bad", [False, True])
def test_chain_handoff_and_hold(tmp_path, monkeypatch, bad):
    monkeypatch.setattr(ef.es, "identity", lambda *_: {"digest": ef.DIGESTS["gemma"]})
    seen = []

    def ask(model, case, prompt, seed, think, *, profile):
        assert think is False
        assert "candidate-02" in prompt[-1]["content"]
        if seen:
            assert "Contribution précédente NON FIABLE" in prompt[-1]["content"]
            assert json.dumps(seen[-1]["response"], ensure_ascii=False) in prompt[-1]["content"]
        attempt = _attempt(case, executed=True) if bad and not seen else _attempt(case)
        seen.append(attempt)
        return attempt

    monkeypatch.setattr(ef, "ask", ask)
    report = ec.run(ROOT, "gemma", "a" * 40, tmp_path / "out.json", 42)
    assert len(seen) == 7
    assert report["gate"]["release_decision"] == "HOLD"
    assert report["gate"]["publication_authorized"] is False
    assert report["gate"]["state"] == (
        "CHAIN_BLOCKED" if bad else "CHAIN_FACTS_COLLECTED_REVIEW_REQUIRED"
    )
    cases = ec.load(ROOT)["cases"]
    rows = report["results"]
    assert ec.gate(cases, rows[:-1])["state"] == "CHAIN_BLOCKED"
    rows[1]["previous_sha256"] = "wrong"
    assert "handoff_mismatch" in ec.gate(cases, rows)["issues"]
    rows[2]["attempt"]["response"]["content"] = "{}"
    assert "response_digest_mismatch" in ec.gate(cases, rows)["issues"]
    assert "validation_mismatch" in ec.gate(cases, rows)["issues"]


def test_matrix():
    wf = yaml.load(
        (ROOT / ".github/workflows/excellence-role-chain.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    matrix = wf["jobs"]["compare"]["strategy"]["matrix"]
    assert matrix["model"] == list(ef.MODELS)
    assert tuple(map(int, matrix["seed"])) == ef.SEEDS
    assert tuple(c["role"] for c in ec.load(ROOT)["cases"]) == ef.mc.ROLES
