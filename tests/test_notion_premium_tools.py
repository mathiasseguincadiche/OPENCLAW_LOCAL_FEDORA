"""Premium Notion helpers: actual compiler, scoped read-only inventory and role isolation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from clawfedora.agent_tools import invoke
from clawfedora.agents import deploy_workspaces
from clawfedora.notion_premium_tools import inventory, studio_check

ROOT = Path(__file__).resolve().parents[1]


def _snapshot(root: Path) -> Path:
    target = root / "Notion-example"
    target.mkdir()
    pages = [{"id": "a" * 32, "title": "Comprendre"},
             {"id": "b" * 32, "title": "Préparer"}]
    (target / ".source-provenance.json").write_text(json.dumps({
        "provider": "notion", "classification": "private_local_only",
        "read_only": True, "attachments": "excluded",
        "root_page": pages[0]["id"], "page_count": 2, "pages": pages,
    }))
    (target / ("page-" + "a" * 32 + ".md")).write_text(
        "# Comprendre\n\n## Diagnostic\n\n## Diagnostic\n\n"
        "```bash\n## Installation des outils\n```\n",
    )
    (target / ("page-" + "b" * 32 + ".md")).write_text(
        "# Préparer\n\n## Installation des outils\n\n## Diagnostic\n",
    )
    return target


def test_inventory_detects_candidates_without_disclosing_content(tmp_path: Path) -> None:
    target = _snapshot(tmp_path)
    before = {p.name: p.read_bytes() for p in target.iterdir()}
    result = inventory(tmp_path, target.name)
    assert result["assessment"] == "INVENTORY_REVIEW_REQUIRED"
    assert result["remote_write"] is False and result["remote_read"] is False
    assert result["spaces_title_present"]["comprendre"] is True
    assert result["installation_locations"] == [{"page_id": "b" * 32, "line": 3}]
    assert {r["kind"] for r in result["findings"]} == {
        "REPEATED_HEADING", "CROSS_PAGE_HEADING",
    }
    assert "Diagnostic" not in json.dumps(result)
    assert before == {p.name: p.read_bytes() for p in target.iterdir()}


def test_inventory_refuses_escape_symlink_and_invalid_provenance(tmp_path: Path) -> None:
    target = _snapshot(tmp_path)
    (tmp_path / "linked").symlink_to(target)
    for scope in ("../outside", str(target), "linked", ".", "missing"):
        with pytest.raises(ValueError):
            inventory(tmp_path, scope)
    source = target / ".source-provenance.json"
    source.write_text("{}")
    with pytest.raises(ValueError):
        inventory(tmp_path, target.name)


def test_studio_compiler_and_premium_requirements() -> None:
    raw = (ROOT / "docs/editorial-demo/studio-spec.json").read_text()
    result = studio_check(raw)
    assert result["compiler_valid"] is True
    assert result["assessment"] == "STRUCTURE_REVIEW_REQUIRED"
    assert result["remote_write"] is False
    spec = json.loads(raw)
    spec["pages"] = spec["pages"][:1]
    spec["tracker"] = None
    result = studio_check(json.dumps(spec))
    assert result["assessment"] == "REVISE_STRUCTURE"
    assert any("Installation" in issue for issue in result["issues"])
    assert any("suivi unique" in issue for issue in result["issues"])
    with pytest.raises(ValueError):
        studio_check("{}")


def test_agent_tools_are_scoped_and_discoverable(tmp_path: Path) -> None:
    deploy_workspaces(ROOT, tmp_path)
    role = "redacteur-pedagogique"
    workspace = tmp_path / "workspaces" / role
    raw = (ROOT / "docs/editorial-demo/studio-spec.json").read_text()
    assert invoke(tmp_path, role, workspace, "clawfedora_notion_studio_check",
                  {"content": raw})["compiler_valid"]
    source = _snapshot(workspace)
    assert invoke(tmp_path, role, workspace, "clawfedora_notion_inventory",
                  {"scope": source.name})["pages"]
    status = invoke(tmp_path, role, workspace, "clawfedora_tool_status", {})
    assert "clawfedora_notion_studio_check" in status["role_tools"]
    other = "ingenieur-devops"
    with pytest.raises(ValueError, match="outil interdit"):
        invoke(tmp_path, other, tmp_path / "workspaces" / other,
               "clawfedora_notion_studio_check", {"content": raw})
