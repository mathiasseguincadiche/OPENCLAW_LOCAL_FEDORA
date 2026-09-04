from __future__ import annotations

import base64
import hashlib
import json
import platform
import statistics
import struct
import time
import urllib.error
import urllib.request
import zlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from clawfedora.core_config import root_contract


@dataclass(frozen=True)
class ChallengerModel:
    variant: str
    slot: str
    runtime_id: str
    quantization: str


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"L6 challenger: {label} doit être un objet")
    return value


def _loopback(endpoint: str) -> bool:
    parsed = urlparse(endpoint)
    return parsed.scheme == "http" and parsed.hostname == "127.0.0.1"


def challenger_plan(repo_root: Path, variant: str) -> ChallengerModel:
    normalized = variant.strip().casefold()
    if normalized not in {"incumbent", "challenger"}:
        raise ValueError("L6 challenger: variant attendu incumbent ou challenger")
    catalog = root_contract(repo_root, "model_catalog.yaml")
    policy = root_contract(repo_root, "optimization_policy.yaml")
    cfg = _mapping(policy.get("model_challenger"), "optimization.model_challenger")
    slot = str(cfg.get("slot", ""))
    if slot != "gemma-deep":
        raise ValueError("L6 challenger: slot doit rester gemma-deep")
    if normalized == "incumbent":
        model = _mapping(_mapping(catalog.get("models"), "models").get(slot), slot)
        runtime_id = str(model.get("runtime_id", ""))
        quantization = str(model.get("quantization", ""))
        if runtime_id != str(cfg.get("incumbent", "")):
            raise ValueError("L6 challenger: incumbent divergent du catalogue")
    else:
        challengers = _mapping(catalog.get("challengers"), "challengers")
        slot_challengers = _mapping(challengers.get(slot), f"challengers.{slot}")
        matches = [
            raw
            for raw in slot_challengers.values()
            if isinstance(raw, dict) and raw.get("runtime_id") == cfg.get("challenger")
        ]
        if len(matches) != 1:
            raise ValueError("L6 challenger: Ministral doit être l'unique challenger attendu")
        model = matches[0]
        runtime_id = str(model.get("runtime_id", ""))
        quantization = str(model.get("quantization", ""))
        if model.get("promotion") != "benchmark-only" or model.get("automatic_promotion") is not False:
            raise ValueError("L6 challenger: Ministral doit rester benchmark-only sans auto-promotion")
    if not runtime_id or not quantization:
        raise ValueError("L6 challenger: identité modèle incomplète")
    return ChallengerModel(normalized, slot, runtime_id, quantization)


def provision_challenger_plan(repo_root: Path) -> dict[str, Any]:
    model = challenger_plan(repo_root, "challenger")
    return {
        "variant": model.variant,
        "slot": model.slot,
        "runtime_id": model.runtime_id,
        "quantization": model.quantization,
        "provider": "ollama",
        "routed": False,
        "counts_toward_required_fleet": False,
        "automatic_promotion": False,
        "explicit_pull_only": True,
    }


def _request_json(url: str, *, timeout: float = 10.0) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
        value = json.loads(response.read().decode("utf-8"))
    return _mapping(value, url)


def _inventory(endpoint: str, model: ChallengerModel) -> dict[str, Any]:
    tags = _request_json(f"{endpoint.rstrip('/')}/api/tags")
    raw_models = tags.get("models", [])
    if not isinstance(raw_models, list):
        raise ValueError("L6 challenger: inventaire Ollama invalide")
    selected: dict[str, Any] | None = None
    for raw in raw_models:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or raw.get("model") or "")
        if name.casefold() == model.runtime_id.casefold():
            selected = raw
            break
    if selected is None:
        raise ValueError(
            f"L6 challenger: modèle absent, aucun téléchargement implicite: {model.runtime_id}"
        )
    details = selected.get("details", {})
    details = details if isinstance(details, dict) else {}
    digest = str(selected.get("digest") or "")
    observed_quant = str(details.get("quantization_level") or "")
    if not digest or observed_quant != model.quantization:
        raise ValueError(
            f"L6 challenger: identité/quantification Ollama invalide pour {model.runtime_id}"
        )
    return {
        "runtime_id": model.runtime_id,
        "digest": digest,
        "quantization": observed_quant,
    }


def _png_blue_square() -> bytes:
    width = 64
    height = 64
    row = b"\x00" + (b"\x00\x00\xff" * width)
    raw = row * height

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, level=9))
        + chunk(b"IEND", b"")
    )


def _probe_definitions() -> tuple[dict[str, Any], ...]:
    document = (
        "Document incident: service=openclaw; severity=high; decision=rollback. "
        "Retourne uniquement un objet JSON avec exactement les clés service, severity, decision "
        "et les valeurs du document."
    )
    tool_prompt = (
        "Enregistre l'incident du service openclaw avec severity high en appelant exactement "
        "l'outil record_incident. N'invente aucun autre champ."
    )
    vision_prompt = (
        "Observe l'image jointe. Réponds uniquement BLUE_SQUARE si elle montre un carré bleu uni."
    )
    return (
        {"id": "document-quality", "prompt": document},
        {"id": "tool-calling", "prompt": tool_prompt},
        {"id": "vision", "prompt": vision_prompt},
    )


def _tool_schema() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "record_incident",
                "description": "Record one incident",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "service": {"type": "string"},
                        "severity": {"type": "string"},
                    },
                    "required": ["service", "severity"],
                    "additionalProperties": False,
                },
            },
        }
    ]


def _chat_probe(
    endpoint: str,
    model: ChallengerModel,
    probe: dict[str, Any],
    *,
    timeout: float = 210.0,
) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "user", "content": str(probe["prompt"])}
    if probe["id"] == "vision":
        message["images"] = [base64.b64encode(_png_blue_square()).decode("ascii")]
    payload: dict[str, Any] = {
        "model": model.runtime_id,
        "messages": [message],
        "stream": True,
        "options": {"num_ctx": 8192, "num_predict": 256, "temperature": 0.0},
    }
    if probe["id"] == "tool-calling":
        payload["tools"] = _tool_schema()
    request = urllib.request.Request(
        f"{endpoint.rstrip('/')}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    first: float | None = None
    content: list[str] = []
    tool_calls: list[Any] = []
    final: dict[str, Any] = {}
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        for raw in response:
            line = raw.decode("utf-8").strip()
            if not line:
                continue
            event = _mapping(json.loads(line), "Ollama stream event")
            message_raw = event.get("message", {})
            message_obj = message_raw if isinstance(message_raw, dict) else {}
            chunk = str(message_obj.get("content") or "")
            calls = message_obj.get("tool_calls", [])
            calls = calls if isinstance(calls, list) else []
            if (chunk or calls) and first is None:
                first = time.perf_counter()
            content.append(chunk)
            tool_calls.extend(calls)
            if event.get("done") is True:
                final = event
    ended = time.perf_counter()
    eval_count = int(final.get("eval_count") or 0)
    eval_duration = int(final.get("eval_duration") or 0)
    if first is None or eval_count <= 0 or eval_duration <= 0:
        raise ValueError("L6 challenger: métriques Ollama incomplètes")
    output = "".join(content).strip()
    return {
        "output": output,
        "tool_calls": tool_calls,
        "first_token_ms": (first - started) * 1000,
        "wall_ms": (ended - started) * 1000,
        "tokens_per_second": eval_count / eval_duration * 1_000_000_000,
        "output_tokens": eval_count,
        "finish_reason": final.get("done_reason"),
    }


def _evaluate_probe(probe_id: str, output: str, tool_calls: list[Any]) -> tuple[bool, str]:
    if probe_id == "vision":
        passed = output.strip() == "BLUE_SQUARE"
        return passed, "exact BLUE_SQUARE" if passed else "vision marker mismatch"
    if probe_id == "document-quality":
        try:
            value = json.loads(output)
        except json.JSONDecodeError:
            return False, "document output is not JSON"
        passed = value == {
            "service": "openclaw",
            "severity": "high",
            "decision": "rollback",
        }
        return passed, "exact document extraction" if passed else "document extraction mismatch"
    if probe_id == "tool-calling":
        for raw in tool_calls:
            if not isinstance(raw, dict):
                continue
            function = raw.get("function", {})
            if not isinstance(function, dict) or function.get("name") != "record_incident":
                continue
            arguments = function.get("arguments", {})
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    continue
            if isinstance(arguments, dict) and arguments == {
                "service": "openclaw",
                "severity": "high",
            }:
                return True, "record_incident exact arguments"
        return False, "required tool call absent or invalid"
    raise ValueError(f"L6 challenger: probe inconnue: {probe_id}")


def _vram_mib() -> float:
    values: list[int] = []
    for path in Path("/sys/class/drm").glob("card*/device/mem_info_vram_used"):
        try:
            values.append(int(path.read_text(encoding="utf-8").strip()))
        except (OSError, ValueError):
            continue
    if not values:
        raise ValueError("L6 challenger: télémétrie VRAM xe indisponible")
    return max(values) / (1024 * 1024)


def _ram_mib() -> float:
    fields: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        key, _, raw = line.partition(":")
        if key in {"MemTotal", "MemAvailable"}:
            fields[key] = int(raw.strip().split()[0])
    if set(fields) != {"MemTotal", "MemAvailable"}:
        raise ValueError("L6 challenger: télémétrie RAM indisponible")
    return (fields["MemTotal"] - fields["MemAvailable"]) / 1024


def _p95(values: list[float]) -> float:
    if not values:
        return float("inf")
    ordered = sorted(values)
    index = max(0, (95 * len(ordered) + 99) // 100 - 1)
    return ordered[index]


def run_challenger_snapshot(
    repo_root: Path,
    *,
    variant: str,
    endpoint: str,
    output: Path,
) -> Path:
    if not _loopback(endpoint):
        raise ValueError("L6 challenger: endpoint doit être http://127.0.0.1")
    model = challenger_plan(repo_root, variant)
    identity = _inventory(endpoint, model)
    _request_json(f"{endpoint.rstrip('/')}/api/version")
    cases: list[dict[str, Any]] = []
    for probe in _probe_definitions():
        started = time.perf_counter()
        try:
            result = _chat_probe(endpoint, model, probe)
            output_text = str(result.pop("output"))
            tool_calls = result.pop("tool_calls")
            tool_calls = tool_calls if isinstance(tool_calls, list) else []
            passed, detail = _evaluate_probe(str(probe["id"]), output_text, tool_calls)
            status = "ok" if passed else "check-failed"
            error: str | None = None
        except (
            OSError,
            TimeoutError,
            urllib.error.URLError,
            json.JSONDecodeError,
            ValueError,
        ) as exc:
            output_text = ""
            result = {
                "first_token_ms": None,
                "wall_ms": (time.perf_counter() - started) * 1000,
                "tokens_per_second": None,
                "output_tokens": 0,
                "finish_reason": None,
            }
            detail = f"{type(exc).__name__}: {exc}"
            status = "error"
            error = str(exc)
        vram = _vram_mib()
        ram = _ram_mib()
        cases.append(
            {
                "model_alias": model.slot,
                "runtime_id": model.runtime_id,
                "probe_id": probe["id"],
                "context": 8192,
                "prompt_sha256": hashlib.sha256(str(probe["prompt"]).encode("utf-8")).hexdigest(),
                "status": status,
                "check_passed": status == "ok",
                "check_detail": detail,
                "error": error,
                "output_sha256": hashlib.sha256(output_text.encode("utf-8")).hexdigest(),
                "output_chars": len(output_text),
                "vram_mib": vram,
                "ram_mib": ram,
                **result,
            }
        )
    rates = [
        float(item["tokens_per_second"])
        for item in cases
        if isinstance(item.get("tokens_per_second"), (int, float))
    ]
    first_tokens = [
        float(item["first_token_ms"])
        for item in cases
        if isinstance(item.get("first_token_ms"), (int, float))
    ]
    flags = {
        "document_quality_pass": any(
            item["probe_id"] == "document-quality" and item["status"] == "ok" for item in cases
        ),
        "tool_calling_pass": any(
            item["probe_id"] == "tool-calling" and item["status"] == "ok" for item in cases
        ),
        "vision_pass": any(
            item["probe_id"] == "vision" and item["status"] == "ok" for item in cases
        ),
    }
    errors = sum(item["status"] != "ok" for item in cases)
    model_payload = {
        model.slot: {
            **identity,
            "median_tokens_per_second": statistics.median(rates) if rates else 0.0,
            "p95_first_token_ms": _p95(first_tokens),
            "vram_mib": max(float(item["vram_mib"]) for item in cases),
            "ram_mib": max(float(item["ram_mib"]) for item in cases),
            "error_rate": errors / len(cases),
        }
    }
    payload = {
        "schema_version": "1.0.0",
        "run_id": datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ"),
        "created_at": datetime.now(UTC).isoformat(),
        "kind": "model-challenger",
        "candidate_id": model.runtime_id,
        "variant": model.variant,
        "kernel": platform.release(),
        "backend": "ollama-vulkan",
        "models": model_payload,
        "contexts": [8192],
        "prompt_hashes": sorted(str(item["prompt_sha256"]) for item in cases),
        "functional_pass": all(item["status"] == "ok" for item in cases),
        "security_pass": True,
        **flags,
        "metrics": {
            "cases": len(cases),
            "passed_cases": sum(item["status"] == "ok" for item in cases),
            "max_vram_mib": max(float(item["vram_mib"]) for item in cases),
            "max_ram_mib": max(float(item["ram_mib"]) for item in cases),
        },
        "cases": cases,
        "raw_outputs_persisted": False,
        "cloud_calls_allowed": False,
        "routed": False if model.variant == "challenger" else True,
        "automatic_promotion": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output
