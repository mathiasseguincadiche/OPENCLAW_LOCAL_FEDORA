"""Realistic, offline acceptance tests with versioned GitHub and private Notion."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from clawfedora import github_refresh, retrieval_acceptance, source_connectors
from clawfedora.knowledge import build_index
from clawfedora.project_intake import create_project
from clawfedora.project_retrieval import retrieve

ROOT = Path(__file__).resolve().parents[1]
REPO = "example/OpsDesk"
OLD = "a" * 40
NEW = "b" * 40
PAGE = "1" * 32


@pytest.fixture
def workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path]:
    runtime = tmp_path / "runtime"
    brief = tmp_path / "brief.md"
    brief.write_text("Projet InfraOps Terraform et Ansible", encoding="utf-8")
    project = create_project(
        ROOT, runtime, "cross-search", "Recherche croisée", intake_items=[brief]
    )

    def github(dest: Path, repo: str, commit: str) -> dict[str, Any]:
        assert repo == REPO
        if commit == OLD:
            documents = {
                "infra/main.tf": "Terraform legacy_backend frozen old-code.",
                "docs/readme.md": "Ancien snapshot du service legacy_backend.",
            }
        else:
            assert commit == NEW
            documents = {
                "infra/main.tf": "Terraform bridge_network source approuvée.",
                "ops/ansible.yml": "Ansible bridge_network deploiement cible.",
                "docs/readme.md": "Revue de l'architecture bridge_network.",
            }
        for name, value in documents.items():
            target = dest / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(value, encoding="utf-8")
        return {
            "provider": "github", "repository": repo, "commit": commit,
            "file_count": len(documents), "skipped": 0,
        }

    def notion(dest: Path, page_id: str, include_children: bool) -> dict[str, Any]:
        assert page_id == PAGE and include_children is False
        (dest / "architecture.md").write_text(
            "# Architecture privée\nTerraform bridge_network procédure "
            "de vérification, rôle Ansible et journal de formation.\n",
            encoding="utf-8",
        )
        return {
            "provider": "notion", "page_id": page_id,
            "classification": "private_local_only", "file_count": 1,
        }

    monkeypatch.setattr(source_connectors, "_github_snapshot", github)
    monkeypatch.setattr(source_connectors, "_notion_snapshot", notion)
    source_connectors.import_snapshot(
        ROOT, runtime, project.name, github=REPO, commit=OLD
    )
    source_connectors.import_snapshot(
        ROOT, runtime, project.name, notion_page=PAGE
    )
    build_index(ROOT, project)
    preview = github_refresh.refresh(runtime, project.name, REPO, NEW)
    github_refresh.refresh(
        runtime, project.name, REPO, NEW,
        approve=preview["approve_sha256"], apply=True,
    )
    return runtime, project





def _write_cases(tmp_path: Path, cases: list[dict[str, object]]) -> Path:
    file = tmp_path / "acceptance.json"
    file.write_text(
        json.dumps({"schema_version": 1, "cases": cases}), encoding="utf-8"
    )
    return file


def _positive() -> dict[str, object]:
    return {
        "id": "git-notion-cross",
        "query": "Terraform bridge_network Ansible",
        "required_paths_contain": ["github:", "Notion-"],
        "forbidden_paths_contain": ["intake/GitHub-"],
        "minimum_hits": 3,
        "minimum_distinct_sources": 3,
    }


def _negative() -> dict[str, object]:
    return {
        "id": "removed-legacy-backend",
        "query": "legacy_backend",
        "expect_empty": True,
        "minimum_hits": 0,
        "minimum_distinct_sources": 0,
    }


def test_real_local_suite_reports_coverage_citations_and_negative_query(
    workspace: tuple[Path, Path], tmp_path: Path,
) -> None:
    _runtime, project = workspace
    config = _write_cases(tmp_path, [_positive(), _negative()])
    before = sorted(
        str(path.relative_to(project)) for path in project.rglob("*")
    )
    report = retrieval_acceptance.evaluate(ROOT, project, config)
    after = sorted(
        str(path.relative_to(project)) for path in project.rglob("*")
    )
    assert report["status"] == "PASS"
    assert report["passed"] == report["total"] == 2
    assert report["sent_to_cloud"] is False
    assert report["agent_answer_graded"] is False
    assert report["operator_skill_certified"] is False
    first, negative = report["cases"]
    assert first["status"] == "PASS"
    assert first["expected_coverage"] == 1
    assert first["distinct_sources"] >= 3
    assert all(
        level == "TEXT_AND_POSITION_VERIFIED"
        for level in first["citation_checks"]
    )
    assert negative["status"] == "PASS"
    assert negative["hit_count"] == 0
    assert before == after
    # Raw private Notion pages and snippets never appear in acceptance reports.
    raw = json.dumps(report, ensure_ascii=False)
    assert "Architecture privée" not in raw
    assert "journal de formation" not in raw


def test_missing_expected_source_fails_without_silent_assumption(
    workspace: tuple[Path, Path], tmp_path: Path,
) -> None:
    _runtime, project = workspace
    case = {**_positive(), "required_paths_contain": ["github:", "Notion-", "nonexistent.md"]}
    report = retrieval_acceptance.evaluate(
        ROOT, project, _write_cases(tmp_path, [case])
    )
    assert report["status"] == "FAIL"
    assert report["cases"][0]["expected_coverage"] < 1
    assert report["cases"][0]["conditions"]["expected_coverage"] is False


def test_obsolete_source_is_not_citable_and_corruption_fails_closed(
    workspace: tuple[Path, Path], tmp_path: Path,
) -> None:
    _runtime, project = workspace
    report = retrieval_acceptance.evaluate(
        ROOT, project, _write_cases(tmp_path, [_negative()])
    )
    assert report["status"] == "PASS"
    # Even when the old code is indexed and still readable, it is no
    # longer part of the approved latest GitHub retrieval view.
    assert retrieve(ROOT, project, "legacy_backend") == []
    new_file = next((project / "context/github-updates").glob("*/" + "b" * 40 + "/files/infra/main.tf"))
    new_file.write_text("modified without approval", encoding="utf-8")
    with pytest.raises(ValueError, match="modifié"):
        retrieval_acceptance.evaluate(
            ROOT, project, _write_cases(tmp_path, [_positive()])
        )


def test_scenario_validation_rejects_missing_expectations_and_symlinks(
    workspace: tuple[Path, Path], tmp_path: Path,
) -> None:
    _runtime, project = workspace
    bad = {**_positive(), "required_paths_contain": []}
    with pytest.raises(ValueError, match="source attendue"):
        retrieval_acceptance.evaluate(
            ROOT, project, _write_cases(tmp_path, [bad])
        )
    with pytest.raises(ValueError, match="requête"):
        retrieval_acceptance.evaluate(
            ROOT, project, _write_cases(
                tmp_path, [{**_positive(), "query": "x" * 1001}]
            )
        )
    source = _write_cases(tmp_path, [_positive()])
    alias = tmp_path / "linked-acceptance.json"
    alias.symlink_to(source)
    with pytest.raises(ValueError, match="lié"):
        retrieval_acceptance.evaluate(ROOT, project, alias)


def test_no_github_or_notion_network_calls_during_acceptance(
    workspace: tuple[Path, Path], tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _runtime, project = workspace

    def forbidden(*_args: object, **_kwargs: object) -> object:
        pytest.fail("retrieval must not query any external connector")

    monkeypatch.setattr(source_connectors, "_get_json", forbidden)
    assert retrieval_acceptance.evaluate(
        ROOT, project, _write_cases(tmp_path, [_positive()])
    )["status"] == "PASS"


def test_cli_outputs_metadata_and_exit_status(
    workspace: tuple[Path, Path], tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runtime, _project = workspace
    config = _write_cases(tmp_path, [_positive()])
    argv = [
        "--runtime-root", str(runtime), "--project-id", "cross-search",
        "--cases", str(config),
    ]
    assert retrieval_acceptance.main(argv) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "PASS"
    assert "sent_to_cloud" in result and result["sent_to_cloud"] is False

    failing = _write_cases(
        tmp_path, [{**_positive(), "required_paths_contain": ["unseen-file"]}]
    )
    assert retrieval_acceptance.main([*argv[:-1], str(failing)]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "FAIL"

    unknown = tmp_path / "missing.json"
    assert retrieval_acceptance.main([*argv[:-1], str(unknown)]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "REFUSED"


def test_legacy_fts_reference_can_be_explicitly_rejected(
    workspace: tuple[Path, Path], tmp_path: Path,
) -> None:
    _runtime, project = workspace
    report = retrieval_acceptance.evaluate(
        ROOT, project, _write_cases(
            tmp_path, [{
                **_positive(),
                "required_paths_contain": ["github:"],
                "forbidden_paths_contain": [f"GitHub-{REPO.replace('/', '-')}-{OLD[:12]}"],
                "minimum_hits": 1,
                "minimum_distinct_sources": 1,
            }]
        )
    )
    assert report["status"] == "PASS"
    assert report["cases"][0]["conditions"]["no_forbidden_paths"]
