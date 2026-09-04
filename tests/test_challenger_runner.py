from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from clawfedora import challenger_runner, optimization

ROOT = Path(__file__).resolve().parents[1]


def test_challenger_plan_is_outside_nominal_routing() -> None:
    plan = challenger_runner.provision_challenger_plan(ROOT)
    assert plan["slot"] == "gemma-deep"
    assert plan["runtime_id"] == "ministral-3:14b-instruct-2512-q4_K_M"
    assert plan["routed"] is False
    assert plan["counts_toward_required_fleet"] is False
    assert plan["automatic_promotion"] is False
    assert plan["explicit_pull_only"] is True


def test_challenger_and_incumbent_share_the_same_slot() -> None:
    incumbent = challenger_runner.challenger_plan(ROOT, "incumbent")
    challenger = challenger_runner.challenger_plan(ROOT, "challenger")
    assert incumbent.slot == challenger.slot == "gemma-deep"
    assert incumbent.runtime_id == "gemma3:12b-it-q4_K_M"
    assert challenger.runtime_id == "ministral-3:14b-instruct-2512-q4_K_M"


def test_blue_square_fixture_is_a_png() -> None:
    value = challenger_runner._png_blue_square()
    assert value.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(value) > 100


def _fake_chat(
    _endpoint: str,
    _model: challenger_runner.ChallengerModel,
    probe: dict[str, Any],
    *,
    timeout: float = 210.0,
) -> dict[str, Any]:
    assert timeout == 210.0
    probe_id = probe["id"]
    if probe_id == "vision":
        output = "BLUE_SQUARE"
        calls: list[dict[str, Any]] = []
    elif probe_id == "document-quality":
        output = json.dumps(
            {"service": "openclaw", "severity": "high", "decision": "rollback"}
        )
        calls = []
    else:
        output = ""
        calls = [
            {
                "function": {
                    "name": "record_incident",
                    "arguments": {"service": "openclaw", "severity": "high"},
                }
            }
        ]
    return {
        "output": output,
        "tool_calls": calls,
        "first_token_ms": 100.0,
        "wall_ms": 500.0,
        "tokens_per_second": 20.0,
        "output_tokens": 10,
        "finish_reason": "stop",
    }


def _patch_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(challenger_runner, "_chat_probe", _fake_chat)
    monkeypatch.setattr(challenger_runner, "_request_json", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(challenger_runner, "_vram_mib", lambda: 4096.0)
    monkeypatch.setattr(challenger_runner, "_ram_mib", lambda: 8192.0)

    def inventory(
        _endpoint: str,
        model: challenger_runner.ChallengerModel,
    ) -> dict[str, Any]:
        return {
            "runtime_id": model.runtime_id,
            "digest": f"digest-{model.variant}",
            "quantization": model.quantization,
        }

    monkeypatch.setattr(challenger_runner, "_inventory", inventory)


def test_challenger_snapshot_records_required_live_quality_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_runner(monkeypatch)
    path = challenger_runner.run_challenger_snapshot(
        ROOT,
        variant="challenger",
        endpoint="http://127.0.0.1:11434",
        output=tmp_path / "challenger.json",
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["kind"] == "model-challenger"
    assert payload["candidate_id"] == "ministral-3:14b-instruct-2512-q4_K_M"
    assert payload["functional_pass"] is True
    assert payload["security_pass"] is True
    assert payload["vision_pass"] is True
    assert payload["document_quality_pass"] is True
    assert payload["tool_calling_pass"] is True
    assert payload["raw_outputs_persisted"] is False
    assert payload["cloud_calls_allowed"] is False
    assert payload["routed"] is False
    assert payload["automatic_promotion"] is False
    optimization.load_evidence(path)


def test_challenger_comparison_is_reproducible_from_three_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_runner(monkeypatch)
    incumbent: list[Path] = []
    challenger: list[Path] = []
    for index in range(3):
        incumbent.append(
            challenger_runner.run_challenger_snapshot(
                ROOT,
                variant="incumbent",
                endpoint="http://127.0.0.1:11434",
                output=tmp_path / f"incumbent-{index}.json",
            )
        )
        challenger.append(
            challenger_runner.run_challenger_snapshot(
                ROOT,
                variant="challenger",
                endpoint="http://127.0.0.1:11434",
                output=tmp_path / f"challenger-{index}.json",
            )
        )
    report = optimization.compare_model_challenger(ROOT, incumbent, challenger)
    assert report.candidate_id == "ministral-3:14b-instruct-2512-q4_K_M"
    assert report.verdict == "ELIGIBLE_FOR_HUMAN_PROMOTION"
