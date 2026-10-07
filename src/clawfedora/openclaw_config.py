from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from clawfedora.agents import load_agent_specs
from clawfedora.core_config import core_contract, daily_limits, root_contract

OLLAMA_KEY_ENV = "OLLAMA_API_KEY"


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _environment_reference(env_name: str) -> dict[str, str]:
    """Return an environment identifier; never read or persist its credential value."""
    return {"source": "env", "provider": "default", "id": env_name}


def _model_ref(alias: str, catalog: dict[str, Any]) -> str:
    models = _mapping(catalog.get("models"))
    if alias not in models:
        raise ValueError(f"alias modèle absent du catalogue: {alias}")
    runtime_id = str(_mapping(models[alias]).get("runtime_id", ""))
    if not runtime_id:
        raise ValueError(f"runtime_id absent pour le modèle {alias}")
    return f"ollama/{runtime_id}"


def _agent_tools(agent_id: str, policy: dict[str, Any]) -> dict[str, Any]:
    defaults = _mapping(policy.get("security_defaults"))
    entry = _mapping(_mapping(policy.get("agents")).get(agent_id))
    tools: dict[str, Any] = {
        "profile": str(entry.get("profile", defaults.get("profile", "minimal"))),
        "fs": {"workspaceOnly": bool(defaults.get("fs_workspace_only", True))},
        "exec": {"mode": str(defaults.get("exec_mode", "ask"))},
        "elevated": {"enabled": bool(defaults.get("elevated_enabled", False))},
    }
    allow = entry.get("also_allow")
    deny = entry.get("deny")
    if isinstance(allow, list) and allow:
        tools["alsoAllow"] = list(allow)
    if isinstance(deny, list) and deny:
        tools["deny"] = list(deny)
    return tools


def _ollama_provider(catalog: dict[str, Any], limits: dict[str, Any]) -> dict[str, Any]:
    models: list[dict[str, Any]] = []
    for alias, raw in _mapping(catalog.get("models")).items():
        model = _mapping(raw)
        if model.get("provider") != "ollama" or model.get("required") is not True:
            continue
        runtime_id = _model_ref(str(alias), catalog).removeprefix("ollama/")
        context_tokens = int(limits["context_tokens"])
        output_tokens = int(limits["max_output_tokens"])
        model_input = model.get("input", ["text"])
        models.append(
            {
                "id": runtime_id,
                "name": runtime_id,
                "input": list(model_input) if isinstance(model_input, list) else ["text"],
                "contextTokens": context_tokens,
                "maxTokens": output_tokens,
                "params": {
                    "num_ctx": context_tokens,
                    "num_predict": output_tokens,
                    "keep_alive": str(limits["keep_alive"]),
                    "think": False,
                },
            }
        )
    return {
        "baseUrl": "http://127.0.0.1:11434",
        "apiKey": _environment_reference(OLLAMA_KEY_ENV),
        "api": "ollama",
        # A full answer after a long prompt can exceed five minutes.
        "timeoutSeconds": 600,
        "models": models,
    }


def build_openclaw_patch(repo_root: Path, runtime_root: Path) -> dict[str, Any]:
    catalog = root_contract(repo_root, "model_catalog.yaml")
    routing = core_contract(repo_root, "model_routing.yaml")
    tools = core_contract(repo_root, "tool_policy.yaml")
    web_policy = core_contract(repo_root, "web_policy.yaml")
    openclaw_policy = core_contract(repo_root, "openclaw_policy.yaml")
    limits = daily_limits(repo_root)
    providers: dict[str, Any] = {"ollama": _ollama_provider(catalog, limits)}

    routes = _mapping(routing.get("agents"))
    agent_list: list[dict[str, Any]] = []
    for spec in load_agent_specs(repo_root):
        route = _mapping(routes.get(spec.agent_id))
        primary_alias = str(route.get("local_primary", spec.model))
        agent_list.append(
            {
                "id": spec.agent_id,
                "default": spec.agent_id == "chef-operations",
                "name": spec.name,
                "workspace": str(runtime_root / "workspaces" / spec.agent_id),
                "model": {
                    "primary": _model_ref(primary_alias, catalog),
                    "fallbacks": [],
                },
                "experimental": {"localModelLean": False},
                "subagents": {"allowAgents": []},
                "tools": _agent_tools(spec.agent_id, tools),
            }
        )

    daily_model = _model_ref("qwen-max", catalog)
    defaults = _mapping(openclaw_policy.get("agents"))
    web = _mapping(web_policy.get("nominal_path"))
    global_tools = _mapping(tools.get("security_defaults"))

    return {
        "gateway": {
            "mode": "local",
            "bind": "loopback",
            "controlUi": {"newSessionModelDefaults": "configured"},
        },
        "plugins": {
            "allow": ["parallel", "clawfedora-toolkit", "memory-core"],
            "slots": {"memory": "none"},
            "load": {"paths": [str(runtime_root / "runtime/extensions/clawfedora-toolkit")]},
            "entries": {
                "memory-core": {"enabled": False},
                "clawfedora-toolkit": {"enabled": True},
            },
        },
        "models": {"mode": "replace", "providers": providers},
        "agents": {
            "defaults": {
                "skipBootstrap": bool(defaults.get("skip_bootstrap", True)),
                "bootstrapMaxChars": int(limits["bootstrap_max_chars"]),
                "bootstrapTotalMaxChars": int(limits["bootstrap_total_max_chars"]),
                "maxConcurrent": 1,
                "thinkingDefault": "off",
                "heartbeat": {"every": "0m"},
                "subagents": {
                    "maxConcurrent": 1,
                    "maxSpawnDepth": 1,
                    "maxChildrenPerAgent": 1,
                    "allowAgents": [],
                },
                "compaction": {
                    "keepRecentTokens": int(defaults["compaction_reserve_tokens"]),
                    "memoryFlush": {"enabled": False},
                },
                "model": {"primary": daily_model, "fallbacks": []},
                "imageModel": {"primary": daily_model, "fallbacks": []},
                "pdfModel": {"primary": daily_model, "fallbacks": []},
                "pdfMaxMb": int(defaults.get("pdf_max_bytes_mb", 50)),
                "pdfMaxPages": int(defaults.get("pdf_max_pages", 20)),
            },
            "entries": {
                str(entry["id"]): {key: value for key, value in entry.items() if key != "id"}
                for entry in agent_list
            },
        },
        "tools": {
            "profile": str(global_tools.get("profile", "minimal")),
            # Direct schemas: one tool call instead of search -> describe -> call,
            # which a 9B model rarely chains reliably. Affordable with the daily context.
            "toolSearch": False,
            "deny": [
                "exec",
                "process",
                "write",
                "edit",
                "apply_patch",
                "sessions_spawn",
                "sessions_send",
                "subagents",
                "browser",
                # "gateway" can run an OpenClaw update: forbidden by the exact version lock.
                "gateway",
                "presence",
            ],
            "fs": {"workspaceOnly": bool(global_tools.get("fs_workspace_only", True))},
            "exec": {
                "mode": str(global_tools.get("exec_mode", "ask")),
                "applyPatch": {"workspaceOnly": True},
            },
            "elevated": {"enabled": bool(global_tools.get("elevated_enabled", False))},
            "web": {
                "search": {
                    "enabled": bool(web.get("web_search_enabled", True)),
                    "provider": str(web.get("search_provider", "parallel-free")),
                    "maxResults": int(web.get("max_results", 8)),
                    "timeoutSeconds": int(web.get("search_timeout_seconds", 30)),
                    "cacheTtlMinutes": int(web.get("cache_ttl_minutes", 15)),
                },
                "fetch": {
                    "enabled": bool(web.get("web_fetch_enabled", True)),
                    "maxChars": int(web.get("fetch_max_chars", 4000)),
                    "maxCharsCap": int(web.get("fetch_max_chars", 4000)),
                    "timeoutSeconds": 30,
                },
            },
        },
    }


def write_openclaw_patch(path: Path, patch: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(patch, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def prepare_migration_patch(patch: dict[str, Any]) -> dict[str, Any]:
    """Stage managed settings; retire roster entries separately through the native SDK."""
    result: dict[str, Any] = json.loads(json.dumps(patch))
    result["agents"]["ownership"] = "explicit"
    defaults = result["agents"]["defaults"]
    defaults["systemAgent"] = {"agentId": "chef-operations"}
    result["talk"] = {"agentId": "chef-operations"}
    defaults["pdfMaxBytesMb"] = None
    defaults["compaction"].update(reserveTokens=None, reserveTokensFloor=None)
    # Remove the provider of the former llama.cpp experiment from older installations.
    result["models"]["providers"]["intel-vulkan"] = None
    for entry in result["agents"]["entries"].values():
        entry["default"] = None
    for retired in ("main", "redacteur-technique", "ingenieur-release-forges"):
        result["agents"]["entries"][retired] = {"default": None}
    # Do not unset agents.list: the pinned CLI redirects this legacy alias to entries.
    return result
