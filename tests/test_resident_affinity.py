"""The affinity hint never changes model routing, residency or permissions."""
from __future__ import annotations

from typing import Any

import pytest

from clawfedora import ollama_api

IDENTITIES = [
    {"alias": "qwen-max", "runtime_id": "qwen3.5:9b-q4_K_M", "digest": "a" * 64},
    {"alias": "ornith-code", "runtime_id": "ornith-1.5:9b", "digest": "b" * 64},
]


def _resident(identity: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": identity["runtime_id"], "model": identity["runtime_id"],
        "digest": identity["digest"], "context_length": 32768,
        "size": 8 * 1024**3,
    }


@pytest.mark.parametrize("identity", IDENTITIES)
def test_affinity_observes_only_the_local_resident_model(
    monkeypatch: pytest.MonkeyPatch, identity: dict[str, Any],
) -> None:
    def ps(url: str, *, timeout: float) -> dict[str, Any]:
        assert url == "http://127.0.0.1:11434/api/ps" and timeout == 2
        return {"models": [_resident(identity)]}

    monkeypatch.setattr(ollama_api, "request_json", ps)
    assert ollama_api.resident_model_alias(IDENTITIES, 32768) == identity["alias"]


@pytest.mark.parametrize("inventory", [
    {},
    {"models": []},
    {"models": "invalid"},
    {"models": [None]},
    {"models": [_resident(IDENTITIES[0]), _resident(IDENTITIES[1])]},
    {"models": [{**_resident(IDENTITIES[0]), "context_length": 8192}]},
    {"models": [{**_resident(IDENTITIES[0]), "context_length": None}]},
    {"models": [{**_resident(IDENTITIES[0]), "digest": "changed"}]},
    {"models": [{**_resident(IDENTITIES[0]), "name": "foreign:latest"}]},
    {"models": [{**_resident(IDENTITIES[0]), "size": 0}]},
    {"models": [{**_resident(IDENTITIES[0]), "size": True}]},
])
def test_unknown_residency_is_never_an_affinity_hint(
    monkeypatch: pytest.MonkeyPatch, inventory: dict[str, Any],
) -> None:
    monkeypatch.setattr(ollama_api, "request_json", lambda *a, **kw: inventory)
    assert ollama_api.resident_model_alias(IDENTITIES, 32768) is None


def test_unavailable_inventory_leaves_original_order(monkeypatch: pytest.MonkeyPatch) -> None:
    def unavailable(*_args: Any, **_kwargs: Any) -> Any:
        raise TimeoutError("Ollama inventory unavailable")

    monkeypatch.setattr(ollama_api, "request_json", unavailable)
    assert ollama_api.resident_model_alias(IDENTITIES, 32768) is None
