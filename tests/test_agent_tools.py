from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from clawfedora.agent_tools import OUTLINES, TOOL_ROLES, check, diagram, invoke
from clawfedora.agents import deploy_workspaces
from clawfedora.core_config import AGENT_IDS, core_contract
from clawfedora.openclaw_config import build_openclaw_patch

ROOT = Path(__file__).resolve().parents[1]


def test_role_tools_policy_matches_callable_helpers_and_prompt_budget(tmp_path: Path) -> None:
    deploy_workspaces(ROOT, tmp_path)
    assert set(build_openclaw_patch(ROOT, tmp_path)["plugins"]["allow"]) == {
        "parallel",
        "clawfedora-toolkit",
        "memory-core",
    }
    policy = core_contract(ROOT, "tool_policy.yaml")
    for role in AGENT_IDS:
        workspace = tmp_path / "workspaces" / role
        injected = ["AGENTS.md", "SOUL.md", "IDENTITY.md", "TOOLS.md"]
        assert all(len((workspace / name).read_text()) <= 2500 for name in injected)
        assert sum(len((workspace / name).read_text()) for name in injected) <= 8000
        assert "infrastructure/OPS" in (workspace / "AGENTS.md").read_text()
        for tool, roles in TOOL_ROLES.items():
            assert (tool in policy["agents"][role]["also_allow"]) == (role in roles)
        for kind in OUTLINES[role]:
            value = invoke(tmp_path, role, workspace, "clawfedora_outline", {"kind": kind})
            assert "preuve" in value["outline"].lower()
    assert "Rédacteur technique" not in (ROOT / "agents/_shared/PEDAGOGY.md").read_text()


def test_tools_fail_closed_on_role_workspace_symlinks_and_input_size(tmp_path: Path) -> None:
    deploy_workspaces(ROOT, tmp_path)
    role = "chef-operations"
    workspace = tmp_path / "workspaces" / role
    for tool, data in [
        ("clawfedora_diagram", {"nodes": ["PC"]}),
        ("clawfedora_check", {"format": "text", "content": "test"}),
        ("unknown", {}),
        ("clawfedora_outline", {"kind": "runbook"}),
        ("clawfedora_search", {"query": "test", "scope": "../outside"}),
        ("clawfedora_search", {"query": ""}),
        ("clawfedora_search", {"query": "x" * 25000}),
    ]:
        with pytest.raises(ValueError):
            invoke(tmp_path, role, workspace, tool, data)
    with pytest.raises(ValueError, match="hors rôle"):
        invoke(tmp_path, role, tmp_path, "clawfedora_search", {"query": "test"})
    (workspace / "linked").symlink_to(tmp_path)
    with pytest.raises(ValueError, match="symbolique"):
        invoke(tmp_path, role, workspace, "clawfedora_search", {"query": "test"})
    with pytest.raises(ValueError, match="inconnu"):
        invoke(tmp_path, "other", workspace, "clawfedora_search", {})


def test_search_bounds_results_and_static_checks_never_execute_code(tmp_path: Path) -> None:
    deploy_workspaces(ROOT, tmp_path)
    role = "ingenieur-devops"
    workspace = tmp_path / "workspaces" / role
    folder = workspace / "projects/test"
    folder.mkdir()
    (folder / "logs.md").write_text("Vulkan fonctionne\n" * 10)
    value = invoke(
        tmp_path, role, workspace, "clawfedora_search", {"query": "Vulkan", "scope": "projects/test"}
    )
    assert len(value["hits"]) == 4
    assert value["hits"][0]["line"] == 1
    assert (
        invoke(
            tmp_path,
            role,
            workspace,
            "clawfedora_search",
            {"query": "absent", "scope": "projects/test"},
        )["hits"]
        == []
    )
    proposed = f"from pathlib import Path\nPath({str(tmp_path / 'never-written')!r}).touch()"
    assert check({"format": "python", "content": proposed})["runtime_tested"] is False
    assert not (tmp_path / "never-written").exists()
    assert check({"format": "json", "content": "{broken"})["findings"]
    assert check({"format": "yaml", "content": "a: ["})["findings"]
    assert check({"format": "python", "content": "def x("})["findings"]
    assert check({"format": "text", "content": "chmod 777 && setenforce 0"})["findings"]
    for data in [{"format": "bash", "content": "echo test"}, {"format": "text", "content": ""}]:
        with pytest.raises(ValueError):
            check(data)


def test_diagrams_escape_untrusted_labels_and_validate_graphs() -> None:
    value = diagram({"nodes": ["<script>alert('x')</script>", "Ollama"], "edges": [[0, 1]]})
    assert "<script>" not in value["svg"] and "&lt;script&gt;" in value["svg"]
    assert "n0 --> n1" in value["mermaid"]
    for data in [
        {"nodes": []},
        {"nodes": ["x" * 61]},
        {"nodes": ["x"], "edges": [[0, 1]]},
        {"nodes": ["x"], "edges": [[True, 0]]},
        {"nodes": ["x"], "edges": [[0]]},
    ]:
        with pytest.raises(ValueError):
            diagram(data)


def test_tool_cli_reports_errors_without_command_execution() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "clawfedora.agent_tools"],
        input="{bad",
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2 and "error" in json.loads(result.stdout)
