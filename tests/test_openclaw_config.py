from __future__ import annotations

import json
from pathlib import Path

import pytest

from clawfedora.openclaw_config import (
    _backend_ref,
    build_openclaw_patch,
    write_openclaw_patch,
)

ROOT = Path(__file__).resolve().parents[1]


def _agents_by_id(patch: dict[str, object]) -> dict[str, dict[str, object]]:
    agents_root = patch["agents"]
    assert isinstance(agents_root, dict)
    entries = agents_root["list"]
    assert isinstance(entries, list)
    return {
        str(entry["id"]): entry
        for entry in entries
        if isinstance(entry, dict) and "id" in entry
    }


def test_ollama_patch_has_eight_agents_and_strict_tools(tmp_path: Path) -> None:
    patch = build_openclaw_patch(ROOT, tmp_path, "ollama-vulkan")
    assert patch["gateway"] == {"mode": "local", "bind": "loopback"}
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
        "gemma3:12b-it-q4_K_M",
        "qwen2.5-coder:14b-instruct-q4_K_M",
    }
    assert all(entry["contextTokens"] == 8192 for entry in by_id.values())
    assert by_id["qwen2.5-coder:14b-instruct-q4_K_M"]["input"] == ["text"]

    agents = _agents_by_id(patch)
    assert len(agents) == 8
    assert agents["chef-operations"]["default"] is True
    assert agents["ingenieur-devops"]["model"] == {
        "primary": "ollama/qwen2.5-coder:14b-instruct-q4_K_M",
        "fallbacks": ["ollama/qwen3.5:9b-q4_K_M"],
    }
    research_tools = agents["expert-recherche"]["tools"]
    assert isinstance(research_tools, dict)
    assert "browser" in research_tools["alsoAllow"]
    security_tools = agents["ingenieur-securite"]["tools"]
    assert isinstance(security_tools, dict)
    assert "write" in security_tools["deny"]

    tools = patch["tools"]
    assert isinstance(tools, dict)
    assert tools["exec"] == {"mode": "ask", "applyPatch": {"workspaceOnly": True}}
    assert tools["elevated"] == {"enabled": False}
    web = tools["web"]
    assert isinstance(web, dict)
    search = web["search"]
    assert isinstance(search, dict)
    assert search["provider"] == "parallel-free"


def test_vulkan_candidate_keeps_multimodal_on_ollama(tmp_path: Path) -> None:
    patch = build_openclaw_patch(ROOT, tmp_path, "llama-cpp-vulkan")
    models = patch["models"]
    assert isinstance(models, dict)
    providers = models["providers"]
    assert isinstance(providers, dict)
    assert set(providers) == {"ollama", "intel-vulkan"}
    vulkan = providers["intel-vulkan"]
    assert isinstance(vulkan, dict)
    assert vulkan["apiKey"] == {
        "source": "env",
        "provider": "default",
        "id": "INTEL_VULKAN_API_KEY",
    }
    assert "intel-vulkan-local" not in json.dumps(patch)
    vulkan_models = vulkan["models"]
    assert isinstance(vulkan_models, list)
    assert all(
        isinstance(entry, dict) and entry["contextTokens"] == 8192
        for entry in vulkan_models
    )
    agents = _agents_by_id(patch)
    devops_model = agents["ingenieur-devops"]["model"]
    assert isinstance(devops_model, dict)
    assert devops_model["primary"] == (
        "intel-vulkan/qwen2.5-coder:14b-instruct-q4_K_M"
    )
    defaults = patch["agents"]
    assert isinstance(defaults, dict)
    agent_defaults = defaults["defaults"]
    assert isinstance(agent_defaults, dict)
    image_model = agent_defaults["imageModel"]
    assert isinstance(image_model, dict)
    assert image_model["primary"] == "ollama/qwen3.5:9b-q4_K_M"
    assert image_model["fallbacks"] == ["ollama/gemma3:12b-it-q4_K_M"]


def test_sycl_candidate_is_explicit_and_local(tmp_path: Path) -> None:
    patch = build_openclaw_patch(ROOT, tmp_path, "llama-cpp-sycl")
    models = patch["models"]
    assert isinstance(models, dict)
    providers = models["providers"]
    assert isinstance(providers, dict)
    sycl = providers["intel-sycl"]
    assert isinstance(sycl, dict)
    assert sycl["baseUrl"] == "http://127.0.0.1:8080/v1"
    assert sycl["api"] == "openai-completions"
    assert sycl["apiKey"] == {
        "source": "env",
        "provider": "default",
        "id": "INTEL_SYCL_API_KEY",
    }
    assert "intel-sycl-local" not in json.dumps(patch)


def test_unknown_backend_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="backend absent"):
        build_openclaw_patch(ROOT, tmp_path, "unknown")


def test_unknown_model_alias_is_contextualized() -> None:
    with pytest.raises(ValueError, match="missing-alias"):
        _backend_ref("missing-alias", {"models": {}}, "ollama-vulkan")


def test_patch_writer_is_atomic_json(tmp_path: Path) -> None:
    patch = build_openclaw_patch(ROOT, tmp_path, "ollama-vulkan")
    output = write_openclaw_patch(tmp_path / "generated" / "openclaw.patch.json", patch)
    assert json.loads(output.read_text(encoding="utf-8")) == patch
    assert not output.with_suffix(output.suffix + ".tmp").exists()
