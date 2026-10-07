"""Measure whether a context size really fits the GPU on this machine.

The daily budget (32768 tokens) is a software contract. Only this measurement, run on
the target PC, tells whether the model stays fully on the GPU and how fast it answers
once the context is actually filled.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from clawfedora.core_config import daily_budget
from clawfedora.lifecycle import model_plan
from clawfedora.qualification import _request_json

ENDPOINT = "http://127.0.0.1:11434"
ALLOWED_CONTEXTS = (8192, 16384, 32768)
Request = Callable[..., dict[str, Any]]

# One French sentence is about 30 tokens; the exact count comes from the server.
_SENTENCE = (
    "Le service web écoute sur le port 8443 derrière un reverse proxy, "
    "et chaque ligne du journal doit être relue avant de conclure. "
)


def _rate(count: Any, duration_ns: Any) -> float | None:
    if not isinstance(count, int) or not isinstance(duration_ns, int) or duration_ns <= 0:
        return None
    return round(count / (duration_ns / 1_000_000_000), 1)


def probe_context(
    repo_root: Path,
    context_tokens: int | None = None,
    *,
    fill_ratio: float = 0.6,
    request: Request = _request_json,
) -> dict[str, Any]:
    """Fill a share of the context, generate a short answer and read the GPU share."""
    budget = daily_budget(repo_root)
    context = int(context_tokens or budget["context_tokens"])
    if context not in ALLOWED_CONTEXTS:
        raise ValueError(f"contexte autorisé: {', '.join(map(str, ALLOWED_CONTEXTS))}")
    if not 0.1 <= fill_ratio <= 0.8:
        raise ValueError("fill_ratio entre 0.1 et 0.8")
    model = str(model_plan(repo_root)[0]["runtime_id"])
    repeats = max(1, int(context * fill_ratio / 30))
    answer = request(
        ENDPOINT + "/api/generate",
        payload={
            "model": model,
            "prompt": _SENTENCE * repeats + "\nRésume ce texte en une phrase.",
            "stream": False,
            "think": False,
            "options": {"num_ctx": context, "num_predict": 128, "temperature": 0},
            "keep_alive": str(budget["keep_alive"]),
        },
        timeout=600,
    )
    prompt_tokens = answer.get("prompt_eval_count")
    if not isinstance(prompt_tokens, int) or prompt_tokens <= 0:
        raise ValueError("sonde: le serveur n'a pas rapporté de tokens d'entrée")
    runners = request(ENDPOINT + "/api/ps").get("models", [])
    loaded = next(
        (
            item
            for item in runners
            if isinstance(item, dict) and model in {item.get("name"), item.get("model")}
        ),
        None,
    )
    if loaded is None:
        raise ValueError("sonde: modèle absent de l'inventaire résident")
    size, size_vram = int(loaded.get("size", 0)), int(loaded.get("size_vram", 0))
    if size <= 0:
        raise ValueError("sonde: taille résidente illisible")
    gpu_share = round(100 * size_vram / size, 1)
    truncated = prompt_tokens >= context - 128
    if truncated:
        verdict = "PROMPT_TRUNCATED"
    elif size_vram >= size:
        verdict = "FULL_GPU"
    elif size_vram > 0:
        verdict = "PARTIAL_CPU_OFFLOAD"
    else:
        verdict = "CPU_ONLY"
    return {
        "verdict": verdict,
        "model": model,
        "context_tokens": context,
        "allocated_context_tokens": loaded.get("context_length"),
        "prompt_tokens": prompt_tokens,
        "prompt_fill_pct": round(100 * prompt_tokens / context, 1),
        "resident_gib": round(size / 1024**3, 2),
        "resident_vram_gib": round(size_vram / 1024**3, 2),
        "gpu_share_pct": gpu_share,
        "load_seconds": round(int(answer.get("load_duration", 0)) / 1_000_000_000, 1),
        "prompt_tokens_per_second": _rate(prompt_tokens, answer.get("prompt_eval_duration")),
        "output_tokens_per_second": _rate(answer.get("eval_count"), answer.get("eval_duration")),
        "daily_context_tokens": budget["context_tokens"],
        "note": (
            "FULL_GPU: le contexte tient entièrement sur la carte. PARTIAL_CPU_OFFLOAD: "
            "une partie du modèle passe sur le processeur, la vitesse chute; réduire "
            "context_tokens dans config/core/openclaw_policy.yaml puis réinstaller."
        ),
    }
