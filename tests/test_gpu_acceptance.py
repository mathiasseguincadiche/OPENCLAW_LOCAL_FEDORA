from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from clawfedora.gpu_acceptance import benchmark, main


def test_benchmark_reports_only_measured_gpu_state_and_recommends_largest_full_gpu(
    tmp_path: Path,
) -> None:
    calls: list[int] = []

    def fake_probe(_root: Path, *, context_tokens: int, fill_ratio: float) -> dict[str, Any]:
        assert fill_ratio == 0.6
        calls.append(context_tokens)
        return {
            "context_tokens": context_tokens,
            "prompt_tokens": 1234,
            "gpu_share_pct": 100.0 if context_tokens <= 16384 else 75.0,
            "resident_gib": 9.0,
            "resident_vram_gib": 9.0 if context_tokens <= 16384 else 6.75,
            "prompt_tokens_per_second": 230.0,
            "output_tokens_per_second": 21.2,
            "verdict": "FULL_GPU" if context_tokens <= 16384 else "PARTIAL_CPU_OFFLOAD",
        }

    result = benchmark(tmp_path, context_sizes=(8192, 16384, 32768), probe=fake_probe)
    assert calls == [8192, 16384, 32768]
    assert result["recommended_full_gpu_context"] == 16384
    assert result["cloud_used"] is False
    assert result["config_modified"] is False
    assert len(result["results"]) == 3


def test_gpu_benchmark_refuses_unknown_and_non_measured_verdicts(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="contextes autorisés"):
        benchmark(tmp_path, context_sizes=(500_000,), probe=lambda *a, **kw: {})
    with pytest.raises(ValueError, match="non certifiable"):
        benchmark(
            tmp_path, context_sizes=(8192,),
            probe=lambda *a, **kw: {"verdict": "SUPER_FAST"},
        )


def test_gpu_benchmark_dry_run_never_calls_model(tmp_path: Path, capsys: Any) -> None:
    assert main(["--root", str(tmp_path), "--contexts", "16384,32768"]) == 0
    output = capsys.readouterr().out
    assert '"model_calls": 0' in output
    assert '"config_modified": false' in output
    assert '"cloud_used": false' in output
