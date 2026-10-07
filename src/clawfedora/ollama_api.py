"""Small client for the local Ollama server (loopback only)."""

from __future__ import annotations

import json
import urllib.request
from typing import Any

ENDPOINT = "http://127.0.0.1:11434"


def request_json(
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    method = "POST" if data is not None else "GET"
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        result = json.loads(response.read().decode("utf-8"))
    if not isinstance(result, dict):
        raise ValueError(f"réponse JSON non objet: {url}")
    return result


def model_inventory(
    tags: dict[str, Any],
    required: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    raw_models = tags.get("models", [])
    if not isinstance(raw_models, list):
        raise ValueError("Ollama /api/tags: models invalide")
    indexed: dict[str, dict[str, Any]] = {}
    for raw in raw_models:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or raw.get("model") or "")
        if name:
            indexed[name.casefold()] = raw
    inventory: list[dict[str, Any]] = []
    for model in required:
        runtime_id = str(model["runtime_id"])
        raw = indexed.get(runtime_id.casefold())
        if raw is None:
            raise ValueError(f"modèle requis absent, aucun download implicite: {runtime_id}")
        details = raw.get("details", {})
        if not isinstance(details, dict):
            details = {}
        digest = str(raw.get("digest") or "")
        quantization = str(details.get("quantization_level") or "")
        if quantization.upper() != str(model.get("quantization", "Q4_K_M")).upper():
            raise ValueError(f"quantization divergente: {runtime_id}: {quantization}")
        if not digest or not quantization:
            raise ValueError(f"identité Ollama incomplète: {runtime_id}")
        inventory.append(
            {
                "alias": model["alias"],
                "runtime_id": runtime_id,
                "digest": digest,
                "size": int(raw.get("size") or 0),
                "format": details.get("format"),
                "family": details.get("family"),
                "parameter_size": details.get("parameter_size"),
                "quantization_level": quantization,
            }
        )
    return inventory
