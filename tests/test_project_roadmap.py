from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from clawfedora.project_cli import add_project_parser
from clawfedora.project_common import read_json, write_json
from clawfedora.project_intake import create_project
from clawfedora.project_roadmap import change, initialize, load
from clawfedora.project_ui import details

ROOT = Path(__file__).resolve().parents[1]


def project(tmp_path: Path) -> Path:
    request = tmp_path / "request.md"
    request.write_text("Projet InfraOps de longue durée.", encoding="utf-8")
    return create_project(
        ROOT, tmp_path / "runtime", "long-project", "Projet long", intake_items=[request]
    )


def definitions() -> dict[str, object]:
    return {
        "milestones": [
            {"id": "exercice-01", "title": "Contrat applicatif", "depends_on": []},
            {"id": "exercice-02", "title": "Terraform", "depends_on": ["exercice-01"]},
            {"id": "exercice-03", "title": "Ansible", "depends_on": ["exercice-02"]},
        ]
    }


def test_roadmap_persists_without_changing_agent_plan_or_project_status(tmp_path: Path) -> None:
    directory = project(tmp_path)
    original = read_json(directory / "project.json")
    expected = definitions()
    preview = initialize(directory, expected)
    assert preview["applied"] is False
    assert not (directory / "context/continuous_roadmap.json").exists()

    created = initialize(directory, expected, apply=True)
    assert created["milestone_count"] == 3
    assert load(directory)["milestones"][1]["state"] == "PLANNED"
    with pytest.raises(FileExistsError, match="déjà présente"):
        initialize(directory, expected, apply=True)

    preview_change = change(directory, "exercice-01", "IN_PROGRESS", "Je prépare le labo.")
    assert preview_change["applied"] is False
    assert load(directory)["milestones"][0]["state"] == "PLANNED"
    change(directory, "exercice-01", "IN_PROGRESS", "Laboratoire préparé.", apply=True)
    change(directory, "exercice-01", "IMPLEMENTED", "Travail réalisé, non vérifié.", apply=True)
    assert load(directory)["milestones"][0]["verification"] == "NOT_VERIFIED"
    assert len(load(directory)["history"]) == 2
    assert read_json(directory / "project.json") == original
    assert not (directory / "context/project_plan.json").exists()


@pytest.mark.parametrize(
    "invalid",
    [
        {"milestones": [{"id": "step-01", "title": "A", "depends_on": ["missing"]}]},
        {"milestones": [{"id": "step-01", "title": "A", "depends_on": ["step-01"]}]},
        {
            "milestones": [
                {"id": "step-01", "title": "A", "depends_on": ["step-02"]},
                {"id": "step-02", "title": "B", "depends_on": ["step-01"]},
            ]
        },
        {
            "milestones": [
                {"id": "step-01", "title": "A", "depends_on": []},
                {"id": "step-01", "title": "B", "depends_on": []},
            ]
        },
    ],
)
def test_roadmap_rejects_invalid_dependencies_without_writing(
    tmp_path: Path, invalid: dict[str, object]
) -> None:
    directory = project(tmp_path)
    with pytest.raises(ValueError):
        initialize(directory, invalid, apply=True)
    assert not (directory / "context/continuous_roadmap.json").exists()


def test_implementation_requires_predecessors_and_never_certifies(tmp_path: Path) -> None:
    directory = project(tmp_path)
    initialize(directory, definitions(), apply=True)
    with pytest.raises(ValueError, match="dépendances non réalisées"):
        change(directory, "exercice-02", "IMPLEMENTED", "Saisi par l'opérateur.", apply=True)
    with pytest.raises(ValueError, match="inchangé"):
        change(directory, "exercice-01", "PLANNED", "Même état.", apply=True)
    with pytest.raises(ValueError, match="état inconnu"):
        change(directory, "exercice-01", "VERIFIED", "Fausse preuve.", apply=True)
    assert load(directory)["history"] == []


def test_roadmap_refuses_symlink_and_corrupted_state(tmp_path: Path) -> None:
    directory = project(tmp_path)
    target = tmp_path / "external.json"
    target.write_text("{}", encoding="utf-8")
    path = directory / "context/continuous_roadmap.json"
    path.symlink_to(target)
    with pytest.raises(ValueError, match="symbolique"):
        initialize(directory, definitions(), apply=True)
    path.unlink()
    initialize(directory, definitions(), apply=True)
    payload = read_json(path)
    payload["milestones"][0]["verification"] = "VERIFIED"
    write_json(path, payload)
    with pytest.raises(ValueError, match="contrôle invalide"):
        load(directory)


def test_project_cli_exposes_explicit_preview_and_apply() -> None:
    parser = argparse.ArgumentParser()
    groups = parser.add_subparsers(dest="command")
    add_project_parser(groups)
    args = parser.parse_args(
        [
            "project", "roadmap-set", "--project-id", "long-project",
            "--milestone-id", "exercice-01", "--state", "IN_PROGRESS",
            "--note", "Démarrage sans preuve",
        ]
    )
    assert args.project_command == "roadmap-set"
    assert args.apply is False


def test_project_ui_exposes_only_persisted_operator_roadmap(tmp_path: Path) -> None:
    directory = project(tmp_path)
    assert details(directory)["continuous_roadmap"] is None
    initialize(directory, definitions(), apply=True)
    reported = details(directory)["continuous_roadmap"]
    assert reported["milestones"][0]["id"] == "exercice-01"
    assert reported["milestones"][0]["verification"] == "NOT_VERIFIED"
