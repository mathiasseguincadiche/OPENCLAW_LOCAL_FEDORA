"""Local inference is not offline operation: Web/GitHub/Notion access remains enabled."""
from __future__ import annotations

from pathlib import Path

from clawfedora.core_config import AGENT_IDS, core_contract
from clawfedora.openclaw_config import build_openclaw_patch

ROOT = Path(__file__).resolve().parents[1]


def test_local_only_inference_keeps_web_research_for_every_specialist(tmp_path: Path) -> None:
    web = core_contract(ROOT, "web_policy.yaml")["nominal_path"]
    assert web["web_search_enabled"] is True
    assert web["web_fetch_enabled"] is True
    assert web["search_provider"] == "parallel-free"
    result = build_openclaw_patch(ROOT, tmp_path)
    assert set(result["models"]["providers"]) == {"ollama"}
    for role in AGENT_IDS:
        tools = result["agents"]["entries"][role]["tools"]
        assert {"web_search", "web_fetch"} <= set(tools["alsoAllow"])
        assert {"web_search", "web_fetch"}.isdisjoint(tools["deny"])
    assert "clawfedora_sandbox_validate" in result["agents"]["entries"][
        "ingenieur-devops"
    ]["tools"]["alsoAllow"]
    assert all(
        "clawfedora_sandbox_validate" not in spec["tools"]["alsoAllow"]
        for role, spec in result["agents"]["entries"].items()
        if role != "ingenieur-devops"
    )


def test_ollama_no_cloud_does_not_disable_openclaw_web_tools() -> None:
    service = (ROOT / "scripts/linux/11_daily_profile.sh").read_text(encoding="utf-8")
    assert 'Environment="OLLAMA_NO_CLOUD=1"' in service
    assert "OLLAMA_KV_CACHE_TYPE=f16" in service
    assert "OLLAMA_KV_CACHE_TYPE=q8_0" in service
    assert "OLLAMA_FLASH_ATTENTION=1" in service
    assert "CLAWFEDORA_KV_CACHE_TYPE" in service
