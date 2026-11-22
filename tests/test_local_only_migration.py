"""Contract tests for the intentionally local-only workshop."""
from __future__ import annotations

from pathlib import Path

import pytest

from clawfedora.agents import load_agent_specs
from clawfedora.cloud_state import cloud_status, write_activation
from clawfedora.lifecycle import model_plan
from clawfedora.openclaw_config import build_openclaw_patch

ROOT = Path(__file__).resolve().parents[1]


def test_two_models_and_seven_specialists() -> None:
    assert [m["runtime_id"] for m in model_plan(ROOT)] == [
        "qwen3.5:9b-q4_K_M",
        "ornith-1.5:9b",
    ]
    roles = {s.agent_id: s.model for s in load_agent_specs(ROOT)}
    assert len(roles) == 7
    assert roles["ingenieur-devops"] == "ornith-code"
    assert set(v for k, v in roles.items() if k != "ingenieur-devops") == {"qwen-max"}


def test_openclaw_cannot_register_cloud_provider(tmp_path: Path) -> None:
    patch = build_openclaw_patch(ROOT, tmp_path)
    assert set(patch["models"]["providers"]) == {"ollama"}
    assert len(patch["models"]["providers"]["ollama"]["models"]) == 2
    assert patch["agents"]["entries"]["ingenieur-devops"]["model"]["primary"] == (
        "ollama/ornith-1.5:9b"
    )
    assert "cloudgw" not in patch["agents"]["defaults"]["modelPolicy"]["allow"]
    with pytest.raises(ValueError, match="OpenRouter retiré"):
        build_openclaw_patch(ROOT, tmp_path, cloud_enabled=True)


def test_old_activation_record_cannot_reenable_cloud(tmp_path: Path) -> None:
    write_activation(tmp_path, {
        "privacy_filter": "2026-11-22T10:00:00Z",
        "budget_guard": "2026-11-22T10:00:00Z",
    })
    assert cloud_status(tmp_path, ROOT) == (
        False, "OpenRouter retiré : atelier uniquement local"
    )
