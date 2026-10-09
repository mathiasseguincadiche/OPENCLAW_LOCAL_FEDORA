from __future__ import annotations

import os
from pathlib import Path
from typing import Any, cast

import yaml

AGENT_IDS = (
    "chef-operations",
    "expert-recherche",
    "architecte-solutions",
    "ingenieur-devops",
    "ingenieur-securite",
    "redacteur-pedagogique",
    "auditeur-qualite",
)


# Provider id under which OpenClaw sees the local cloud gateway (config/core/cloud_policy.yaml).
CLOUD_PROVIDER_ID = "cloudgw"
# Variable holding the local token between OpenClaw and the gateway (never an upstream key).
CLOUD_TOKEN_ENV = "CLAWFEDORA_CLOUD_GATEWAY_TOKEN"


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        payload: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"YAML illisible: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"YAML invalide: {path}: racine non mapping")
    return cast(dict[str, Any], payload)


def core_contract(repo_root: Path, name: str) -> dict[str, Any]:
    path = repo_root / "config" / "core" / name
    if not path.is_file():
        raise FileNotFoundError(path)
    return load_yaml(path)


def root_contract(repo_root: Path, name: str) -> dict[str, Any]:
    path = repo_root / "config" / name
    if not path.is_file():
        raise FileNotFoundError(path)
    return load_yaml(path)


def daily_limits(repo_root: Path) -> dict[str, Any]:
    """Daily limits: the single source for context, answer length and injected prompts."""
    agents = core_contract(repo_root, "openclaw_policy.yaml").get("agents")
    webui = root_contract(repo_root, "webui_policy.yaml")
    if not isinstance(agents, dict):
        raise ValueError("openclaw_policy.yaml: agents doit être un mapping")
    limits: dict[str, Any] = {
        "context_tokens": int(agents.get("context_tokens", 0) or 0),
        "max_output_tokens": int(agents.get("max_output_tokens", 0) or 0),
        "keep_alive": str(agents.get("keep_alive", "")),
        "bootstrap_max_chars": int(agents.get("bootstrap_max_chars", 0) or 0),
        "bootstrap_total_max_chars": int(agents.get("bootstrap_total_max_chars", 0) or 0),
        "max_history_bytes": int(webui.get("max_history_bytes", 0) or 0),
    }
    if not all(limits.values()):
        raise ValueError("limites quotidiennes incomplètes: openclaw_policy.yaml / webui_policy.yaml")
    if int(webui.get("max_response_tokens", 0) or 0) != limits["max_output_tokens"]:
        raise ValueError("webui_policy.yaml: max_response_tokens doit égaler max_output_tokens")
    fleet = root_contract(repo_root, "model_catalog.yaml").get("fleet_policy")
    declared = fleet.get("openclaw_agent_context_tokens") if isinstance(fleet, dict) else None
    if declared != limits["context_tokens"]:
        raise ValueError(
            "model_catalog.yaml: openclaw_agent_context_tokens doit égaler le contexte quotidien"
        )
    if limits["max_output_tokens"] * 2 > limits["context_tokens"]:
        raise ValueError("limites quotidiennes: la sortie ne peut dépasser la moitié du contexte")
    return limits


def resolve_runtime_root(explicit: str | Path | None = None) -> Path:
    if explicit is not None:
        return Path(explicit).expanduser().resolve()
    configured = os.environ.get("OPENCLAW_LOCAL_FEDORA_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    preferred = Path("/srv/openclaw-local")
    if preferred.is_dir():
        return preferred.resolve()
    return (Path.home() / ".local" / "share" / "openclaw-local").resolve()


def openclaw_environment(runtime: Path | None = None) -> dict[str, str]:
    root = runtime or resolve_runtime_root()
    env = dict(os.environ)
    env.pop("OPENCLAW_CONFIG_PATH", None)
    env.update(
        PATH=os.pathsep.join(
            [str(Path.home() / ".openclaw/bin"), str(Path.home() / ".local/bin"), env.get("PATH", "")]
        ),
        OPENCLAW_STATE_DIR=str(root / "state/openclaw"),
        OPENCLAW_LOCAL_FEDORA_ROOT=str(root),
        OLLAMA_API_KEY="ollama-local",
    )
    # OpenClaw resolves every provider secret before a turn: the local gateway token must
    # always exist, or a configured cloud provider would also break local turns.
    from clawfedora.cloud_state import ensure_gateway_token

    env[CLOUD_TOKEN_ENV] = ensure_gateway_token(root)
    return env
