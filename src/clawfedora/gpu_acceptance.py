"""Explicit operator-only local GPU benchmark, recording no conversation or secrets.

The benchmark never edits settings or sends model input to the cloud.
"""
from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from clawfedora.context_probe import probe_context

Probe = Callable[..., dict[str, Any]]


def benchmark(
    repo: Path, *, context_sizes: tuple[int, ...], probe: Probe = probe_context
) -> dict[str, Any]:
    if not context_sizes or len(context_sizes) > 3 or any(
        context not in (8192, 16384, 32768) for context in context_sizes
    ):
        raise ValueError("contextes autorisés: 8192, 16384, 32768 (maximum 3)")
    results: list[dict[str, Any]] = []
    for context in context_sizes:
        result = probe(repo, context_tokens=context, fill_ratio=0.6)
        if result.get("verdict") not in {
            "FULL_GPU", "PARTIAL_CPU_OFFLOAD", "CPU_ONLY", "PROMPT_TRUNCATED"
        }:
            raise ValueError("résultat du GPU non certifiable")
        results.append({
            key: result.get(key)
            for key in (
                "context_tokens", "prompt_tokens", "gpu_share_pct",
                "resident_gib", "resident_vram_gib",
                "prompt_tokens_per_second", "output_tokens_per_second", "verdict",
            )
        })
    recommended = max(
        (r["context_tokens"] for r in results if r["verdict"] == "FULL_GPU"),
        default=None,
    )
    return {
        "scope": "local_ollama_qwen_benchmark_only",
        "model_content_not_exported": True,
        "config_modified": False,
        "cloud_used": False,
        "recommendation_requires_human_approval": True,
        "recommended_full_gpu_context": recommended,
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mesurer Qwen local sur la B580 sans mutation")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--contexts", default="8192,16384,32768")
    parser.add_argument(
        "--apply", action="store_true", help="Effectuer les inférences Ollama locales"
    )
    args = parser.parse_args(argv)
    try:
        contexts = tuple(int(item) for item in args.contexts.split(","))
        if not contexts or len(set(contexts)) != len(contexts) or any(
            item not in (8192, 16384, 32768) for item in contexts
        ):
            raise ValueError("liste de contextes invalide")
        if not args.apply:
            print(json.dumps({
                "verdict": "DRY_RUN", "contexts": contexts,
                "cloud_used": False, "model_calls": 0, "config_modified": False,
            }))
            return 0
        print(json.dumps(benchmark(args.root, context_sizes=contexts), ensure_ascii=False, indent=2))
    except (ValueError, OSError, TimeoutError) as exc:
        print(json.dumps({"verdict": "REFUSED", "reason": str(exc)}, ensure_ascii=False))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
