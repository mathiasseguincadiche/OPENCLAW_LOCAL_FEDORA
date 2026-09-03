from __future__ import annotations

import json
from pathlib import Path

import pytest

from clawfedora.agents import deploy_workspaces, load_agent_specs, validate_agent_assets
from clawfedora.core_config import AGENT_IDS

ROOT = Path(__file__).resolve().parents[1]


def test_agent_assets_and_specs_are_complete() -> None:
    assert validate_agent_assets(ROOT) == ()
    specs = load_agent_specs(ROOT)
    assert tuple(spec.agent_id for spec in specs) == AGENT_IDS
    assert len(specs) == 8
    assert specs[0].agent_id == "chef-operations"
    assert {spec.model for spec in specs} == {"qwen-max", "gemma-deep", "devstral-devops"}


def test_deploy_workspaces_is_managed_and_idempotent(tmp_path: Path) -> None:
    deployed = deploy_workspaces(ROOT, tmp_path)
    assert len(deployed) == 8
    for workspace in deployed:
        marker = workspace / ".openclaw-fedora-managed"
        payload = json.loads(marker.read_text(encoding="utf-8"))
        assert payload["agent_id"] == workspace.name
        for filename in ("AGENTS.md", "IDENTITY.md", "SOUL.md", "CONTRACT.md", "TOOLS.md"):
            assert (workspace / filename).is_file()
        assert (workspace / "projects").is_dir()

    deployed_again = deploy_workspaces(ROOT, tmp_path)
    assert deployed_again == deployed


def test_deploy_refuses_unmanaged_nonempty_workspace(tmp_path: Path) -> None:
    unmanaged = tmp_path / "workspaces" / "chef-operations"
    unmanaged.mkdir(parents=True)
    (unmanaged / "foreign.txt").write_text("do not overwrite", encoding="utf-8")
    with pytest.raises(PermissionError, match="workspace non géré"):
        deploy_workspaces(ROOT, tmp_path)
