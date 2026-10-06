from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from clawfedora import model_compare
from clawfedora.gpu_telemetry import PeakSampler
from clawfedora.project_common import read_json
from clawfedora.project_worker import worker_lock

ROOT = Path(__file__).resolve().parents[1]


def fake_api(monkeypatch: pytest.MonkeyPatch, problem: str = "") -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    active: list[dict[str, Any]] = []
    models = model_compare.comparison_plan(ROOT)["models"]

    def request(
        url: str, *, payload: dict[str, Any] | None = None, timeout: float = 10
    ) -> dict[str, Any]:
        calls.append({"url": url, "payload": payload, "timeout": timeout})
        endpoint = url.rsplit("/", 1)[1]
        if endpoint == "version":
            return {"version": "wrong" if problem == "version" else "0.35.1"}
        if endpoint == "tags":
            return {
                "models": [
                    {"name": model, "digest": f"digest-{i}"}
                    for i, model in enumerate(models)
                    if not (i == 2 and problem == "missing")
                ]
            }
        if endpoint == "ps":
            return {"models": [{"name": "busy"}] if problem == "busy" else active}
        if endpoint == "show":
            return {"details": {"quantization_level": "Q8_0" if problem == "quant" else "Q4_K_M"}}
        assert payload
        if endpoint == "generate":
            assert payload["keep_alive"] == 0
            active.clear()
            return {}
        assert endpoint == "chat"
        if problem == "request":
            raise ValueError("inference failed")
        active[:] = [
            {
                "name": payload["model"],
                "digest": f"digest-{models.index(payload['model'])}",
                "size_vram": 0 if problem == "cpu" else 6000000000,
            }
        ]
        if problem == "identity":
            active[0]["digest"] = "changed"
        return {
            "done": problem != "incomplete",
            "done_reason": "length",
            "message": {"content": "Une hypothèse, puis vérifier."},
            "eval_count": 100,
            "eval_duration": 2000000000,
            "prompt_eval_count": 120,
            "load_duration": 20,
        }

    monkeypatch.setattr(model_compare, "_request_json", request)
    monkeypatch.setattr(
        model_compare,
        "collect_hardware_gate",
        lambda *_args: SimpleNamespace(
            payload=lambda: {"verdict": "FAIL" if problem == "hardware" else "PASS"}
        ),
    )
    monkeypatch.setattr(model_compare, "b580_slot", lambda: "fake")
    monkeypatch.setattr(model_compare, "PeakSampler", lambda *_args: PeakSampler(lambda: 100.0))
    return calls


def test_dry_run_never_requests_or_downloads_a_model(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "plan.json"
    monkeypatch.setattr(sys, "argv", ["compare", "--root", str(ROOT), "--output", str(output)])
    monkeypatch.setattr(model_compare, "_request_json", lambda *_args, **_kwargs: pytest.fail("HTTP"))
    assert model_compare.main() == 0
    plan = read_json(output)
    assert plan["runtime_tested"] is False and plan["automatic_promotion"] is False
    assert len(plan["cases"]) == 12 and len(plan["models"]) == 3
    assert model_compare.comparison_plan(ROOT, 1536)["context"] == 8192
    with pytest.raises(SystemExit):
        model_compare.main()


@pytest.mark.parametrize("tokens,repeats", [(4096, 1), (1024, 0), (1024, 4)])
def test_comparison_budget_is_explicit(tokens: int, repeats: int) -> None:
    with pytest.raises(ValueError):
        model_compare.comparison_plan(ROOT, tokens, repeats)


@pytest.mark.parametrize("case_index", [0, 8])
def test_response_comparison_keeps_raw_answers_and_requires_human_review(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    case_index: int,
) -> None:
    calls = fake_api(monkeypatch)
    plan = model_compare.comparison_plan(ROOT)
    plan["cases"] = [plan["cases"][case_index]]
    output = tmp_path / "result.json"
    result = model_compare.run_comparison(ROOT, tmp_path / "runtime", output, plan)
    assert result["status"] == "AWAITING_HUMAN_REVIEW"
    assert result["runtime_tested"] is True and result["automatic_promotion"] is False
    assert len(result["results"]) == 3
    assert all(value is None for value in result["results"][0]["human_review"].values())
    assert result["results"][0]["tokens_per_second"] == 50
    assert result["results"][0]["done_reason"] == "length"  # Truncation is visible, not a PASS.
    assert sum(call["url"].endswith("/generate") for call in calls) == 3
    assert not any("pull" in call["url"] for call in calls)
    assert all(call["payload"]["think"] is False for call in calls if call["url"].endswith("/chat"))
    for call in calls:
        if call["url"].endswith("/chat"):
            assert call["payload"]["messages"][1:-1] == plan["cases"][0].get("history", [])
    assert read_json(output)["status"] == "AWAITING_HUMAN_REVIEW"


@pytest.mark.parametrize(
    "problem",
    ["hardware", "version", "missing", "busy", "quant", "request", "cpu", "identity", "incomplete"],
)
def test_failed_or_unqualified_comparison_never_becomes_a_complete_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    problem: str,
) -> None:
    calls = fake_api(monkeypatch, problem)
    plan = model_compare.comparison_plan(ROOT)
    plan["cases"] = plan["cases"][:1]
    output = tmp_path / "result.json"
    with pytest.raises(ValueError):
        model_compare.run_comparison(ROOT, tmp_path / "runtime", output, plan)
    if output.exists():
        assert read_json(output)["status"] == "INCOMPLETE"
        assert read_json(output)["runtime_tested"] is False
        assert calls[-1]["url"].endswith("/generate")
    else:
        assert not any(call["url"].endswith("/chat") for call in calls)


def test_comparison_obeys_shared_lock_and_preserves_existing_reports(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = fake_api(monkeypatch)
    plan = model_compare.comparison_plan(ROOT)
    output = tmp_path / "report.json"
    with worker_lock(tmp_path / "runtime"), pytest.raises(ValueError, match="actif"):
        model_compare.run_comparison(ROOT, tmp_path / "runtime", output, plan)
    assert not calls
    output.write_text("existing")
    with pytest.raises(ValueError, match="écraser"):
        model_compare.run_comparison(ROOT, tmp_path / "runtime", output, plan)
    assert output.read_text() == "existing"
