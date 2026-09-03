from __future__ import annotations

from pathlib import Path
from typing import Any

from clawfedora.agents import validate_agent_assets
from clawfedora.core_config import AGENT_IDS, core_contract, root_contract

CORE_FILES = (
    "agents.yaml",
    "model_routing.yaml",
    "tool_policy.yaml",
    "web_policy.yaml",
    "openclaw_policy.yaml",
    "intake_policy.yaml",
    "document_ingestion_policy.yaml",
    "orchestration_policy.yaml",
    "artifact_exchange_policy.yaml",
    "budget_policy.yaml",
    "telemetry_policy.yaml",
)


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _loopback(endpoint: str) -> bool:
    return endpoint.startswith("http://127.0.0.1:") or endpoint.startswith("http://localhost:")


def _validate_project_contracts(
    contracts: dict[str, dict[str, Any]], failures: list[str]
) -> None:
    intake = contracts["intake_policy.yaml"]
    intake_security = _mapping(intake.get("security"))
    intake_integrity = _mapping(intake.get("integrity"))
    if intake_security.get("reject_symlinks") is not True:
        failures.append("core/intake: symlinks doivent être refusés")
    if intake_security.get("scan_obvious_secrets") is not True:
        failures.append("core/intake: scan de secrets requis")
    if intake_security.get("execute_received_files") is not False:
        failures.append("core/intake: exécution des entrées interdite")
    for key in ("sha256_required", "aggregate_digest_required", "intake_files_read_only"):
        if intake_integrity.get(key) is not True:
            failures.append(f"core/intake: {key}=true requis")

    ingestion = contracts["document_ingestion_policy.yaml"]
    if ingestion.get("local_first") is not True:
        failures.append("core/ingestion: local-first requis")
    gate = _mapping(ingestion.get("analysis_gate"))
    if gate.get("require_complete_source_coverage") is not True:
        failures.append("core/ingestion: couverture complète requise")
    formats = _mapping(ingestion.get("formats"))
    if _mapping(formats.get("pdf")).get("method") != "pdf":
        failures.append("core/ingestion: PDF doit utiliser l'outil pdf")
    if _mapping(formats.get("image")).get("method") != "view_image":
        failures.append("core/ingestion: image doit utiliser view_image")
    if _mapping(formats.get("archive")).get("method") != "local_safe_archive_extract":
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

    budget = contracts["budget_policy.yaml"]
    if budget.get("cloud_enabled_by_default") is not False:
        failures.append("core/budget: cloud désactivé par défaut requis")
    if _mapping(budget.get("behavior")).get("on_limit") != "deny":
        failures.append("core/budget: dépassement doit être refusé")

    telemetry = contracts["telemetry_policy.yaml"]
    if telemetry.get("local_only") is not True:
        failures.append("core/telemetry: stockage local requis")
    forbidden = set(telemetry.get("forbidden_content", []))
    required_forbidden = {"prompt", "response", "document_content", "secret", "api_key", "token"}
    if not required_forbidden <= forbidden:
        failures.append("core/telemetry: contenu sensible insuffisamment interdit")


def validate_core_contracts(repo_root: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
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
        failures.append("core/agents: exactement huit rôles sont requis")
    policy = _mapping(contracts["agents.yaml"].get("policy"))
    if int(policy.get("exact_agent_count", 0)) != 8:
        failures.append("core/agents: exact_agent_count doit rester à 8")
    if policy.get("default_agent") != "chef-operations":
        failures.append("core/agents: chef-operations doit rester l'agent par défaut")

    catalog = root_contract(repo_root, "model_catalog.yaml")
    model_aliases = set(_mapping(catalog.get("models")))
    routing = _mapping(contracts["model_routing.yaml"].get("agents"))
    tools = _mapping(contracts["tool_policy.yaml"].get("agents"))
    if set(routing) != expected or set(tools) != expected:
        failures.append("core: routage et politique outils doivent couvrir les huit agents")

    for agent_id, raw in agents.items():
        entry = _mapping(raw)
        model = str(entry.get("model", ""))
        fallback = str(entry.get("fallback", ""))
        if model not in model_aliases or fallback not in model_aliases:
            failures.append(f"core/agents: modèle ou fallback invalide pour {agent_id}")
        route = _mapping(routing.get(agent_id))
        if route.get("local_primary") != model or route.get("local_fallback") != fallback:
            failures.append(f"core/routing: divergence de routage pour {agent_id}")

    defaults = _mapping(contracts["tool_policy.yaml"].get("security_defaults"))
    if defaults.get("fs_workspace_only") is not True:
        failures.append("core/tools: fs workspace-only requis")
    if defaults.get("exec_mode") != "ask":
        failures.append("core/tools: exec.mode=ask requis")
    if defaults.get("elevated_enabled") is not False:
        failures.append("core/tools: elevated doit rester désactivé")

    web = _mapping(contracts["web_policy.yaml"].get("nominal_path"))
    if web.get("reasoning") != "local_model":
        failures.append("core/web: le raisonnement doit rester local")

    openclaw = contracts["openclaw_policy.yaml"]
    gateway = _mapping(openclaw.get("gateway"))
    security = _mapping(openclaw.get("security"))
    if gateway.get("mode") != "local" or gateway.get("bind") != "loopback":
        failures.append("core/openclaw: Gateway local loopback requis")
    if security.get("providers_loopback_only") is not True:
        failures.append("core/openclaw: providers loopback-only requis")
    if security.get("exec_mode") != "ask" or security.get("elevated_enabled") is not False:
        failures.append("core/openclaw: exec=ask et elevated=false requis")

    backends = root_contract(repo_root, "runtime_backends.yaml")
    for backend_id, raw in _mapping(backends.get("backends")).items():
        entry = _mapping(raw)
        endpoint = str(entry.get("endpoint", ""))
        if endpoint and not _loopback(endpoint):
            failures.append(f"core/backends: endpoint non loopback pour {backend_id}")

    _validate_project_contracts(contracts, failures)
    failures.extend(validate_agent_assets(repo_root))
    if not failures:
        warnings.append(
            "L1 runtime: configuration générée à valider contre le schéma OpenClaw vivant"
        )
    return tuple(failures), tuple(warnings)
