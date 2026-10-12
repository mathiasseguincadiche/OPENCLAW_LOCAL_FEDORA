"""Shared specialist prompts must remain truthful on both inference routes."""

from __future__ import annotations

from pathlib import Path

from clawfedora.agents import effective_instructions, validate_agent_assets
from clawfedora.core_config import AGENT_IDS, core_contract

ROOT = Path(__file__).resolve().parents[1]


def test_shared_prompt_does_not_hardcode_local_inference_limits() -> None:
    tools = (ROOT / "agents/_shared/TOOLS.md").read_text(encoding="utf-8")
    assert "contexte 32768, sortie 4096" not in tools
    assert "dépendent de la route" in tools
    assert "ne pas imposer au cloud les plafonds du local" in tools
    assert not validate_agent_assets(ROOT)


def test_direct_teaching_has_no_arbitrary_depth_cap() -> None:
    text = (ROOT / "agents/_shared/PEDAGOGY.md").read_text(encoding="utf-8")
    assert "En guidé, limiter à trois notions" in text
    assert "En direct, expliquer aussi profondément que demandé" in text
    assert "exercice facultatif" in text


def test_no_provider_name_or_automatic_route_claim_in_shared_prompts() -> None:
    for role in AGENT_IDS:
        prompt = effective_instructions(ROOT, role)
        for forbidden in ("OpenRouter", "DeepSeek", "Qwen", "GLM-"):
            assert forbidden not in prompt, (role, forbidden)
        assert "Le modèle choisit le fournisseur" not in prompt
    route = core_contract(ROOT, "model_routing.yaml")["policy"]
    assert route["local_to_cloud_fallback"] == "forbidden"
