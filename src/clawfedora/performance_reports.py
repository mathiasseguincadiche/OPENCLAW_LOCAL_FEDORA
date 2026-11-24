"""Private, read-only-on-dashboard snapshots from explicit local GPU benchmarks.

Never query Ollama, execute a model, read chat transcripts or accept browser writes.
All displayed numbers come from the existing operator-run benchmark command.
"""
from __future__ import annotations

import json
import math
import os
import secrets
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ALIASES = ("qwen-max", "ornith-code")
LABELS = {"qwen-max": "Qwen 3.5 9B", "ornith-code": "Ornith 1.5 9B"}
CONTEXTS = (8192, 16384, 32768)
VERDICTS = {"FULL_GPU", "PARTIAL_CPU_OFFLOAD", "CPU_ONLY", "PROMPT_TRUNCATED"}
RELATIVE = Path("state/performance/gpu-benchmark.json")
SOURCE = "clawfedora-gpu-benchmark"
MAX_REPORT_BYTES = 16_384
MAX_AGE = timedelta(days=30)


def _root(runtime: Path, *, create: bool) -> Path:
    marker = runtime / ".openclaw-fedora-runtime"
    if marker.is_symlink() or not marker.is_file():
        raise ValueError("rapport GPU réservé au runtime Fedora géré")
    for folder in (runtime / "state", runtime / "state/performance"):
        if folder.is_symlink():
            raise ValueError("dossier de mesures lié : accès refusé")
        if create:
            folder.mkdir(mode=0o700, parents=False, exist_ok=True)
        if folder.exists() and (
            not folder.is_dir() or folder.stat().st_mode & 0o077
        ):
            raise ValueError("dossier de mesures non privé (0700 requis)")
    return runtime / RELATIVE


def _number(value: Any, *, maximum: float) -> float | None:
    if value is None:
        return None
    if (isinstance(value, bool) or not isinstance(value, (float, int))
            or not math.isfinite(float(value)) or not 0 <= float(value) <= maximum):
        raise ValueError("mesure GPU numérique invalide")
    return round(float(value), 2)


def _normalise(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or not value or set(value) - set(ALIASES):
        raise ValueError("rapport GPU : seuls les deux modèles locaux sont autorisés")
    models: dict[str, Any] = {}
    for alias in ALIASES:
        if alias not in value:
            continue
        report = value[alias]
        if (
            not isinstance(report, dict)
            or report.get("model_alias") != alias
            or report.get("cloud_used") is not False
            or report.get("config_modified") is not False
            or type(report.get("near_limit_requested")) is not bool
        ):
            raise ValueError("rapport GPU : provenance ou modèle invalide")
        rows = report.get("results")
        if not isinstance(rows, list) or not 1 <= len(rows) <= len(CONTEXTS):
            raise ValueError("rapport GPU : contextes manquants")
        contexts: set[int] = set()
        clean: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("mesure GPU invalide")
            ctx = row.get("context_tokens")
            if type(ctx) is not int or ctx not in CONTEXTS or ctx in contexts:
                raise ValueError("mesure GPU : contexte inconnu ou répété")
            contexts.add(ctx)
            verdict = row.get("verdict")
            if verdict not in VERDICTS:
                raise ValueError("mesure GPU : verdict non autorisé")
            if type(row.get("near_limit_qualified")) is not bool:
                raise ValueError("mesure GPU : qualification invalide")
            allocated = row.get("allocated_context_tokens")
            if allocated is not None and (
                type(allocated) is not int or not 1 <= allocated <= 65536
            ):
                raise ValueError("mesure GPU : contexte alloué invalide")
            prompt_tokens = row.get("prompt_tokens")
            if prompt_tokens is not None and (
                type(prompt_tokens) is not int or not 0 <= prompt_tokens <= 65536
            ):
                raise ValueError("mesure GPU : tokens d'entrée invalides")
            clean_row = {
                "context_tokens": ctx,
                "allocated_context_tokens": allocated,
                "prompt_tokens": prompt_tokens,
                "verdict": verdict,
                "gpu_share_pct": _number(row.get("gpu_share_pct"), maximum=100),
                "resident_gib": _number(row.get("resident_gib"), maximum=128),
                "resident_vram_gib": _number(row.get("resident_vram_gib"), maximum=128),
                "load_seconds": _number(row.get("load_seconds"), maximum=86400),
                "prompt_tokens_per_second": _number(
                    row.get("prompt_tokens_per_second"), maximum=100000
                ),
                "output_tokens_per_second": _number(
                    row.get("output_tokens_per_second"), maximum=100000
                ),
                "prompt_fill_pct": _number(row.get("prompt_fill_pct"), maximum=100),
            }
            qualified = bool(
                report["near_limit_requested"] and row["near_limit_qualified"]
                and verdict == "FULL_GPU"
                and clean_row["prompt_fill_pct"] is not None
                and clean_row["prompt_fill_pct"] >= 80
                and allocated is not None and allocated >= ctx
            )
            if row["near_limit_qualified"] and not qualified:
                raise ValueError("rapport GPU : qualification non démontrée")
            clean_row["near_limit_qualified"] = qualified
            clean.append(clean_row)
        clean.sort(key=lambda item: item["context_tokens"])
        models[alias] = {
            "near_limit_requested": report["near_limit_requested"],
            "results": clean,
            "largest_full_gpu_context": max(
                (r["context_tokens"] for r in clean if r["verdict"] == "FULL_GPU"),
                default=None,
            ),
            "qualified_near_limit_context": max(
                (r["context_tokens"] for r in clean if r["near_limit_qualified"]),
                default=None,
            ),
        }
    return models


def save(runtime: Path, measured: dict[str, Any]) -> None:
    """Atomically replace only the last explicit run; never merge unrelated dates."""
    models = _normalise(measured)
    path = _root(runtime, create=True)
    if path.is_symlink() or (path.exists() and (
        not path.is_file() or path.stat().st_mode & 0o077
    )):
        raise ValueError("rapport GPU non privé ou lié (0600 requis)")
    value = {
        "schema_version": 1,
        "source": SOURCE,
        "recorded_at": datetime.now(UTC).isoformat(),
        "models": models,
    }
    raw = (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    if len(raw) > MAX_REPORT_BYTES:
        raise ValueError("rapport GPU trop volumineux")
    temporary = path.with_name(path.name + "." + secrets.token_hex(8) + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as writer:
            writer.write(raw)
            writer.flush()
            os.fsync(writer.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _model_cards(models: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "alias": alias, "label": LABELS[alias],
            "status": "MEASURED" if alias in models else "NOT_MEASURED",
            **models.get(alias, {
                "near_limit_requested": False,
                "results": [],
                "largest_full_gpu_context": None,
                "qualified_near_limit_context": None,
            }),
        }
        for alias in ALIASES
    ]


def view(runtime: Path) -> dict[str, Any]:
    """No GPU calls, no model startup and no write. Reject untrusted on-disk data."""
    base = {
        "status": "NOT_MEASURED",
        "source": SOURCE,
        "recorded_at": None,
        "models": _model_cards({}),
        "hardware_certified": False,
        "note": "Mesures locales indicatives ; la réception Fedora reste humaine.",
    }
    try:
        path = _root(runtime, create=False)
        if not path.exists() and not path.is_symlink():
            return base
        if path.is_symlink():
            raise ValueError("rapport GPU lié")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as reader:
            info = os.fstat(reader.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
                raise ValueError("rapport GPU non privé")
            if info.st_size > MAX_REPORT_BYTES:
                raise ValueError("rapport GPU trop volumineux")
            raw = reader.read(MAX_REPORT_BYTES + 1)
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            raise ValueError("format de rapport GPU inconnu")
        if data.get("source") != SOURCE:
            raise ValueError("source de rapport GPU inconnue")
        instant = datetime.fromisoformat(data["recorded_at"])
        if instant.utcoffset() is None:
            raise ValueError("date de mesure non horodatée")
        age = datetime.now(UTC) - instant.astimezone(UTC)
        if age < timedelta(minutes=-5):
            raise ValueError("date de mesure future")
        models = _normalise({
            alias: {
                "model_alias": alias,
                "cloud_used": False, "config_modified": False,
                "near_limit_requested": row["near_limit_requested"],
                "results": row["results"],
            }
            for alias, row in data["models"].items()
        })
        base.update({
            "status": "STALE" if age > MAX_AGE else "MEASURED",
            "recorded_at": instant.astimezone(UTC).isoformat(),
            "models": _model_cards(models),
        })
    except (OSError, ValueError, KeyError, TypeError, OverflowError, AttributeError):
        base["status"] = "UNVERIFIED"
    return base
