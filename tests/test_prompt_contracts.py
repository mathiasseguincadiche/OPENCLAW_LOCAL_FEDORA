from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from clawfedora.agents import (
    BOOTSTRAP_FILES,
    bootstrap_chars,
    deploy_workspaces,
    effective_instructions,
    validate_agent_assets,
)
from clawfedora.core_config import AGENT_IDS, daily_limits
from clawfedora.core_contracts import validate_core_contracts

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def prompt_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    for folder in ("agents", "config", "plugins"):
        shutil.copytree(ROOT / folder, root / folder)
    shutil.copy(ROOT / "VERSION", root / "VERSION")
    return root


def test_all_roles_receive_ordered_complete_instructions(tmp_path: Path) -> None:
    workspaces = deploy_workspaces(ROOT, tmp_path)
    shared = ROOT / "agents/_shared"
    limits = daily_limits(ROOT)
    for role, workspace in zip(AGENT_IDS, workspaces, strict=True):
        parts = [
            (shared / "PEDAGOGY.md").read_text().strip(),
            (ROOT / "agents" / role / "AGENTS.md").read_text().strip(),
            (shared / "TOOLS.md").read_text().strip(),
            (shared / "CONTRACT.md").read_text().strip(),
        ]
        deployed = (workspace / "AGENTS.md").read_text()
        assert deployed == "\n\n".join(parts) + "\n"
        assert len(deployed) <= bootstrap_chars(deployed) <= 12000
        assert all(
            bootstrap_chars((workspace / name).read_text()) <= limits["bootstrap_max_chars"]
            for name in BOOTSTRAP_FILES
        )
        assert sum(
            bootstrap_chars((workspace / name).read_text()) for name in BOOTSTRAP_FILES
        ) <= limits["bootstrap_total_max_chars"]
        for instruction in (
            "Mode direct par défaut", "consentement explicite", "practice_opt_in=true",
            "Terraform/Ansible/CI/CD", "documentation officielle", "files/summary",
            "NON VÉRIFIÉ ACTUELLEMENT", "À EXÉCUTER", "co-construction",
            "sans le reproduire", "relèvent de l'application",
        ):
            assert instruction in deployed
        # The prompts must stay true whichever model answers: no claim about the backend.
        for claim in ("Qwen", "OpenRouter", "GLM", "25 EUR", "Le modèle est local"):
            assert claim not in deployed


@pytest.mark.parametrize("character", ["é", "🧰"])
def test_exact_12000_boundary_and_native_unicode_count(
    prompt_repo: Path, tmp_path: Path, character: str,
) -> None:
    role = "ingenieur-devops"
    path = prompt_repo / "agents" / role / "AGENTS.md"
    original = path.read_text().strip()
    remaining = 12000 - bootstrap_chars(effective_instructions(prompt_repo, role))
    units = bootstrap_chars(character)
    padding = character * (remaining // units) + "x" * (remaining % units)
    path.write_text(original + padding)
    assert bootstrap_chars(effective_instructions(prompt_repo, role)) == 12000
    assert validate_agent_assets(prompt_repo) == ()
    deploy_workspaces(prompt_repo, tmp_path / "accepted")
    path.write_text(path.read_text() + "x")
    assert any("bootstrap_max_chars" in failure for failure in validate_agent_assets(prompt_repo))
    runtime = tmp_path / "rejected"
    with pytest.raises(ValueError, match="bootstrap_max_chars"):
        deploy_workspaces(prompt_repo, runtime)
    assert not runtime.exists()


@pytest.mark.parametrize("filename", ["PEDAGOGY.md", "TOOLS.md", "CONTRACT.md"])
def test_shared_growth_is_counted_for_every_role(prompt_repo: Path, filename: str) -> None:
    path = prompt_repo / "agents/_shared" / filename
    path.write_text(path.read_text() + "x" * 12000)
    failures = validate_agent_assets(prompt_repo)
    for role in AGENT_IDS:
        assert any(f"bootstrap_max_chars: {role}" in failure for failure in failures)


@pytest.mark.parametrize("key,value", [
    ("bootstrap_max_chars", 12001), ("bootstrap_max_chars", 0),
    ("bootstrap_total_max_chars", 8000),
])
def test_budget_cannot_be_raised_or_total_overflow_ignored(
    prompt_repo: Path, key: str, value: int,
) -> None:
    path = prompt_repo / "config/core/openclaw_policy.yaml"
    data = yaml.safe_load(path.read_text())
    data["agents"][key] = value
    path.write_text(yaml.safe_dump(data))
    assert validate_agent_assets(prompt_repo)


def test_separate_identity_file_cannot_be_truncated(prompt_repo: Path) -> None:
    (prompt_repo / "agents/chef-operations/SOUL.md").write_text("x" * 12001)
    assert any(
        "chef-operations/SOUL.md" in failure for failure in validate_agent_assets(prompt_repo)
    )


@pytest.mark.parametrize("role", AGENT_IDS)
@pytest.mark.parametrize("tool", ["exec", "sessions_spawn", "clawfedora_unknown"])
def test_role_cannot_gain_undeclared_tools(prompt_repo: Path, role: str, tool: str) -> None:
    path = prompt_repo / "config/core/tool_policy.yaml"
    data = yaml.safe_load(path.read_text())
    data["agents"][role]["also_allow"].append(tool)
    path.write_text(yaml.safe_dump(data))
    failures, _ = validate_core_contracts(prompt_repo)
    assert any(f"permissions divergentes pour {role}" in failure for failure in failures)


def test_specialist_tool_cannot_cross_roles(prompt_repo: Path) -> None:
    path = prompt_repo / "config/core/tool_policy.yaml"
    data = yaml.safe_load(path.read_text())
    data["agents"]["expert-recherche"]["also_allow"].append("clawfedora_diagram")
    path.write_text(yaml.safe_dump(data))
    failures, _ = validate_core_contracts(prompt_repo)
    assert any("permissions divergentes pour expert-recherche" in failure for failure in failures)


@pytest.mark.parametrize("key,value", [("local_only", False), ("cloud_models_supported", True)])
def test_local_routing_flags_cannot_change_silently(
    prompt_repo: Path, key: str, value: bool,
) -> None:
    path = prompt_repo / "config/core/model_routing.yaml"
    data = yaml.safe_load(path.read_text())
    data["policy"][key] = value
    path.write_text(yaml.safe_dump(data))
    failures, _ = validate_core_contracts(prompt_repo)
    assert any("core/routing: local_only" in failure for failure in failures)


def test_unknown_role_cannot_select_an_instruction_path() -> None:
    with pytest.raises(ValueError, match="rôle inconnu"):
        effective_instructions(ROOT, "../_shared")
