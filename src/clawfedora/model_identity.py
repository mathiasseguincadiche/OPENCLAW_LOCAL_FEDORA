"""Explicit adoption and subsequent exact verification of mutable Ollama tags."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from clawfedora import ollama_api
from clawfedora.project_common import read_json, write_json


def verify_model_lock(runtime: Path, identities: list[dict[str, Any]]) -> None:
    path = runtime / "state/model-identities.json"
    if not path.is_file():
        raise ValueError("identité non adoptée: clawfedora-ops models-lock --apply requis")
    locked = read_json(path).get("models", {})
    for model in identities:
        previous = locked.get(model["runtime_id"], {})
        if (
            previous.get("digest") != model["digest"]
            or previous.get("quantization_level") != model["quantization_level"]
        ):
            raise ValueError(f"identité modifiée/non adoptée: {model['runtime_id']}")


def adopt_model_lock(runtime: Path, required: list[dict[str, Any]]) -> Path:
    tags = ollama_api.request_json(ollama_api.ENDPOINT + "/api/tags")
    identities = ollama_api.model_inventory(tags, required)
    for model in identities:
        if not re.fullmatch(r"(?:sha256:)?[0-9a-f]{64}", str(model["digest"])):
            raise ValueError("digest SHA-256 invalide")
    path = runtime / "state/model-identities.json"
    existing = read_json(path).get("models", {}) if path.exists() else {}
    for item in identities:
        previous = existing.get(item["runtime_id"])
        if previous and (
            previous["digest"] != item["digest"]
            or previous["quantization_level"] != item["quantization_level"]
        ):
            raise ValueError(
                f"digest déjà adopté divergent: {item['runtime_id']}; "
                "adoption explicite requise après vérification"
            )
        existing[item["runtime_id"]] = item
    write_json(path, {"schema_version": "1.0.0", "models": existing})
    path.chmod(0o600)
    return path
