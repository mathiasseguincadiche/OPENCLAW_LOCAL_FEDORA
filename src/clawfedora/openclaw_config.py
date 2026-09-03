from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from clawfedora.agents import load_agent_specs
from clawfedora.core_config import core_contract, root_contract

PROVIDER_IDS = {
    "llama-cpp-vulkan": "intel-vulkan",
    "llama-cpp-sycl": "intel-sycl",
}
PROVIDER_ENV_KEYS = {
    "ollama": "OLLAMA_API_KEY",
    "intel-vulkan": "INTEL_VULKAN_API_KEY",
    "intel-sycl": "INTEL_SYCL_API_KEY",
}


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _env_secret_ref(env_name: str) -> dict[str, str]:
    return {"source": "env", "provider": "default", "id": env_name}


def _runtime_id(model: dict[str, Any], backend_id: str, *, alias: str) -> str:
    field = {
        "ollama-vulkan": "runtime_id",
        "llama-cpp-vulkan": "vulkan_runtime_id",
        "llama-cpp-sycl": "sycl_runtime_id",
    }.get(backend_id)
    if field is None:
        raise ValueError(f"backend OpenClaw non supporté: {backend_id}")
    value = str(model.get(field, ""))
    if not value:
        raise ValueError(f"{field} absent pour le modèle {alias}")
    return value


def _nominal_context_tokens(model: dict[str, Any], *, alias: str) -> int:
    value = int(model.get("nominal_context_tokens", 0) or 0)
    if value <= 0:
        raise ValueError(f"nominal_context_tokens absent pour le modèle {alias}")
    return value


def _backend_ref(alias: str, catalog: dict[str, Any], backend_id: str) -> str:
    models = _mapping(catalog.get("models"))
    if alias not in models:
        raise ValueError(f"alias modèle absent du catalogue: {alias}")
    model = _mapping(models[alias])
    if backend_id == "ollama-vulkan":
        return f"ollama/{_runtime_id(model, backend_id, alias=alias)}"
    provider = PROVIDER_IDS.get(backend_id)
    if provider is None:
        raise ValueError(f"backend OpenClaw non supporté: {backend_id}")
    return f"{provider}/{_runtime_id(model, backend_id, alias=alias)}"


def _agent_tools(agent_id: str, policy: dict[str, Any]) -> dict[str, Any]:
    defaults = _mapping(policy.get("security_defaults"))
    entry = _mapping(_mapping(policy.get("agents")).get(agent_id))
    tools: dict[str, Any] = {
        "profile": str(entry.get("profile", defaults.get("profile", "coding"))),
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


def _ollama_provider(catalog: dict[str, Any]) -> dict[str, Any]:
    models: list[dict[str, Any]] = []
    for alias, raw in _mapping(catalog.get("models")).items():
        model = _mapping(raw)
        if model.get("provider") != "ollama" or model.get("required") is not True:
            continue
        alias_text = str(alias)
        runtime_id = _runtime_id(model, "ollama-vulkan", alias=alias_text)
        context_tokens = _nominal_context_tokens(model, alias=alias_text)
        model_input = model.get("input", ["text"])
        inputs = list(model_input) if isinstance(model_input, list) else ["text"]
        models.append(
            {
                "id": runtime_id,
                "name": runtime_id,
                "input": inputs,
                "contextTokens": context_tokens,
                "params": {"num_ctx": context_tokens, "keep_alive": "15m"},
            }
        )
    return {
        "baseUrl": "http://127.0.0.1:11434",
        "apiKey": _env_secret_ref(PROVIDER_ENV_KEYS["ollama"]),
        "api": "ollama",
        "timeoutSeconds": 300,
        "models": models,
    }


def _llamacpp_provider(
    catalog: dict[str, Any], backend_id: str, backend: dict[str, Any]
) -> dict[str, Any]:
    provider_id = PROVIDER_IDS[backend_id]
    router = _mapping(backend.get("router"))
    context_tokens = int(router.get("context_tokens", 8192))
    models: list[dict[str, Any]] = []
    for alias, raw in _mapping(catalog.get("models")).items():
        model = _mapping(raw)
        if model.get("required") is not True:
            continue
        runtime_id = _runtime_id(model, backend_id, alias=str(alias))
        models.append(
            {
                "id": runtime_id,
                "name": runtime_id,
                "input": ["text"],
                "contextWindow": context_tokens,
                "contextTokens": context_tokens,
                "maxTokens": 2048,
                "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
                "compat": {"supportsTools": True, "toolSchemaProfile": "llamacpp"},
            }
        )
    return {
        "baseUrl": str(backend["endpoint"]),
        "apiKey": _env_secret_ref(PROVIDER_ENV_KEYS[provider_id]),
        "api": "openai-completions",
        "timeoutSeconds": 300,
        "models": models,
    }


def build_openclaw_patch(
    repo_root: Path, runtime_root: Path, backend_id: str = "ollama-vulkan"
) -> dict[str, Any]:
    catalog = root_contract(repo_root, "model_catalog.yaml")
    backends = root_contract(repo_root, "runtime_backends.yaml")
    configured = _mapping(backends.get("backends"))
    if backend_id not in configured:
        raise ValueError(f"backend absent de runtime_backends.yaml: {backend_id}")

    routing = core_contract(repo_root, "model_routing.yaml")
    tools = core_contract(repo_root, "tool_policy.yaml")
    web_policy = core_contract(repo_root, "web_policy.yaml")
    openclaw_policy = core_contract(repo_root, "openclaw_policy.yaml")

    providers: dict[str, Any] = {"ollama": _ollama_provider(catalog)}
    if backend_id != "ollama-vulkan":
        provider_id = PROVIDER_IDS.get(backend_id)
        if provider_id is None:
            raise ValueError(f"backend OpenClaw non supporté: {backend_id}")
        providers[provider_id] = _llamacpp_provider(
            catalog, backend_id, _mapping(configured[backend_id])
        )

    routes = _mapping(routing.get("agents"))
    agent_list: list[dict[str, Any]] = []
    for spec in load_agent_specs(repo_root):
        route = _mapping(routes.get(spec.agent_id))
        primary_alias = str(route.get("local_primary", spec.model))
        fallback_alias = str(route.get("local_fallback", spec.fallback))
        agent_list.append(
            {
                "id": spec.agent_id,
                "default": spec.agent_id == "chef-operations",
                "name": spec.name,
                "workspace": str(runtime_root / "workspaces" / spec.agent_id),
                "model": {
                    "primary": _backend_ref(primary_alias, catalog, backend_id),
                    "fallbacks": [_backend_ref(fallback_alias, catalog, backend_id)],
                },
                "experimental": {"localModelLean": True},
                "tools": _agent_tools(spec.agent_id, tools),
            }
        )

    qwen_ollama = _backend_ref("qwen-max", catalog, "ollama-vulkan")
    gemma_ollama = _backend_ref("gemma-deep", catalog, "ollama-vulkan")
    defaults = _mapping(openclaw_policy.get("agents"))
    web = _mapping(web_policy.get("nominal_path"))
    global_tools = _mapping(tools.get("security_defaults"))

    return {
        "gateway": {"mode": "local", "bind": "loopback"},
        "models": {"providers": providers},
        "agents": {
            "defaults": {
                "skipBootstrap": bool(defaults.get("skip_bootstrap", True)),
                "compaction": {
                    "reserveTokens": int(defaults.get("compaction_reserve_tokens", 4096)),
                    "reserveTokensFloor": int(defaults.get("compaction_reserve_tokens", 4096)),
                },
                "model": {
                    "primary": _backend_ref("qwen-max", catalog, backend_id),
                    "fallbacks": [_backend_ref("gemma-deep", catalog, backend_id)],
                },
                "imageModel": {"primary": qwen_ollama, "fallbacks": [gemma_ollama]},
                "pdfModel": {"primary": qwen_ollama, "fallbacks": [gemma_ollama]},
                "pdfMaxBytesMb": int(defaults.get("pdf_max_bytes_mb", 50)),
                "pdfMaxPages": int(defaults.get("pdf_max_pages", 20)),
            },
            "list": agent_list,
        },
        "tools": {
            "profile": str(global_tools.get("profile", "coding")),
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
                    "maxChars": 20000,
                    "maxCharsCap": 20000,
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
