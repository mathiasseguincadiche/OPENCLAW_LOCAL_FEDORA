from __future__ import annotations

import json
from pathlib import Path

import pytest

from clawfedora.openclaw_config import (
    _model_ref,
    build_openclaw_patch,
    write_openclaw_patch,
)

ROOT = Path(__file__).resolve().parents[1]


def _agents_by_id(patch: dict[str, object]) -> dict[str, dict[str, object]]:
    agents_root = patch["agents"]
    assert isinstance(agents_root, dict)
    entries = agents_root["entries"]
    assert isinstance(entries, dict)
    return {key: dict(value) for key, value in entries.items() if isinstance(value, dict)}


def test_ollama_patch_has_seven_agents_and_strict_tools(tmp_path: Path) -> None:
    patch = build_openclaw_patch(ROOT, tmp_path)
    assert patch["gateway"] == {
        "mode": "local",
        "bind": "loopback",
        "controlUi": {"newSessionModelDefaults": "configured"},
    }
    assert patch["plugins"]["slots"]["memory"] == "none"
    assert patch["plugins"]["entries"]["memory-core"]["enabled"] is False
    models = patch["models"]
    assert isinstance(models, dict)
    providers = models["providers"]
    assert isinstance(providers, dict)
    assert set(providers) == {"ollama"}
    ollama = providers["ollama"]
    assert isinstance(ollama, dict)
    assert ollama["apiKey"] == {
        "source": "env",
        "provider": "default",
        "id": "OLLAMA_API_KEY",
    }
    assert "ollama-local" not in json.dumps(patch)

    provider_models = ollama["models"]
    assert isinstance(provider_models, list)
    by_id = {
        str(entry["id"]): entry
        for entry in provider_models
        if isinstance(entry, dict) and "id" in entry
    }
    assert set(by_id) == {
        "qwen3.5:9b-q4_K_M",
    }
    assert all(entry["contextTokens"] == 32768 for entry in by_id.values())
    assert all(entry["maxTokens"] == 4096 for entry in by_id.values())
    assert by_id["qwen3.5:9b-q4_K_M"]["input"] == ["text", "image"]

    agents = _agents_by_id(patch)
    assert len(agents) == 7
    assert agents["chef-operations"]["default"] is True
    assert agents["ingenieur-devops"]["model"] == {
        "primary": "ollama/qwen3.5:9b-q4_K_M",
        "fallbacks": [],
    }
    research_tools = agents["expert-recherche"]["tools"]
    assert isinstance(research_tools, dict)
    assert research_tools["profile"] == "minimal"
    assert "browser" not in research_tools["alsoAllow"]
    security_tools = agents["ingenieur-securite"]["tools"]
    assert isinstance(security_tools, dict)
    assert security_tools["profile"] == "minimal"
    assert "write" in security_tools["deny"]

    tools = patch["tools"]
    assert isinstance(tools, dict)
    assert tools["profile"] == "minimal"
    assert tools["exec"] == {"mode": "ask", "applyPatch": {"workspaceOnly": True}}
    assert tools["elevated"] == {"enabled": False}
    web = tools["web"]
    assert isinstance(web, dict)
    search = web["search"]
    assert isinstance(search, dict)
    assert search["provider"] == "parallel-free"


def test_unknown_model_alias_is_contextualized() -> None:
    with pytest.raises(ValueError, match="missing-alias"):
        _model_ref("missing-alias", {"models": {}})


def test_patch_writer_is_atomic_json(tmp_path: Path) -> None:
    patch = build_openclaw_patch(ROOT, tmp_path)
    output = write_openclaw_patch(tmp_path / "generated" / "openclaw.patch.json", patch)
    assert json.loads(output.read_text(encoding="utf-8")) == patch
    assert not output.with_suffix(output.suffix + ".tmp").exists()


def test_generated_configuration_contains_references_without_credential_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    value = "test-sensitive-value-must-never-be-persisted"
    monkeypatch.setenv("OLLAMA_API_KEY", value)
    patch = build_openclaw_patch(ROOT, tmp_path)
    assert value not in json.dumps(patch)
    providers = patch["models"]["providers"]
    assert providers["ollama"]["apiKey"]["id"] == "OLLAMA_API_KEY"
    assert set(providers) == {"ollama"}
