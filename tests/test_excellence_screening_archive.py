"""Replay public screening evidence offline; never execute generated content."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from clawfedora import excellence_screening as es

ROOT = Path(__file__).resolve().parents[1]
RUN = 45769070175
COMMIT = "26394deebcf43a7dd600ff86aedfd6f2a2bcee9c"
EXPECTED = {
    "gemma": ((5, 1, 1), (5, 2, 0)),
    "qwen": ((2, 3, 2), (3, 3, 1)),
    "ornith": ((1, 1, 5), (1, 1, 5)),
    "lfm": ((0, 0, 7), (0, 0, 7)),
}
DIGESTS = {
    "gemma": "6114515d63c17436a7c0417d82820ac65ad643e2806c5a3c89cb62846436ed0b",
    "ornith": "e5df7dcdd8a263994df62d610317e07be0d6af23f96fcbd8543273058fce575e",
    "qwen": "56671c2ab9385f9cfcb404638e32cd62d88e3501d44822208363c010179a3c90",
    "lfm": "9cf756159fc2f3b9128c6a3f544ec90c5e9b8afdbb4179a57b8aea9de589cfb2",
}


def _report(alias):
    return json.loads(
        (ROOT / f"tests/fixtures/excellence_{RUN}_{alias}.json").read_text(encoding="utf-8")
    )


def _replay(case, attempt):
    # Explicit, narrowly scoped technical synonym; no truncation or other repairs.
    response = attempt["response"]
    value = json.loads(response["content"])
    if case["id"] == "writing" and value.get("dump_format") in {"-Fc", "pg_dump -Fc"}:
        value["dump_format"] = "custom"
        response = {**response, "content": json.dumps(value, ensure_ascii=False)}
    return es.tm.validate(case, response)


@pytest.mark.parametrize("alias", sorted(EXPECTED))
def test_archived_screening_replays_original_and_scoped_review(alias):
    report = _report(alias)
    suite = es.load(ROOT)
    assert report["commit"] == COMMIT
    assert report["suite_sha256"] == es.mc._digest(suite)
    assert report["classification"] == "synthetic_public"
    assert report["model"]["digest"] == DIGESTS[alias]
    assert report["model"]["runtime_id"] == es.CANDIDATES[alias]
    assert report["native_excellence_certified"] is False
    assert report["production_routing_changed"] is False
    assert len(report["results"]) == len(suite["cases"]) == 7
    counts = [0, 0, 0]
    for case, row in zip(suite["cases"], report["results"], strict=True):
        assert (row["id"], row["role"]) == (case["id"], case["role"])
        for attempt in [row["initial"], *([row["correction"]] if "correction" in row else [])]:
            assert es.tm.validate(case, attempt["response"]) == attempt["validation"]
        initial = _replay(case, row["initial"])
        if initial["state"] == "PASS_FACT_CONTRACT_ONLY":
            counts[0] += 1
        elif "correction" in row and es.promotion(
            {"validation": initial}, {"validation": _replay(case, row["correction"])}
        ) == "CORRECTED_FACT_CONTRACT_ONLY":
            counts[1] += 1
        else:
            counts[2] += 1
    summary = report["summary"]
    assert tuple(summary[k] for k in ("initial_pass", "corrected", "blocked")) == EXPECTED[alias][0]
    assert tuple(counts) == EXPECTED[alias][1]


def test_length_failures_are_not_invalid_json_or_automatically_promoted():
    report = _report("ornith")
    cases = {case["id"]: case for case in es.load(ROOT)["cases"]}
    long_answers = []
    for row in report["results"]:
        for attempt in [row["initial"], *([row["correction"]] if "correction" in row else [])]:
            if attempt["validation"]["state"] == "FAIL_SCHEMA":
                value = json.loads(attempt["response"]["content"])
                case = cases[row["id"]]
                assert set(value) == set(es.tm.schema(case)["required"])
                assert all(type(value[k]) is type(v) for k, v in case["fields"].items())
                assert type(value["executed"]) is bool
                assert len(value["reason"].strip()) > 1200
                assert _replay(case, attempt)["state"] == "FAIL_SCHEMA"
                long_answers.append(row["id"])
    assert len(long_answers) == 9


def test_format_synonym_never_overrides_wrong_restore_or_execution():
    case = es.load(ROOT)["cases"][-1]
    for field in ("restore_pass", "executed"):
        value = {**case["fields"], "dump_format": "pg_dump -Fc",
                 "reason": "Justification synthétique.", "executed": False}
        value[field] = True
        attempt = {"response": {"content": json.dumps(value), "done_reason": "stop"}}
        assert _replay(case, attempt)["state"] == "FAIL_FACT_CONTRACT"


def test_archive_attempt_count():
    assert sum(
        1 + int("correction" in row)
        for alias in EXPECTED for row in _report(alias)["results"]
    ) == 48
