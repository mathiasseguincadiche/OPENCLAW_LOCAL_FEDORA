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
    assert len(specs) == 6
    assert specs[0].agent_id == "chef-operations"
    assert {spec.model for spec in specs} == {"qwen-max"}


def test_deploy_workspaces_is_managed_and_idempotent(tmp_path: Path) -> None:
    deployed = deploy_workspaces(ROOT, tmp_path)
    assert len(deployed) == 6
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


def test_toolkit_assets_are_required_before_workspace_deployment(tmp_path: Path) -> None:
    import shutil

    shutil.copytree(ROOT / "agents", tmp_path / "agents")
    shutil.copytree(ROOT / "config", tmp_path / "config")
    assert any("toolkit" in failure for failure in validate_agent_assets(tmp_path))
    shutil.copytree(ROOT / "plugins", tmp_path / "plugins")
    assert validate_agent_assets(tmp_path) == ()
    manifest = tmp_path / "plugins/clawfedora-toolkit/openclaw.plugin.json"
    data = json.loads(manifest.read_text())
    data["contracts"]["tools"] = []
    manifest.write_text(json.dumps(data))
    assert any("divergent" in failure for failure in validate_agent_assets(tmp_path))
