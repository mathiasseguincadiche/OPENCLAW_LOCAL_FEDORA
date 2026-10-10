"""The cloud is an opt-in route through one loopback gateway; nothing may enable it silently."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from clawfedora.core_config import AGENT_IDS
from clawfedora.core_contracts import validate_core_contracts
from clawfedora.openclaw_config import (
    build_openclaw_patch,
    cloud_model_ref,
    prepare_migration_patch,
)

ROOT = Path(__file__).resolve().parents[1]
Mutation = Callable[[dict[str, Any]], None]


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    for folder in ("agents", "config", "plugins"):
        shutil.copytree(ROOT / folder, root / folder)
    shutil.copy(ROOT / "VERSION", root / "VERSION")
    return root


def _edit(repo: Path, relative: str, change: Mutation) -> None:
    path = repo / relative
    data = yaml.safe_load(path.read_text())
    change(data)
    path.write_text(yaml.safe_dump(data))


def test_shipped_contracts_are_valid() -> None:
    failures, _ = validate_core_contracts(ROOT)
    assert failures == ()


@pytest.mark.parametrize(
    ("relative", "change", "expected"),
    [
        ("config/core/model_routing.yaml",
         lambda d: d["policy"].update(cloud_enabled_by_default=True), "désactivé par défaut"),
        ("config/core/cloud_policy.yaml",
         lambda d: d["policy"].update(enabled_by_default=True), "désactivé par défaut"),
        ("config/model_catalog.yaml",
         lambda d: d["fleet_policy"].update(cloud_enabled_by_default=True), "désactivé par défaut"),
        ("config/core/model_routing.yaml",
         lambda d: d["policy"].update(local_to_cloud_fallback="allowed"), "aucun repli"),
        ("config/model_catalog.yaml",
         lambda d: d["fleet_policy"].update(cloud_model_as_local_fallback=True), "aucun repli"),
        ("config/core/cloud_policy.yaml",
         lambda d: d["policy"].update(cloud_to_local_fallback="silent"), "repli cloud vers local"),
        ("config/core/cloud_policy.yaml",
         lambda d: d["policy"].update(requires=["privacy_filter"]), "tous deux requis"),
        ("config/core/cloud_policy.yaml",
         lambda d: d["gateway"].update(host="0.0.0.0"), "127.0.0.1"),
        ("config/core/cloud_policy.yaml",
         lambda d: d["gateway"].update(port=11434), "port de passerelle"),
        ("config/core/cloud_policy.yaml",
         lambda d: d["gateway"].update(upstream_key_file="/etc/openrouter.key"), "relatif"),
        ("config/core/cloud_policy.yaml",
         lambda d: d["gateway"].update(upstream_key_file="../key"), "relatif"),
        ("config/core/cloud_policy.yaml",
         lambda d: d["gateway"].update(upstream_key_file="cloud/upstream.txt"), "sauvegardes"),
        ("config/core/cloud_policy.yaml",
         lambda d: d["gateway"].update(upstream_key_file="other/upstream.key"), "sauvegardes"),
        ("config/core/cloud_policy.yaml",
         lambda d: d["gateway"].update(token_env="sk-or-literal"), "token_env"),
        ("config/core/cloud_policy.yaml",
         lambda d: d["gateway"].update(token_env="OTHER_TOKEN"), "token_env"),
        ("config/core/cloud_policy.yaml",
         lambda d: d["model"].update(context_tokens=131072), "limites quotidiennes"),
        ("config/core/cloud_policy.yaml",
         lambda d: d["model"].update(pricing_usd_per_million={"input": 0, "output": 1}),
         "tarifs"),
        ("config/core/cloud_policy.yaml",
         lambda d: d["upstream_params"]["provider"].update(data_collection="allow"),
         "data_collection"),
        ("config/core/cloud_policy.yaml",
         lambda d: d["upstream_params"]["provider"].update(require_parameters=False),
         "require_parameters"),
        ("config/core/cloud_policy.yaml",
         lambda d: d["policy"].update(provider_id="openrouter"), "cloudgw"),
        ("config/core/cloud_policy.yaml",
         lambda d: d["budget"].update(monthly_cap_eur=26), "plafond mensuel"),
        ("config/core/cloud_policy.yaml",
         lambda d: d["budget"].update(monthly_cap_eur=0), "plafond mensuel"),
        ("config/core/cloud_policy.yaml",
         lambda d: d["budget"].update(eur_per_usd=0.9), "eur_per_usd"),
        ("config/core/cloud_policy.yaml",
         lambda d: d["budget"].update(alert_ratio=1.2), "alert_ratio"),
        ("config/core/cloud_policy.yaml",
         lambda d: d["budget"].update(recommended_key_limit_usd=30), "limite de clé"),
        ("config/core/cloud_policy.yaml",
         lambda d: d["budget"].update(ledger_file="/etc/ledger.jsonl"), "journal de budget"),
        ("config/core/cloud_policy.yaml",
         lambda d: d["budget"].update(ledger_file="cloud/ledger.jsonl"), "journal de budget"),
        ("config/core/cloud_policy.yaml",
         lambda d: d["upstream"].update(base_url="http://openrouter.ai/api/v1"), "base_url"),
        ("config/core/cloud_policy.yaml",
         lambda d: d["upstream"].update(base_url="https://evil.example/api/v1"), "base_url"),
        ("config/core/cloud_policy.yaml",
         lambda d: d["limits"].update(max_request_bytes=0), "limites de requête"),
        ("config/model_catalog.yaml",
         lambda d: d["models"]["cloud-main"].update(required=True), "modèle cloud"),
        ("config/model_catalog.yaml",
         lambda d: d["models"]["cloud-main"].update(provider="openrouter"), "modèle cloud"),
        ("config/core/model_routing.yaml",
         lambda d: d["agents"]["chef-operations"].pop("cloud_primary"), "route cloud divergente"),
    ],
)
def test_cloud_contract_cannot_change_silently(
    repo: Path, relative: str, change: Mutation, expected: str
) -> None:
    _edit(repo, relative, change)
    failures, _ = validate_core_contracts(repo)
    assert any(expected in failure for failure in failures), failures


def test_default_configuration_has_no_cloud_provider() -> None:
    patch = build_openclaw_patch(ROOT, Path("/runtime"))
    assert set(patch["models"]["providers"]) == {"ollama"}
    allowed = patch["agents"]["defaults"]["modelPolicy"]["allow"]
    assert allowed == [patch["agents"]["defaults"]["model"]["primary"]]
    assert "cloudgw" not in json.dumps(patch)


def test_enabled_configuration_routes_the_cloud_through_the_loopback_gateway() -> None:
    patch = build_openclaw_patch(ROOT, Path("/runtime"), cloud_enabled=True)
    provider = patch["models"]["providers"]["cloudgw"]
    assert provider["baseUrl"] == "http://127.0.0.1:18892/v1"
    assert provider["api"] == "openai-completions"
    # Only the name of a local token variable: no upstream credential can be persisted.
    assert provider["apiKey"] == {
        "source": "env", "provider": "default", "id": "CLAWFEDORA_CLOUD_GATEWAY_TOKEN",
    }
    serialized = json.dumps(patch)
    assert "openrouter.ai" not in serialized and "sk-or" not in serialized
    (model,) = provider["models"]
    assert model["id"] == "deepseek/deepseek-v4.1-flash"
    assert model["contextTokens"] == 32768 and model["maxTokens"] == 4096
    assert model["cost"] == {"input": 0.15, "output": 0.5, "cacheRead": 0, "cacheWrite": 0}
    defaults = patch["agents"]["defaults"]
    assert defaults["modelPolicy"]["allow"] == [
        defaults["model"]["primary"], "cloudgw/deepseek/deepseek-v4.1-flash",
    ]
    # Every role keeps the local model as its only primary: cloud is chosen per run.
    for agent in AGENT_IDS:
        entry = patch["agents"]["entries"][agent]
        assert entry["model"] == {"primary": defaults["model"]["primary"], "fallbacks": []}


def test_cloud_model_reference_matches_the_policy() -> None:
    from clawfedora.core_config import core_contract

    assert cloud_model_ref(core_contract(ROOT, "cloud_policy.yaml")) == "cloudgw/deepseek/deepseek-v4.1-flash"


def test_disabling_the_cloud_retires_its_provider_from_an_existing_installation() -> None:
    off = prepare_migration_patch(build_openclaw_patch(ROOT, Path("/runtime")))
    assert off["models"]["providers"]["cloudgw"] is None
    on = prepare_migration_patch(build_openclaw_patch(ROOT, Path("/runtime"), cloud_enabled=True))
    assert isinstance(on["models"]["providers"]["cloudgw"], dict)
