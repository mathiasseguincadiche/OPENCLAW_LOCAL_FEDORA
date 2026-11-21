from pathlib import Path
from typing import Any

import pytest

from clawfedora.cloud_profiles import ProfileRefused, set_profile, set_upstream_model
from clawfedora.cloud_routing import agent_route, automatic_routes, gateway_route
from clawfedora.core_config import core_contract

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def policy() -> dict[str, Any]:
    return core_contract(ROOT, "cloud_policy.yaml")


@pytest.mark.parametrize(
    ("role", "routine", "escalation"),
    [
        ("chef-operations", "standard-soutenu", "expert-equilibre"),
        ("expert-recherche", "standard-rapide", "standard-soutenu"),
        ("architecte-solutions", "standard-soutenu", "expert-soutenu"),
        ("ingenieur-devops", "standard-soutenu", "expert-soutenu"),
        ("ingenieur-securite", "standard-soutenu", "expert-soutenu"),
        ("auditeur-qualite", "standard-soutenu", "expert-soutenu"),
        ("redacteur-pedagogique", "standard-rapide", "expert-equilibre"),
    ],
)
def test_all_seven_roles_have_a_deterministic_route(
    tmp_path: Path, policy: dict[str, Any], role: str, routine: str, escalation: str,
) -> None:
    first = agent_route(tmp_path, policy, role)
    second = agent_route(tmp_path, policy, role, "approved_revision")
    assert first.model_id == "atelier/" + routine
    assert second.model_id == "atelier/" + escalation
    assert gateway_route(tmp_path, policy, first.model_id) is not None
    assert len(automatic_routes(policy)) == 4


def test_final_review_is_expert_only_for_auditor(
    tmp_path: Path, policy: dict[str, Any],
) -> None:
    assert agent_route(tmp_path, policy, "auditeur-qualite", "final_review").model_name == "expert"
    with pytest.raises(ProfileRefused):
        agent_route(tmp_path, policy, "ingenieur-devops", "final_review")
    with pytest.raises(ProfileRefused):
        agent_route(tmp_path, policy, "auditeur-qualite", "budget_error")


def test_manual_override_and_return_to_automatic(
    tmp_path: Path, policy: dict[str, Any],
) -> None:
    set_upstream_model(tmp_path, policy, "expert")
    set_profile(tmp_path, policy, "equilibre")
    manual = agent_route(tmp_path, policy, "chef-operations")
    assert manual.upstream["upstream_id"] == "openai/gpt-6.2-sol"
    assert manual.profile["effort"] == "medium" and manual.reason == "manual"
    set_upstream_model(tmp_path, policy, "auto")
    assert agent_route(tmp_path, policy, "chef-operations").model_name == "standard"


def test_disabled_expert_never_falls_back(tmp_path: Path, policy: dict[str, Any]) -> None:
    policy["upstream_models"]["expert"]["enabled"] = False
    with pytest.raises(ProfileRefused, match="désactivé"):
        agent_route(tmp_path, policy, "auditeur-qualite", "final_review")

@pytest.mark.parametrize("role", [
    "chef-operations", "expert-recherche", "architecte-solutions",
    "ingenieur-devops", "ingenieur-securite", "auditeur-qualite",
    "redacteur-pedagogique",
])
@pytest.mark.parametrize(("tier", "expected"), [
    ("simple", "atelier/standard-rapide"),
    ("complex", "atelier/standard-soutenu"),
    ("critical", "atelier/standard-soutenu"),
])
def test_approved_task_tier_overrides_daily_role_without_spending_sol(
    tmp_path: Path, policy: dict[str, Any], role: str, tier: str, expected: str,
) -> None:
    routed = agent_route(tmp_path, policy, role, task_tier=tier)
    assert routed.model_id == expected
    assert routed.model_name == "standard"
    assert gateway_route(tmp_path, policy, routed.model_id) is not None


def test_critical_tier_cannot_escalate_to_sol_without_approved_revision(
    tmp_path: Path, policy: dict[str, Any],
) -> None:
    routine = agent_route(tmp_path, policy, "ingenieur-devops", task_tier="critical")
    approved = agent_route(
        tmp_path, policy, "ingenieur-devops", "approved_revision", task_tier="critical",
    )
    assert routine.model_name == "standard"
    assert approved.model_name == "expert"
    with pytest.raises(ProfileRefused, match="niveau de tâche"):
        agent_route(tmp_path, policy, "ingenieur-devops", task_tier="untrusted")
    with pytest.raises(ProfileRefused, match="niveau de tâche"):
        agent_route(tmp_path, policy, "ingenieur-devops", task_tier="Critical")
