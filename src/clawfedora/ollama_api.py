"""Small client for the local Ollama server (loopback only)."""

from __future__ import annotations

import json
from http.client import HTTPConnection, HTTPException
from typing import Any

ENDPOINT = "http://127.0.0.1:11434"
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
READ_PATHS = {"/api/version", "/api/tags", "/api/ps"}
WRITE_PATHS = {"/api/generate"}


def request_json(
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    # No environment proxy, URL credentials, redirect or model-provided destination.
    allowed = WRITE_PATHS if payload is not None else READ_PATHS
    if url not in {ENDPOINT + path for path in allowed}:
        raise ValueError("Destination Ollama locale non autorisée")
    path = url[len(ENDPOINT):]
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    method = "POST" if data is not None else "GET"
    client = HTTPConnection("127.0.0.1", 11434, timeout=timeout)
    try:
        client.request(method, path, body=data, headers={"Content-Type": "application/json"})
        response = client.getresponse()
        if response.status != 200:
            raise ValueError("Réponse HTTP Ollama refusée")
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("Réponse Ollama trop volumineuse")
        result = json.loads(raw)
    except HTTPException as exc:
        raise ValueError("Réponse HTTP Ollama interrompue") from exc
    finally:
        client.close()
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


def resident_model_alias(
    identities: list[dict[str, Any]], context_tokens: int,
) -> str | None:
    """Best-effort affinity hint from the one actually resident, verified local model.

    Never start or evict a model. A stale/malformed/unavailable inventory or a
    different context allocation gives no preference. The caller must have
    verified identities against the local lock and hold the worker lock.
    """
    try:
        loaded = request_json(ENDPOINT + "/api/ps", timeout=2).get("models")
        if not isinstance(loaded, list) or len(loaded) != 1:
            return None
        model = loaded[0]
        if not isinstance(model, dict):
            return None
        name = model.get("name") or model.get("model")
        if not isinstance(name, str) or not name:
            return None
        if any(model.get(key) not in (None, "", name) for key in ("name", "model")):
            return None
        digest = model.get("digest")
        if (
            not isinstance(digest, str) or not digest
            or type(model.get("context_length")) is not int
            or model["context_length"] != context_tokens
            or type(model.get("size")) is not int or model["size"] <= 0
        ):
            return None
        for identity in identities:
            if (
                identity.get("runtime_id") == name
                and identity.get("digest") == digest
                and identity.get("alias") in {"qwen-max", "ornith-code", "gemma-expert"}
            ):
                return str(identity["alias"])
    except (OSError, ValueError, TypeError, AttributeError):
        # The inventory is only a scheduling hint, not an authorization decision.
        return None
    return None
