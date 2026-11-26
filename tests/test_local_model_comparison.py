"""CPU comparison tests use fake API replies, never download or execute a model."""
from __future__ import annotations

import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from clawfedora import local_model_comparison as mc

ROOT = Path(__file__).resolve().parents[1]


def reply(model, content, calls=None):
    return {
        "model": model, "done": True, "done_reason": "stop",
        "message": {"content": content, "tool_calls": calls or []},
        **dict.fromkeys(("total_duration", "load_duration", "prompt_eval_count",
                         "prompt_eval_duration", "eval_count", "eval_duration"), 1),
    }


def test_inputs_are_identical_and_cover_all_roles():
    pilot = mc._inputs(ROOT, "pilot")
    assert len(pilot) == 7
    assert {row["role"] for row in pilot} == set(mc.ROLES)
    assert len(mc._inputs(ROOT, "smoke")) == 2
    assert len(mc._inputs(ROOT, "extended")) == 14
    assert all("aucun outil OpenClaw" in row["system"] for row in pilot)
    assert mc._digest(pilot) == mc._digest(mc._inputs(ROOT, "pilot"))


def test_dry_run_never_calls_model(tmp_path, monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail("unexpected inference")
    monkeypatch.setattr(mc, "_chat", forbidden)
    monkeypatch.setattr(mc, "_identity", forbidden)
    assert mc.main(["--root", str(ROOT), "--model", "qwen",
                    "--commit", "a" * 40, "--output", str(tmp_path / "out.json")]) == 0
    assert json.loads(capsys.readouterr().out)["assessment"] == "NOT_RUN"
    assert not list(tmp_path.iterdir())


def test_identity_requires_exact_version_quantization_and_digest(monkeypatch):
    def request(url):
        if url.endswith("/version"):
            return {"version": "0.40.6"}
        return {"models": [{"name": mc.MODELS["qwen"], "digest": "a" * 64,
                            "size": 6_600_000_000, "details": {"quantization_level": "Q4_K_M"}}]}
    monkeypatch.setattr(mc.ollama_api, "request_json", request)
    assert mc._identity(ROOT, "qwen")["digest"] == "a" * 64
    monkeypatch.setattr(mc.ollama_api, "request_json", lambda _: {"version": "0.1.0"})
    with pytest.raises(ValueError, match="version"):
        mc._identity(ROOT, "qwen")


def test_probe_checks_tool_arguments_and_answer(monkeypatch):
    model = mc.MODELS["ornith"]
    calls = [{"function": {"name": "read_atlas_fixture", "arguments": {"service": "atlas-api"}}}]
    answers = iter([reply(model, "", calls),
                    reply(model, "service=atlas-api;port=8443;status=inactive")])
    monkeypatch.setattr(mc, "_chat", lambda _: next(answers))
    assert mc._tool_probe(model)["state"] == "PASS_FIXTURE_ONLY"
    monkeypatch.setattr(mc, "_chat", lambda _: reply(model, "no tool"))
    assert mc._tool_probe(model)["state"] == "FAIL_TOOL_CALL"


def test_static_code_probe_never_executes_candidate(monkeypatch):
    model = mc.MODELS["qwen"]
    script = '#!/bin/bash\nsha256sum -- "$1"'
    monkeypatch.setattr(mc, "_chat", lambda _: reply(model, json.dumps({"script": script})))

    def check(args, **kwargs):
        assert args == ["shellcheck", "--shell=bash", "--format=json", "-"]
        assert kwargs["input"] == script
        return CompletedProcess(args, 0, stdout="[]")

    monkeypatch.setattr(mc.subprocess, "run", check)
    assert mc._code_probe(model)["state"] == "PASS_STATIC_ONLY"


def test_run_writes_real_response_schema_without_a_quality_pass(tmp_path, monkeypatch):
    model = mc.MODELS["qwen"]
    monkeypatch.setattr(mc, "_identity", lambda *_: {"digest": "a" * 64})
    monkeypatch.setattr(mc, "_chat", lambda _: reply(model, "Réponse synthétique simulée."))
    monkeypatch.setattr(mc, "_tool_probe", lambda _: {"state": "FAIL_TOOL_CALL"})
    monkeypatch.setattr(mc, "_code_probe", lambda _: {"state": "PASS_STATIC_ONLY"})
    target = tmp_path / "report.json"
    result = mc.run(ROOT, "qwen", "smoke", "a" * 40, target)
    assert result["assessment"] == "RESPONSES_COLLECTED_REVIEW_REQUIRED"
    assert not result["native_agent_qualification"] and not result["gpu_qualification"]
    assert len(result["results"]) == 2
    assert all(row["quality_review"] == "NOT_REVIEWED" for row in result["results"])
    assert json.loads(target.read_text()) == result


def test_incomplete_run_keeps_partial_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(mc, "_identity", lambda *_: {"digest": "a" * 64})

    def broken(_):
        raise OSError("not running")

    monkeypatch.setattr(mc, "_chat", broken)
    target = tmp_path / "report.json"
    result = mc.run(ROOT, "ornith", "smoke", "a" * 40, target)
    assert result["assessment"] == "INCOMPLETE_INFERENCE"
    assert result["results"][0]["state"] == "INFERENCE_ERROR"
    assert result["tool_probe"]["state"] == "NOT_RUN"
    assert json.loads(target.read_text()) == result
