"""Contrats anti-régression du mode Ollama exclusivement local.

Ces tests remplacent les tests d'activation/facturation de la route OpenRouter
retirée. Les outils spécialisés des sept agents et les validations restent inchangés.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from clawfedora.agents import load_agent_specs
from clawfedora.cloud_activation import enable, set_key
from clawfedora.cloud_cli import main as legacy_cloud_main
from clawfedora.cloud_gateway import make_server as legacy_gateway
from clawfedora.cloud_state import cloud_status
from clawfedora.core_config import core_contract, openclaw_environment, root_contract
from clawfedora.core_contracts import validate_core_contracts
from clawfedora.lifecycle import model_plan
from clawfedora.openclaw_config import build_openclaw_patch, prepare_migration_patch
from clawfedora.project_cloud import consent_state
from clawfedora.project_worker import openclaw_runner

ROOT = Path(__file__).resolve().parents[1]
QWEN = "qwen3.5:9b-q4_K_M"
ORNITH = "ornith-1.5:9b"
GEMMA = "gemma4:12b-it-q4_K_M"


def test_local_only_contracts_have_exactly_three_ollama_models() -> None:
    catalog = root_contract(ROOT, "model_catalog.yaml")
    assert set(catalog["models"]) == {"qwen-max", "ornith-code", "gemma-expert"}
    assert {model["provider"] for model in catalog["models"].values()} == {"ollama"}
    assert {model["runtime_id"] for model in catalog["models"].values()} == {QWEN, ORNITH, GEMMA}
    assert catalog["fleet_policy"]["exact_required_model_count"] == 3
    assert catalog["fleet_policy"]["local_only"] is True
    assert core_contract(ROOT, "cloud_policy.yaml")["policy"]["retired"] is True
    assert core_contract(ROOT, "model_routing.yaml")["policy"]["local_only"] is True
    assert [model["runtime_id"] for model in model_plan(ROOT)] == [QWEN, ORNITH, GEMMA]
    failures, _warnings = validate_core_contracts(ROOT)
    assert not failures


def test_exactly_one_specialist_uses_ornith() -> None:
    agents = load_agent_specs(ROOT)
    assert len(agents) == 7
    assert {a.agent_id for a in agents if a.model == "ornith-code"} == {"ingenieur-devops"}
    assert {a.agent_id for a in agents if a.model == "qwen-max"} == {"chef-operations"}
    assert len([a for a in agents if a.model == "gemma-expert"]) == 5
    routes = core_contract(ROOT, "model_routing.yaml")["agents"]
    assert set(routes) == {agent.agent_id for agent in agents}
    for agent in agents:
        assert routes[agent.agent_id]["local_primary"] == agent.model
        assert "cloud_primary" not in routes[agent.agent_id]


def test_generated_openclaw_patch_cannot_register_a_remote_provider(tmp_path: Path) -> None:
    config = build_openclaw_patch(ROOT, tmp_path)
    assert set(config["models"]["providers"]) == {"ollama"}
    ids = {m["id"] for m in config["models"]["providers"]["ollama"]["models"]}
    assert ids == {QWEN, ORNITH, GEMMA}
    for agent_id, spec in config["agents"]["entries"].items():
        expected = {"ingenieur-devops": ORNITH, "chef-operations": QWEN}.get(agent_id, GEMMA)
        assert spec["model"]["primary"] == f"ollama/{expected}"
        assert spec["model"]["fallbacks"] == []
    with pytest.raises(ValueError, match="OpenRouter retiré"):
        build_openclaw_patch(ROOT, tmp_path, cloud_enabled=True)
    assert "openrouter.ai" not in str(config).lower()


def test_legacy_cloud_approval_cannot_reactivate_remote_inference(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    project = tmp_path / "project"
    project.mkdir()
    (runtime / "state/cloud").mkdir(parents=True)
    (runtime / "state/cloud/activation.json").write_text('{"approved":true}')
    assert cloud_status(runtime, ROOT)[0] is False
    assert consent_state(ROOT, runtime, project)["state"] == "none"
    runner = openclaw_runner(runtime, ROOT)
    with pytest.raises(ValueError, match="route inconnue"):
        runner("chef-operations", "bonjour", "test", route="cloud")


def test_legacy_cloud_cli_and_direct_api_fail_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    assert legacy_cloud_main(["--root", str(ROOT), "status"]) == 2
    assert "OpenRouter retiré" in capsys.readouterr().out
    with pytest.raises(ValueError, match="OpenRouter retiré"):
        set_key(ROOT, tmp_path, "sk-or-placeholder-1234567890")
    with pytest.raises(ValueError, match="OpenRouter retiré"):
        enable(ROOT, tmp_path, key_limit_usd=1.0, prepaid=True, apply=True)
    with pytest.raises(ValueError, match="OpenRouter retiré"):
        legacy_gateway(
            ROOT, tmp_path, budget=None, activation_check=lambda: None,
        )


def test_openclaw_environment_never_inherits_remote_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret_should_not_be_forwarded")
    monkeypatch.setenv("CLAWFEDORA_CLOUD_GATEWAY_TOKEN", "old_gateway_token")
    environment = openclaw_environment(tmp_path)
    assert "OPENROUTER_API_KEY" not in environment
    assert "CLAWFEDORA_CLOUD_GATEWAY_TOKEN" not in environment


def test_migration_patch_retires_old_provider_without_deleting_user_work(
    tmp_path: Path,
) -> None:
    active = build_openclaw_patch(ROOT, tmp_path)
    migration = prepare_migration_patch(active)
    assert "cloudgw" not in active["models"]["providers"]
    assert migration["models"]["providers"].get("cloudgw") is None


def test_agent_tool_permissions_remain_strict() -> None:
    policy = core_contract(ROOT, "tool_policy.yaml")["agents"]
    assert len(policy) == 7
    for agent_id, tools in policy.items():
        assert {"exec", "edit", "apply_patch", "write", "process"} <= set(tools["deny"])
        assert tools["profile"] == "minimal", agent_id
