"""Regression contract for the three read-only hybrid features after merging PRs.

The combined feature set cannot authorize cloud, inspect private conversations,
write to project state, or turn an unverified report into a runtime deployment.
"""

from __future__ import annotations

import runpy
import tomllib
from pathlib import Path
from typing import Any

import pytest

from clawfedora import chat_projects, ci_evidence
from clawfedora.cloud_budget import load_ledger
from clawfedora.model_advice import advise

ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 40


def test_all_readonly_entrypoints_exist_without_cloud_permission() -> None:
    scripts = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["scripts"]
    assert scripts["clawfedora-ci-proof"] == "clawfedora.ci_evidence:main"
    assert scripts["clawfedora-evals"] == "clawfedora.agent_eval:main"
    assert scripts["clawfedora-lab"] == "clawfedora.devops_lab:main"

    actions = runpy.run_path(str(ROOT / "plugins/openwebui/clawfedora_project_actions.py"))
    assert actions["READ_ONLY_ACTIONS"] == {
        "projects": "!projets",
        "status": "!etat",
        "sources": "!sources",
        "help": "!aide",
        "models": "!modele",
        "budget": "!budget",
    }
    assert {"modele", "budget"} <= set(chat_projects.COMMANDS)
    assert "modifier" not in actions["READ_ONLY_ACTIONS"].values()
    assert "livrer" not in actions["READ_ONLY_ACTIONS"].values()


def test_provenance_and_local_guidance_cannot_claim_production_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def official(url: str) -> dict[str, Any]:
        calls.append(url)
        return {
            "id": 987, "head_sha": SHA,
            "status": "completed", "conclusion": "success",
        }

    monkeypatch.setattr(ci_evidence, "_json_get", official)
    report = ci_evidence.verify_public_run("github", "octo/repo", 987, SHA)
    assert report["verdict"] == "VERIFIED_RUN_SUCCESS"
    assert report["scope"] == "pipeline_result_only"
    assert "rollback" in report["warning"]
    assert calls == ["https://api.github.com/repos/octo/repo/actions/runs/987"]

    for request in ("iac", "confidentiel", ""):
        hint = advise(request)
        assert "Aucune route OpenRouter" in hint
        assert "sans analyse des documents" in hint


def test_budget_hint_is_local_and_cannot_mutate_project_state(tmp_path: Path) -> None:
    (tmp_path / "state").mkdir()
    before = sorted(
        (p.relative_to(tmp_path).as_posix(), p.read_bytes())
        for p in tmp_path.rglob("*") if p.is_file()
    )
    for command, arg in (("modele", "iac"), ("modele", ""), ("budget", "")):
        reply = chat_projects.run_command(ROOT, tmp_path, command, arg, None)
        assert reply.startswith("📁 Aucun projet · pont")
        assert "local" in reply.lower() or "Ornith" in reply
    after = sorted(
        (p.relative_to(tmp_path).as_posix(), p.read_bytes())
        for p in tmp_path.rglob("*") if p.is_file()
    )
    assert before == after
    assert "aucun budget API" in chat_projects.run_command(
        ROOT, tmp_path, "budget", "", None
    )
