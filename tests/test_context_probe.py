from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from clawfedora import ops_cli
from clawfedora.context_probe import probe_context

ROOT = Path(__file__).resolve().parents[1]
MODEL = "qwen3.5:9b-q4_K_M"


def _server(size_vram: int, prompt_tokens: int = 19000) -> Any:
    calls: list[dict[str, Any]] = []

    def request(url: str, *, payload: dict[str, Any] | None = None, timeout: float = 10) -> Any:
        if url.endswith("/api/generate"):
            assert payload is not None
            calls.append(payload)
            return {
                "prompt_eval_count": prompt_tokens,
                "prompt_eval_duration": 10_000_000_000,
                "eval_count": 100,
                "eval_duration": 4_000_000_000,
                "load_duration": 3_000_000_000,
            }
        return {"models": [{"name": MODEL, "size": 8 * 1024**3, "size_vram": size_vram}]}

    request.calls = calls  # type: ignore[attr-defined]
    return request


def test_probe_uses_the_daily_context_and_reports_full_gpu() -> None:
    request = _server(8 * 1024**3)
    report = probe_context(ROOT, request=request)
    assert report["verdict"] == "FULL_GPU" and report["gpu_share_pct"] == 100.0
    assert report["context_tokens"] == report["daily_context_tokens"] == 32768
    assert report["prompt_tokens_per_second"] == 1900.0
    assert report["output_tokens_per_second"] == 25.0
    options = request.calls[0]["options"]
    assert options["num_ctx"] == 32768 and request.calls[0]["think"] is False


def test_probe_detects_cpu_offload_truncation_and_bad_input() -> None:
    assert probe_context(ROOT, request=_server(6 * 1024**3))["verdict"] == "PARTIAL_CPU_OFFLOAD"
    assert probe_context(ROOT, request=_server(0))["verdict"] == "CPU_ONLY"
    truncated = probe_context(ROOT, 16384, request=_server(8 * 1024**3, prompt_tokens=16384))
    assert truncated["verdict"] == "PROMPT_TRUNCATED"
    with pytest.raises(ValueError, match="contexte autorisé"):
        probe_context(ROOT, 65536, request=_server(1))
    with pytest.raises(ValueError, match="tokens d'entrée"):
        probe_context(ROOT, request=_server(1, prompt_tokens=0))


def test_probe_cli_is_a_plan_without_apply(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = ops_cli.main(["--root", str(ROOT), "--runtime-root", str(tmp_path), "context-probe"])
    assert code == 0
    assert "CONTEXT_PROBE_PLAN context=32768" in capsys.readouterr().out
