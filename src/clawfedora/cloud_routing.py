"""Deterministic cloud routing: no prompt, inference, retry loop or secret in the decision."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from clawfedora.cloud_profiles import (
    ProfileRefused,
    chosen_profile,
    chosen_routing_mode,
    chosen_upstream_model,
    profiles,
    require_compatible,
    upstream_models,
)
from clawfedora.core_config import AGENT_IDS

REASONS = frozenset({"routine", "approved_revision", "final_review"})
# Optional, human-approved task classification; never infer sensitivity from prompt text.
TASK_TIERS = frozenset({"simple", "complex", "critical"})
ALLOWED_PAIRS = frozenset({
    ("standard", "rapide"), ("standard", "soutenu"),
    ("expert", "equilibre"), ("expert", "soutenu"),
})


@dataclass(frozen=True)
class Route:
    model_id: str
    model_name: str
    profile_name: str
    upstream: dict[str, Any]
    profile: dict[str, Any]
    reason: str


def model_alias(model: str, profile: str) -> str:
    return f"atelier/{model}-{profile}"


def _pair(value: Any) -> tuple[str, str]:
    if (
        not isinstance(value, list) or len(value) != 2
        or any(type(v) is not str for v in value)
        or tuple(value) not in ALLOWED_PAIRS
    ):
        raise ProfileRefused("routage cloud : couple modèle/profil non autorisé")
    return str(value[0]), str(value[1])


def role_routes(policy: dict[str, Any]) -> dict[str, dict[str, tuple[str, str]]]:
    value = policy.get("agent_routing")
    if not isinstance(value, dict) or value.get("default_mode") != "auto":
        raise ProfileRefused("routage cloud : mode automatique requis")
    roles = value.get("roles")
    if not isinstance(roles, dict) or set(roles) != set(AGENT_IDS):
        raise ProfileRefused("routage cloud : sept rôles exacts requis")
    declared, declared_profiles = upstream_models(policy), profiles(policy)
    if {key: value["upstream_id"] for key, value in declared.items()} != {
        "standard": "deepseek/deepseek-v4.1-flash-1017", "expert": "openai/gpt-6.2-sol",
    }:
        raise ProfileRefused("routage cloud : deux modèles approuvés exacts requis")
    result: dict[str, dict[str, tuple[str, str]]] = {}
    for role in AGENT_IDS:
        spec = roles[role]
        if not isinstance(spec, dict) or set(spec) != {"routine", "escalation"}:
            raise ProfileRefused("routage cloud : routine et escalade requises")
        pairs = {key: _pair(spec[key]) for key in ("routine", "escalation")}
        if pairs["routine"][0] != "standard":
            raise ProfileRefused("routage cloud : DeepSeek requis en routine")
        if (role == "expert-recherche") != (pairs["escalation"][0] == "standard"):
            raise ProfileRefused("routage cloud : escalade incohérente avec le rôle")
        for model, profile in pairs.values():
            if model not in declared or profile not in declared_profiles:
                raise ProfileRefused("routage cloud : référence absente de la politique")
            require_compatible(model, declared[model], profile, declared_profiles[profile])
        result[role] = pairs
    return result


def _route(
    policy: dict[str, Any], model_id: str, model_name: str, profile_name: str, reason: str,
) -> Route:
    upstream = upstream_models(policy)[model_name]
    profile = profiles(policy)[profile_name]
    require_compatible(model_name, upstream, profile_name, profile)
    return Route(model_id, model_name, profile_name, upstream, profile, reason)


def automatic_routes(policy: dict[str, Any]) -> dict[str, Route]:
    pairs = {pair for spec in role_routes(policy).values() for pair in spec.values()}
    return {
        model_alias(model, profile): _route(
            policy, model_alias(model, profile), model, profile, "automatic",
        )
        for model, profile in sorted(pairs)
    }


def _manual(runtime: Path, policy: dict[str, Any]) -> Route:
    model_name, _ = chosen_upstream_model(runtime, policy)
    profile_name, _ = chosen_profile(runtime, policy)
    result = _route(
        policy, str(policy["model"]["upstream_id"]), model_name, profile_name, "manual",
    )
    return _enabled(result)


def _enabled(route: Route) -> Route:
    if route.upstream["enabled"] is not True:
        raise ProfileRefused(f"modèle cloud « {route.model_name} » désactivé")
    return route


def agent_route(
    runtime: Path, policy: dict[str, Any], role: str, reason: str = "routine",
    *, task_tier: str | None = None,
) -> Route:
    roles = role_routes(policy)
    if role not in roles or reason not in REASONS:
        raise ProfileRefused("routage cloud : rôle ou raison non autorisés")
    if task_tier is not None and (type(task_tier) is not str or task_tier not in TASK_TIERS):
        raise ProfileRefused("routage cloud : niveau de tâche non autorisé")
    if reason == "final_review" and role != "auditeur-qualite":
        raise ProfileRefused("routage cloud : revue finale réservée à l'auditeur")
    mode = chosen_routing_mode(runtime, policy)
    # Even in auto mode a corrupted operator profile must fail closed.
    chosen_profile(runtime, policy)
    if mode != "auto":
        return _manual(runtime, policy)
    # An approved task tier takes precedence over the role for everyday cloud work.
    # A critical task still uses DeepSeek until a revision/final review is approved;
    # complexity alone cannot spend Sol credits or bypass human consent.
    if task_tier is not None and reason == "routine":
        model, profile = ("standard", "rapide" if task_tier == "simple" else "soutenu")
    else:
        model, profile = roles[role]["routine" if reason == "routine" else "escalation"]
    return _enabled(_route(policy, model_alias(model, profile), model, profile, reason))


def gateway_route(runtime: Path, policy: dict[str, Any], model_id: Any) -> Route | None:
    """Decode a declared local alias; client cannot submit an arbitrary upstream model."""
    mode = chosen_routing_mode(runtime, policy)
    chosen_profile(runtime, policy)
    if model_id == policy["model"]["upstream_id"]:
        return _manual(runtime, policy)
    if not isinstance(model_id, str):
        return None
    routes = automatic_routes(policy)
    if model_id not in routes:
        return None
    if mode != "auto":
        raise ProfileRefused("routage automatique indisponible en mode manuel")
    return _enabled(routes[model_id])
