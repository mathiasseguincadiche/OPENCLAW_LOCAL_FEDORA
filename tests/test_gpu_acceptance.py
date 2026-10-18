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
            "prompt_fill_pct": 60.0,
            "allocated_context_tokens": context_tokens,
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


def test_near_limit_context_qualification_requires_real_fill_and_allocation(
    tmp_path: Path,
) -> None:
    def measured(
        _root: Path, *, context_tokens: int, fill_ratio: float,
    ) -> dict[str, Any]:
        assert fill_ratio == 0.9
        return {
            "context_tokens": context_tokens,
            "prompt_tokens": round(context_tokens * 0.9),
            "prompt_fill_pct": 90.0,
            "allocated_context_tokens": context_tokens,
            "gpu_share_pct": 100.0,
            "resident_gib": 9.1,
            "resident_vram_gib": 9.1,
            "prompt_tokens_per_second": 140.0,
            "output_tokens_per_second": 18.5,
            "verdict": "FULL_GPU",
        }

    passed = benchmark(tmp_path, context_sizes=(16384,), near_limit=True, probe=measured)
    assert passed["qualified_near_limit_context"] == 16384
    assert passed["results"][0]["near_limit_qualified"] is True
    provisional = benchmark(
        tmp_path, context_sizes=(16384,), near_limit=False,
        probe=lambda _root, *, context_tokens, fill_ratio: {
            **measured(_root, context_tokens=context_tokens, fill_ratio=0.9),
        },
    )
    assert provisional["qualified_near_limit_context"] is None
    assert provisional["recommended_context_is_provisional"] is True


@pytest.mark.parametrize("bad_fill, bad_alloc", [(10.0, 32768), (90.0, 8192)])
def test_near_limit_rejects_false_full_gpu_evidence(
    tmp_path: Path, bad_fill: float, bad_alloc: int,
) -> None:
    def misleading(_root: Path, *, context_tokens: int, fill_ratio: float) -> dict[str, Any]:
        return {
            "context_tokens": context_tokens,
            "prompt_fill_pct": bad_fill,
            "allocated_context_tokens": bad_alloc,
            "verdict": "FULL_GPU",
        }

    result = benchmark(tmp_path, context_sizes=(32768,), near_limit=True, probe=misleading)
    assert result["qualified_near_limit_context"] is None
    assert result["results"][0]["near_limit_qualified"] is False


def test_near_limit_dry_run_never_calls_a_model(tmp_path: Path, capsys: Any) -> None:
    assert main(["--root", str(tmp_path), "--contexts", "32768", "--near-limit"]) == 0
    output = capsys.readouterr().out
    assert '"model_calls": 0' in output
    assert '"near_limit_requested": true' in output
