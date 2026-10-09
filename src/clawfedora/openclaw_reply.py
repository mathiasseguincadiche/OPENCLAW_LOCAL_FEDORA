"""Read what the OpenClaw CLI returns: configured roles and the agent answer."""

from __future__ import annotations

import json
from typing import Any

from clawfedora.core_config import AGENT_IDS


def agent_entries(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    agents = config.get("agents", {})
    if not isinstance(agents, dict):
        raise ValueError("openclaw.json: agents invalide")
    canonical = agents.get("entries")
    if isinstance(canonical, dict):
        result = {
            str(key): dict(value, id=key)
            for key, value in canonical.items()
            if isinstance(value, dict)
        }
    else:
        entries = agents.get("list", [])
        if not isinstance(entries, list):
            raise ValueError("openclaw.json: roster invalide")
        result = {str(raw["id"]): raw for raw in entries if isinstance(raw, dict) and raw.get("id")}
    if set(result) != set(AGENT_IDS):
        raise ValueError(f"OpenClaw doit exposer exactement 7 agents: {sorted(result)}")
    return result


def visible_text(payload: dict[str, Any]) -> str:
    result = payload.get("result")
    if isinstance(result, dict):
        meta = result.get("meta")
        if isinstance(meta, dict):
            value = meta.get("finalAssistantVisibleText")
            if isinstance(value, str) and value.strip():
                return value.strip()
    final = payload.get("final")
    if isinstance(final, str) and final.strip():
        return final.strip()
    payloads = payload.get("payloads")
    if payloads is None and isinstance(result, dict):
        payloads = result.get("payloads")
    if isinstance(payloads, list):
        texts = [
            str(item.get("text", "")).strip()
            for item in payloads
            if isinstance(item, dict) and str(item.get("text", "")).strip()
        ]
        return "\n".join(texts)
    return ""


def assert_agent_success(
    payload: dict[str, Any], expected_provider: str, expected_model: str | None = None
) -> None:
    result = payload.get("result")
    if not isinstance(result, dict):
        raise ValueError("résultat agent absent")
    meta = result.get("meta")
    if not isinstance(meta, dict):
        raise ValueError("métadonnées agent absentes")
    error = meta.get("error")
    if isinstance(error, dict) and any(str(value).strip() for value in error.values()):
        raise RuntimeError(f"erreur agent OpenClaw: {error}")
    liveness = str(meta.get("livenessState", "")).casefold()
    if liveness in {"blocked", "error", "failed"}:
        raise RuntimeError(f"liveness agent invalide: {liveness}")
    status = str(payload.get("status", "")).casefold()
    if status and status != "ok":
        raise RuntimeError(f"status agent invalide: {status}")
    serialized = json.dumps(payload, ensure_ascii=False)
    agent_meta = meta.get("agentMeta", {})
    observed_provider = meta.get("provider") or (
        agent_meta.get("provider") if isinstance(agent_meta, dict) else None
    )
    if observed_provider != expected_provider:
        raise RuntimeError(f"preuve provider={expected_provider} absente")
    if expected_model is not None:
        observed_model = meta.get("model") or (
            agent_meta.get("model") if isinstance(agent_meta, dict) else None
        )
        if observed_model != expected_model:
            raise RuntimeError(f"preuve model={expected_model} absente")
    if '"transport":"embedded"' in serialized.replace(" ", ""):
        raise RuntimeError("transport embedded interdit: passer par le Gateway")
    if '"fallbackFrom":"gateway"' in serialized.replace(" ", ""):
        raise RuntimeError("fallback silencieux depuis Gateway interdit")
