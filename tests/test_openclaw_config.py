from __future__ import annotations

import json
from pathlib import Path

import pytest

from clawfedora.openclaw_config import build_openclaw_patch, write_openclaw_patch

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

    agents = _agents_by_id(patch)
    assert len(agents) == 8
    assert agents["chef-operations"]["default"] is True
    assert agents["ingenieur-devops"]["model"] == {
        "primary": "ollama/devstral-small-2:24b",
        "fallbacks": ["ollama/qwen3.8:27b"],
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
    agents = _agents_by_id(patch)
    devops_model = agents["ingenieur-devops"]["model"]
    assert isinstance(devops_model, dict)
    assert devops_model["primary"] == "intel-vulkan/devstral-small-2:24B"
    defaults = patch["agents"]
    assert isinstance(defaults, dict)
    agent_defaults = defaults["defaults"]
    assert isinstance(agent_defaults, dict)
    image_model = agent_defaults["imageModel"]
    assert isinstance(image_model, dict)
    assert str(image_model["primary"]).startswith("ollama/")


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


def test_unknown_backend_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="backend absent"):
        build_openclaw_patch(ROOT, tmp_path, "unknown")


def test_patch_writer_is_atomic_json(tmp_path: Path) -> None:
    patch = build_openclaw_patch(ROOT, tmp_path, "ollama-vulkan")
    output = write_openclaw_patch(tmp_path / "generated" / "openclaw.patch.json", patch)
    assert json.loads(output.read_text(encoding="utf-8")) == patch
    assert not output.with_suffix(output.suffix + ".tmp").exists()
