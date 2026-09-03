from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from clawfedora.core_config import AGENT_IDS, core_contract

ROLE_FILES = ("AGENTS.md", "IDENTITY.md", "SOUL.md")
SHARED_FILES = ("CONTRACT.md", "TOOLS.md", "HEARTBEAT.md", "PEDAGOGY.md")


@dataclass(frozen=True)
class AgentSpec:
    agent_id: str
    name: str
    model: str
    fallback: str
    mission: str


def _agent_map(repo_root: Path) -> dict[str, Any]:
    payload = core_contract(repo_root, "agents.yaml")
    agents = payload.get("agents")
    if not isinstance(agents, dict):
        raise ValueError("agents.yaml: agents doit être un mapping")
    return agents


def load_agent_specs(repo_root: Path) -> tuple[AgentSpec, ...]:
    agents = _agent_map(repo_root)
    result: list[AgentSpec] = []
    for agent_id in AGENT_IDS:
        entry = agents.get(agent_id)
        if not isinstance(entry, dict):
            raise ValueError(f"agents.yaml: agent absent ou invalide: {agent_id}")
        result.append(
            AgentSpec(
                agent_id=agent_id,
                name=str(entry.get("name", "")),
                model=str(entry.get("model", "")),
                fallback=str(entry.get("fallback", "")),
                mission=str(entry.get("mission", "")),
            )
        )
    return tuple(result)


def validate_agent_assets(repo_root: Path) -> tuple[str, ...]:
    failures: list[str] = []
    shared = repo_root / "agents" / "_shared"
    for filename in SHARED_FILES:
        if not (shared / filename).is_file():
            failures.append(f"agents: fichier partagé absent: {filename}")

    try:
        specs = load_agent_specs(repo_root)
    except (FileNotFoundError, ValueError) as exc:
        return (str(exc),)

    if len(specs) != 8 or tuple(spec.agent_id for spec in specs) != AGENT_IDS:
        failures.append("agents: les huit rôles attendus ne sont pas exactement présents")

    for spec in specs:
        if not spec.name or not spec.model or not spec.fallback or not spec.mission:
            failures.append(f"agents: contrat incomplet pour {spec.agent_id}")
        role_root = repo_root / "agents" / spec.agent_id
        for filename in ROLE_FILES:
            if not (role_root / filename).is_file():
                failures.append(f"agents: {spec.agent_id}/{filename} absent")
    return tuple(failures)


def _copy_policy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    destination.chmod(0o640)


def deploy_workspaces(repo_root: Path, runtime_root: Path) -> tuple[Path, ...]:
    failures = validate_agent_assets(repo_root)
    if failures:
        raise ValueError("; ".join(failures))

    policy = core_contract(repo_root, "openclaw_policy.yaml")
    workspace_policy = policy.get("workspace", {})
    marker_name = str(workspace_policy.get("managed_marker", ".openclaw-fedora-managed"))
    shared_root = repo_root / "agents" / "_shared"
    workspaces_root = runtime_root / "workspaces"
    workspaces_root.mkdir(parents=True, exist_ok=True)
    deployed: list[Path] = []

    for spec in load_agent_specs(repo_root):
        workspace = workspaces_root / spec.agent_id
        marker = workspace / marker_name
        if workspace.exists() and any(workspace.iterdir()) and not marker.is_file():
            raise PermissionError(f"workspace non géré refusé: {workspace}")
        workspace.mkdir(parents=True, exist_ok=True)
        workspace.chmod(0o750)

        for filename in ROLE_FILES:
            _copy_policy_file(repo_root / "agents" / spec.agent_id / filename, workspace / filename)
        for filename in SHARED_FILES:
            _copy_policy_file(shared_root / filename, workspace / filename)

        (workspace / "projects").mkdir(exist_ok=True)
        marker_payload = {
            "schema_version": "1.0.0",
            "agent_id": spec.agent_id,
            "managed_by": "OPENCLAW_LOCAL_FEDORA",
        }
        marker.write_text(
            json.dumps(marker_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        marker.chmod(0o600)
        deployed.append(workspace)

    return tuple(deployed)
