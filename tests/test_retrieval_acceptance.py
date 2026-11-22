"""Realistic, offline acceptance tests with versioned GitHub and private Notion."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from clawfedora import retrieval_acceptance, source_connectors
from clawfedora.project_retrieval import retrieve
from test_project_retrieval import OLD, REPO, workspace

ROOT = Path(__file__).resolve().parents[1]


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
