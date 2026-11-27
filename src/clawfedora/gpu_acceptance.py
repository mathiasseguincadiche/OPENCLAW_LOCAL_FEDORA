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
from clawfedora.gpu_profiles import PROFILES, require_configured
from clawfedora.storage import load_settings, require_storage

Probe = Callable[..., dict[str, Any]]


def benchmark(
    repo: Path, *, context_sizes: tuple[int, ...], near_limit: bool = False,
    model_alias: str | None = None, probe: Probe = probe_context,
) -> dict[str, Any]:
    if not context_sizes or len(context_sizes) > 3 or any(
        context not in (8192, 16384, 32768) for context in context_sizes
    ):
        raise ValueError("contextes autorisés: 8192, 16384, 32768 (maximum 3)")
    requested_fill = 0.9 if near_limit else 0.6
    results: list[dict[str, Any]] = []
    for context in context_sizes:
        arguments: dict[str, Any] = {"context_tokens": context, "fill_ratio": requested_fill}
        if model_alias is not None:
            arguments["model_alias"] = model_alias
        result = probe(repo, **arguments)
        if result.get("verdict") not in {
            "FULL_GPU", "PARTIAL_CPU_OFFLOAD", "CPU_ONLY", "PROMPT_TRUNCATED"
        }:
            raise ValueError("résultat du GPU non certifiable")
        actual_fill = result.get("prompt_fill_pct")
        allocated = result.get("allocated_context_tokens")
        # A 60% test is insufficient to certify a 32K context. Even in
        # near-limit mode, refuse a false FULL_GPU when the server truncated
        # the intended prompt or allocated a smaller context.
        validated = bool(
            near_limit
            and result["verdict"] == "FULL_GPU"
            and isinstance(actual_fill, (float, int)) and not isinstance(actual_fill, bool)
            and float(actual_fill) >= 80.0
            and isinstance(allocated, int) and allocated >= context
        )
        entry = {
            key: result.get(key)
            for key in (
                "context_tokens", "prompt_tokens", "prompt_fill_pct",
                "allocated_context_tokens", "gpu_share_pct",
                "resident_gib", "resident_vram_gib", "load_seconds",
                "prompt_tokens_per_second", "output_tokens_per_second", "verdict",
            )
        }
        entry["near_limit_qualified"] = validated
        results.append(entry)
    recommended = max(
        (r["context_tokens"] for r in results if r["verdict"] == "FULL_GPU"),
        default=None,
    )
    qualified = max(
        (r["context_tokens"] for r in results if r["near_limit_qualified"]),
        default=None,
    )
    return {
        "scope": "local_ollama_model_benchmark_only",
        "model_alias": model_alias or "qwen-max",
        "model_content_not_exported": True,
        "config_modified": False,
        "cloud_used": False,
        "recommendation_requires_human_approval": True,
        "recommended_full_gpu_context": recommended,
        "recommended_context_is_provisional": qualified != recommended or recommended is None,
        "near_limit_requested": near_limit,
        "near_limit_fill_target_pct": round(requested_fill * 100),
        "qualified_near_limit_context": qualified,
        "hardware_qualification": "PENDING_REAL_FEDORA_B580_ACCEPTANCE",
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Mesurer Qwen, Ornith et Gemma sur la B580 sans mutation",
    )
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--contexts", default="8192,16384,32768")
    parser.add_argument(
        "--models", choices=("qwen-max", "ornith-code", "gemma-expert", "all"), default="qwen-max",
        help="Modèle à mesurer, ou les trois modèles locaux (all)",
    )
    parser.add_argument(
        "--near-limit", action="store_true",
        help="Essai exigeant 90%% du contexte ; jamais exécuté sans --apply",
    )
    parser.add_argument(
        "--apply", action="store_true", help="Effectuer les inférences Ollama locales"
    )
    parser.add_argument(
        "--record", action="store_true",
        help="Conserver un rapport privé après un benchmark explicitement exécuté",
    )
    parser.add_argument(
        "--runtime-root", type=Path,
        help="Runtime Fedora géré (défaut : contrat de stockage ; explicite pour --record)",
    )
    parser.add_argument(
        "--expected-profile", choices=tuple(PROFILES),
        help="Vérifier le profil systemd avant/après la mesure enregistrée",
    )
    args = parser.parse_args(argv)
    try:
        if args.expected_profile and not args.record:
            raise ValueError("--expected-profile exige --record")
        if args.record and (not args.apply or args.runtime_root is None):
            raise ValueError("--record exige --apply et --runtime-root")
        if args.runtime_root is not None and not args.apply:
            raise ValueError("--runtime-root exige --apply")
        contexts = tuple(int(item) for item in args.contexts.split(","))
        if not contexts or len(set(contexts)) != len(contexts) or any(
            item not in (8192, 16384, 32768) for item in contexts
        ):
            raise ValueError("liste de contextes invalide")
        aliases = (
            ("qwen-max", "ornith-code", "gemma-expert")
            if args.models == "all" else (args.models,)
        )
        if not args.apply:
            print(json.dumps({
                "verdict": "DRY_RUN", "contexts": contexts, "models": aliases,
                "near_limit_requested": bool(args.near_limit),
                "cloud_used": False, "model_calls": 0, "config_modified": False,
            }))
            return 0
        from clawfedora.performance_reports import prepare_record, save
        from clawfedora.project_worker import worker_lock

        settings = load_settings(args.root)
        runtime = args.runtime_root or settings.runtime_root
        require_storage(runtime, settings)
        marker = runtime / ".openclaw-fedora-runtime"
        if marker.is_symlink() or not marker.is_file():
            raise ValueError("Benchmark réservé au runtime Fedora géré")
        # The lock applies even to a run without a saved report.
        with worker_lock(runtime):
            if args.record:
                prepare_record(runtime)
            if args.expected_profile:
                require_configured(args.expected_profile)
            measured = {
                alias: benchmark(
                    args.root, context_sizes=contexts, near_limit=args.near_limit,
                    model_alias=alias,
                ) for alias in aliases
            }
            if args.expected_profile:
                require_configured(args.expected_profile)
            if args.record:
                save(runtime, measured, configured_profile=args.expected_profile)
        report = (
            {
                "scope": "local_ollama_two_model_benchmark",
                "config_modified": False, "cloud_used": False,
                "benchmarks": measured,
            } if args.models == "all" else measured[aliases[0]]
        )
        if args.expected_profile:
            report["configured_profile"] = args.expected_profile
            report["backend_profile_verified"] = False
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except (ValueError, OSError, TimeoutError) as exc:
        print(json.dumps({"verdict": "REFUSED", "reason": str(exc)}, ensure_ascii=False))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
