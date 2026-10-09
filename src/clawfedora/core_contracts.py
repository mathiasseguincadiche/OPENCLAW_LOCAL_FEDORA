from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from clawfedora.agents import validate_agent_assets
from clawfedora.core_config import (
    AGENT_IDS,
    CLOUD_PROVIDER_ID,
    CLOUD_TOKEN_ENV,
    core_contract,
    daily_limits,
    root_contract,
)

CORE_FILES = (
    "agents.yaml",
    "model_routing.yaml",
    "cloud_policy.yaml",
    "tool_policy.yaml",
    "web_policy.yaml",
    "openclaw_policy.yaml",
    "intake_policy.yaml",
    "document_ingestion_policy.yaml",
    "orchestration_policy.yaml",
    "artifact_exchange_policy.yaml",
    "knowledge_policy.yaml",
)



def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _loopback(endpoint: str) -> bool:
    return endpoint.startswith("http://127.0.0.1:") or endpoint.startswith("http://localhost:")


def _validate_project_contracts(
    contracts: dict[str, dict[str, Any]],
    failures: list[str],
) -> None:
    knowledge = contracts["knowledge_policy.yaml"]
    if knowledge.get("local_only") is not True or knowledge.get("backend") != "sqlite-fts5":
        failures.append("knowledge: recherche locale SQLite FTS5 requise")
    limits = _mapping(knowledge.get("limits"))
    if (
        not 0 < int(limits.get("max_results", 0)) <= 4
        or not 0 < int(limits.get("max_result_chars", 0)) <= 4000
    ):
        failures.append("knowledge: passages limités à 4 et 4000 caractères requis")
    if not 0 <= int(limits.get("overlap_chars", -1)) < int(limits.get("chunk_chars", 0)):
        failures.append("knowledge: taille/recouvrement de passage invalides")
    for key in (
        "max_documents",
        "max_file_bytes",
        "max_text_chars",
        "max_total_chars",
        "max_chunks",
        "pdf_max_pages",
        "pdf_timeout_seconds",
    ):
        if int(limits.get(key, 0)) <= 0:
            failures.append(f"knowledge: limite positive requise: {key}")
    intake = contracts["intake_policy.yaml"]
    intake_security = _mapping(intake.get("security"))
    intake_integrity = _mapping(intake.get("integrity"))
    if intake_security.get("reject_symlinks") is not True:
        failures.append("core/intake: symlinks doivent être refusés")
    if intake_security.get("scan_obvious_secrets") is not True:
        failures.append("core/intake: scan de secrets requis")
    if intake_security.get("execute_received_files") is not False:
        failures.append("core/intake: exécution des entrées interdite")
    for key in (
        "sha256_required",
        "aggregate_digest_required",
        "intake_files_read_only",
        "revalidate_before_phase_changes",
    ):
        if intake_integrity.get(key) is not True:
            failures.append(f"core/intake: {key}=true requis")

    ingestion = contracts["document_ingestion_policy.yaml"]
    if ingestion.get("local_first") is not True:
        failures.append("core/ingestion: local-first requis")
    gate = _mapping(ingestion.get("analysis_gate"))
    if gate.get("require_complete_source_coverage") is not True:
        failures.append("core/ingestion: couverture complète requise")
    if gate.get("tool_required_must_be_actually_read") is not True:
        failures.append("core/ingestion: lecture réelle des médias requise")
    formats = _mapping(ingestion.get("formats"))
    if _mapping(formats.get("pdf")).get("method") != "pdf":
        failures.append("core/ingestion: PDF doit utiliser l'outil pdf")
    if _mapping(formats.get("image")).get("method") != "view_image":
        failures.append("core/ingestion: image doit utiliser view_image")
    archive = _mapping(formats.get("archive"))
    if archive.get("method") != "local_safe_archive_extract":
        failures.append("core/ingestion: ZIP doit utiliser l'extraction sûre locale")

    orchestration = contracts["orchestration_policy.yaml"]
    engine = _mapping(orchestration.get("engine"))
    if engine.get("fail_closed") is not True:
        failures.append("core/orchestration: fail-closed requis")
    if engine.get("final_human_approval_required") is not True:
        failures.append("core/orchestration: approbation humaine finale requise")
    if engine.get("artifact_exchange_fail_closed") is not True:
        failures.append("core/orchestration: artifact exchange fail-closed requis")
    expected_flow = [
        "INTAKE_READY",
        "ANALYZED",
        "CLARIFICATION_REQUIRED",
        "PLANNED",
        "ASSIGNED",
        "IN_PROGRESS",
        "VALIDATING",
        "REVIEW",
        "PACKAGING",
        "COMPLETE",
    ]
    if orchestration.get("status_flow") != expected_flow:
        failures.append("core/orchestration: machine d'états canonique requise")
    execution = _mapping(orchestration.get("execution"))
    if int(execution.get("max_task_attempts", 0)) != 2:
        failures.append("core/orchestration: deux tentatives maximum par tâche")
    if int(execution.get("max_parallel_tasks", 0)) != 1:
        failures.append("core/orchestration: parallélisme initial doit rester à 1")

    exchange = contracts["artifact_exchange_policy.yaml"]
    principles = _mapping(exchange.get("principles"))
    for key in (
        "central_project_is_source_of_truth",
        "never_overwrite_previous_runs",
        "publish_self_history_for_every_attempt",
        "publish_to_dependents_only_on_pass",
        "preserve_provenance",
        "hash_every_exchanged_file",
        "consumer_must_not_modify_exchange_in_place",
    ):
        if principles.get(key) is not True:
            failures.append(f"core/exchange: {key}=true requis")



def _validate_cloud_contracts(
    repo_root: Path,
    contracts: dict[str, dict[str, Any]],
    catalog: dict[str, Any],
    routing_policy: dict[str, Any],
    failures: list[str],
) -> None:
    """The cloud is an opt-in route through one loopback gateway; it is never a default."""
    cloud = contracts["cloud_policy.yaml"]
    policy = _mapping(cloud.get("policy"))
    gateway = _mapping(cloud.get("gateway"))
    model = _mapping(cloud.get("model"))
    models = _mapping(catalog.get("models"))
    fleet = _mapping(catalog.get("fleet_policy"))

    if (
        routing_policy.get("cloud_enabled_by_default") is not False
        or policy.get("enabled_by_default") is not False
        or fleet.get("cloud_enabled_by_default") is not False
    ):
        failures.append("core/cloud: le cloud doit rester désactivé par défaut")
    if (
        routing_policy.get("local_to_cloud_fallback") != "forbidden"
        or policy.get("local_to_cloud_fallback") != "forbidden"
        or routing_policy.get("no_hidden_small_model_fallback") is not True
        or fleet.get("cloud_model_as_local_fallback") is not False
    ):
        failures.append("core/cloud: aucun repli du local vers le cloud ni vers un modèle caché")
    if policy.get("cloud_to_local_fallback") != "visible_only":
        failures.append("core/cloud: le repli cloud vers local doit rester visible")
    if set(policy.get("requires", [])) != {"privacy_filter", "budget_guard"}:
        failures.append("core/cloud: confidentialité et budget sont tous deux requis")

    if policy.get("provider_id") != CLOUD_PROVIDER_ID or policy.get("upstream") != "openrouter":
        failures.append("core/cloud: fournisseur cloudgw vers openrouter requis")
    host = str(gateway.get("host", ""))
    port = gateway.get("port")
    if host != "127.0.0.1" or type(port) is not int or not 1024 <= port <= 65535:
        failures.append("core/cloud: la passerelle doit écouter sur 127.0.0.1 (port valide)")
    if port in {3000, 11434, 18789, 18890, 18891}:
        failures.append("core/cloud: port de passerelle déjà utilisé par un autre service")
    if gateway.get("token_env") != CLOUD_TOKEN_ENV or not re.fullmatch(
        r"[A-Z][A-Z0-9_]{2,63}", str(gateway.get("token_env", ""))
    ):
        failures.append("core/cloud: token_env doit nommer la variable d'environnement du jeton")
    key_file = str(gateway.get("upstream_key_file", ""))
    if not key_file or key_file.startswith(("/", "~")) or ".." in Path(key_file).parts:
        failures.append("core/cloud: upstream_key_file doit être relatif à l'état d'exécution")
    if gateway.get("api") != "openai-completions" or not str(
        gateway.get("path_prefix", "")
    ).startswith("/"):
        failures.append("core/cloud: passerelle openai-completions avec path_prefix requis")

    alias = str(model.get("alias", ""))
    entry = _mapping(models.get(alias))
    if (
        alias != routing_policy.get("cloud_alias")
        or entry.get("provider") != "cloud-gateway"
        or entry.get("required") is True
        or entry.get("runtime_id") != model.get("upstream_id")
    ):
        failures.append("core/cloud: le modèle cloud doit être déclaré, optionnel, au catalogue")
    try:
        limits = daily_limits(repo_root)
    except (FileNotFoundError, ValueError):
        limits = {}
    if limits and (
        model.get("context_tokens") != limits["context_tokens"]
        or model.get("max_output_tokens") != limits["max_output_tokens"]
    ):
        failures.append("core/cloud: contexte et sortie doivent égaler les limites quotidiennes")
    pricing = _mapping(model.get("pricing_usd_per_million"))
    if not all(
        isinstance(pricing.get(key), int | float) and pricing[key] > 0
        for key in ("input", "output")
    ):
        failures.append("core/cloud: tarifs de référence requis")
    provider = _mapping(_mapping(cloud.get("upstream_params")).get("provider"))
    if provider.get("data_collection") != "deny":
        failures.append("core/cloud: data_collection=deny requis")
    if provider.get("require_parameters") is not True:
        failures.append("core/cloud: require_parameters=true requis")


def validate_core_contracts(
    repo_root: Path,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    failures: list[str] = []
    warnings: list[str] = []
    version = (repo_root / "VERSION").read_text(encoding="utf-8").strip()

    contracts: dict[str, dict[str, Any]] = {}
    for name in CORE_FILES:
        try:
            payload = core_contract(repo_root, name)
        except (FileNotFoundError, ValueError) as exc:
            failures.append(f"core: {exc}")
            continue
        contracts[name] = payload
        if str(payload.get("platform_version", "")) != version:
            failures.append(f"core/{name}: platform_version != VERSION ({version})")

    if failures:
        return tuple(failures), tuple(warnings)

    agents = _mapping(contracts["agents.yaml"].get("agents"))
    expected = set(AGENT_IDS)
    if set(agents) != expected:
        failures.append("core/agents: roster des spécialistes divergent")
    policy = _mapping(contracts["agents.yaml"].get("policy"))
    if int(policy.get("exact_agent_count", 0)) != len(AGENT_IDS):
        failures.append("core/agents: exact_agent_count divergent du roster")
    if policy.get("default_agent") != "chef-operations":
        failures.append("core/agents: chef-operations doit rester l'agent par défaut")

    catalog = root_contract(repo_root, "model_catalog.yaml")
    model_aliases = set(_mapping(catalog.get("models")))
    routing = _mapping(contracts["model_routing.yaml"].get("agents"))
    routing_policy = _mapping(contracts["model_routing.yaml"].get("policy"))
    _validate_cloud_contracts(repo_root, contracts, catalog, routing_policy, failures)
    tools = _mapping(contracts["tool_policy.yaml"].get("agents"))
    if set(routing) != expected or set(tools) != expected:
        failures.append("core: routage et politique outils doivent couvrir tous les agents")

    for agent_id, raw in agents.items():
        entry = _mapping(raw)
        model = str(entry.get("model", ""))
        fallback = str(entry.get("fallback", ""))
        if model not in model_aliases or fallback not in model_aliases:
            failures.append(f"core/agents: modèle ou fallback invalide pour {agent_id}")
        route = _mapping(routing.get(agent_id))
        if route.get("local_primary") != model or route.get("local_fallback") != fallback:
            failures.append(f"core/routing: divergence de routage pour {agent_id}")
        if route.get("cloud_primary") != routing_policy.get("cloud_alias"):
            failures.append(f"core/routing: route cloud divergente pour {agent_id}")

    defaults = _mapping(contracts["tool_policy.yaml"].get("security_defaults"))
    if defaults.get("fs_workspace_only") is not True:
        failures.append("core/tools: fs workspace-only requis")
    if defaults.get("exec_mode") != "ask":
        failures.append("core/tools: exec.mode=ask requis")
    if defaults.get("elevated_enabled") is not False:
        failures.append("core/tools: elevated doit rester désactivé")

    from clawfedora.agent_tools import TOOL_ROLES

    forbidden = {
        "exec", "process", "write", "edit", "apply_patch", "gateway", "browser",
        "sessions_spawn", "sessions_send", "subagents", "presence",
    }
    native_allowed = {
        "read", "web_search", "web_fetch", "session_status", "pdf", "view_image",
    }
    mentor_allowed = {"agents_list", "sessions_list", "sessions_history", "sessions_search"}
    for agent_id, raw_tools in tools.items():
        tool_entry = _mapping(raw_tools)
        allow = tool_entry.get("also_allow")
        deny = tool_entry.get("deny")
        expected_tools = native_allowed | {
            tool for tool, roles in TOOL_ROLES.items() if agent_id in roles
        }
        if agent_id == "chef-operations":
            expected_tools |= mentor_allowed
        if (
            tool_entry.get("profile") != "minimal"
            or not isinstance(allow, list)
            or any(not isinstance(tool, str) for tool in allow)
            or set(allow) != expected_tools
            or len(allow) != len(set(allow))
            or not isinstance(deny, list)
            or any(not isinstance(tool, str) for tool in deny)
            or not {"exec", "process", "write", "edit", "apply_patch"} <= set(deny)
            or bool(set(allow) & (set(deny) | forbidden))
        ):
            failures.append(f"core/tools: permissions divergentes pour {agent_id}")

    web = _mapping(contracts["web_policy.yaml"].get("nominal_path"))
    if web.get("reasoning") != "local_model":
        failures.append("core/web: le raisonnement doit rester local")

    openclaw = contracts["openclaw_policy.yaml"]
    openclaw_runtime = _mapping(openclaw.get("runtime"))
    openclaw_plugins = _mapping(openclaw.get("plugins"))
    parallel_policy = _mapping(openclaw_plugins.get("parallel_search"))
    gateway = _mapping(openclaw.get("gateway"))
    security = _mapping(openclaw.get("security"))

    runtime_versions = root_contract(repo_root, "runtime_versions.yaml")
    version_contract = _mapping(runtime_versions.get("openclaw"))
    parallel_version = _mapping(_mapping(version_contract.get("plugins")).get("parallel"))
    upgrade_policy = _mapping(runtime_versions.get("upgrade_policy"))

    # config/runtime_versions.yaml is the single place where the version is written.
    locked = str(version_contract.get("version", ""))
    if not re.fullmatch(r"\d{4}\.\d+\.\d+", locked):
        failures.append("core/openclaw: version exacte attendue dans runtime_versions.yaml")
    if version_contract.get("lock") != "exact":
        failures.append("core/openclaw: verrou de version exact requis")
    if version_contract.get("automatic_update") is not False:
        failures.append("core/openclaw: mise à jour automatique interdite")
    if openclaw_runtime.get("required_version") != locked:
        failures.append("core/openclaw: required_version diffère de runtime_versions.yaml")
    if openclaw_runtime.get("version_lock") != "exact":
        failures.append("core/openclaw: version_lock=exact requis")
    if openclaw_runtime.get("automatic_update_allowed") is not False:
        failures.append("core/openclaw: automatic_update_allowed=false requis")
    if parallel_version.get("version") != locked:
        failures.append("core/openclaw: plugin Parallel doit suivre la version d'OpenClaw")
    if parallel_version.get("lock") != "exact":
        failures.append("core/openclaw: plugin Parallel doit être verrouillé exactement")
    if parallel_policy.get("version") != locked:
        failures.append("core/openclaw: politique Parallel diffère de runtime_versions.yaml")
    if parallel_policy.get("version_lock") != "exact":
        failures.append("core/openclaw: politique Parallel exige version_lock=exact")
    if parallel_policy.get("automatic_update_allowed") is not False:
        failures.append("core/openclaw: mise à jour automatique Parallel interdite")
    for key in (
        "openclaw_version_locked",
        "openclaw_update_requires_explicit_contract_change",
        "parallel_plugin_version_locked",
    ):
        if upgrade_policy.get(key) is not True:
            failures.append(f"core/openclaw: upgrade_policy.{key}=true requis")
    if upgrade_policy.get("automatic_runtime_upgrade") is not False:
        failures.append("core/openclaw: automatic_runtime_upgrade=false requis")

    if gateway.get("mode") != "local" or gateway.get("bind") != "loopback":
        failures.append("core/openclaw: Gateway local loopback requis")
    if security.get("providers_loopback_only") is not True:
        failures.append("core/openclaw: providers loopback-only requis")
    if security.get("exec_mode") != "ask" or security.get("elevated_enabled") is not False:
        failures.append("core/openclaw: exec=ask et elevated=false requis")

    _validate_project_contracts(contracts, failures)
    failures.extend(validate_agent_assets(repo_root))
    # One set of daily limits for OpenClaw, Ollama, the chat bridge and the catalog.
    try:
        daily_limits(repo_root)
    except (FileNotFoundError, ValueError) as exc:
        failures.append(f"core/limites: {exc}")

    return tuple(failures), tuple(warnings)
