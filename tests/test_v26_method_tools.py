"""Evidence-limited documentation review and impact analysis (no remote mutation)."""
from __future__ import annotations

from pathlib import Path

import pytest

from clawfedora.agent_tools import invoke
from clawfedora.agents import deploy_workspaces
from clawfedora.document_impact import inspect as impact
from clawfedora.document_review import inspect_document

ROOT = Path(__file__).resolve().parents[1]


def test_impact_finds_actual_links_and_requires_notion_review(tmp_path: Path) -> None:
    (tmp_path / "docs/diagrams").mkdir(parents=True)
    (tmp_path / "docs/diagrams/infra.drawio").write_text("<mxfile/>")
    (tmp_path / "README.md").write_text(
        "# Produit\n\nVoir [source de l'architecture](docs/diagrams/infra.drawio).\n"
    )
    before = {p.relative_to(tmp_path).as_posix(): p.read_bytes()
              for p in tmp_path.rglob("*") if p.is_file()}
    report = impact(tmp_path, ["docs/diagrams/infra.drawio"])
    item = report["changes"][0]
    assert report["assessment"] == "REVIEW_QUEUE_NOT_SYNCHRONIZATION"
    assert item["direct_references"] == ["README.md"]
    assert item["potential_review"] == [{"path": "docs/diagrams/infra.svg",
                                         "state": "NOT_CHECKED"}]
    assert item["notion"] == "NOT_CHECKED_EXPLICIT_EXPORT_REQUIRED"
    assert before == {p.relative_to(tmp_path).as_posix(): p.read_bytes()
                      for p in tmp_path.rglob("*") if p.is_file()}


def test_impact_refuses_traversal_and_symlinked_snapshots(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "snapshot"
    root.mkdir()
    (root / "README.md").symlink_to(outside / "secrets.md")
    report = impact(root, ["README.md"])
    assert report["documents_scanned"] == 0
    assert report["changes"][0]["source_state"] == "NOT_CHECKED"
    for name in ("../outside", "/etc/passwd", "docs/../secret", "a\\b", ""):
        with pytest.raises(ValueError):
            impact(root, [name])
    linked = tmp_path / "linked"
    linked.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError):
        impact(linked, ["README.md"])


def test_doc_review_is_structural_not_a_fake_pass() -> None:
    content = (
        "# Restaurer le service\n\n## Préparer\nPrérequis\n\n"
        "## Procédure\nÉtapes explicitées\n\n## Vérifier\nContrôle\n\n"
        "## Dépannage\nErreurs\n\n## Retour arrière\nRollback\n"
    )
    report = inspect_document(content, "procedure")
    assert len(report["indicators"]) == 5
    assert all(x["state"] == "SIGNAL_FOUND" for x in report["indicators"])
    assert all(x["verdict"] == "NOT_EVALUATED" for x in report["reader_situations"])
    assert report["assessment"] == "STRUCTURAL_REVIEW_ONLY_NO_EDITORIAL_PASS"
    assert not report["structure"]["skipped_heading_levels_at"]
    incomplete = inspect_document("# Démo\n\n### Panne", "readme")
    assert incomplete["structure"]["skipped_heading_levels_at"]
    assert all(x["state"] == "NOT_LOCATED_IN_HEADINGS" for x in incomplete["indicators"])


def test_doc_review_ignores_headings_in_code_blocks_and_bounds_input() -> None:
    body = "# Sujet\n\n" + "\x60\x60\x60sh\n# Fausse section\n\x60\x60\x60\n\n## Vraie section\n"
    assert len(inspect_document(body, "readme")["headings"]) == 2
    for raw, kind in [("", "readme"), ("X" * 12001, "readme"),
                      ("# Exemple", "other")]:
        with pytest.raises(ValueError):
            inspect_document(raw, kind)


def test_review_tools_are_workspace_scoped_and_role_restricted(tmp_path: Path) -> None:
    deploy_workspaces(ROOT, tmp_path)
    role, writer = "ingenieur-devops", "redacteur-pedagogique"
    workspace = tmp_path / "workspaces" / role
    sample = workspace / "project-snapshot"
    sample.mkdir()
    (sample / "README.md").write_text("# Projet\n\nLien vers compose.yaml.")
    (sample / "compose.yaml").write_text("services: {}")
    result = invoke(
        tmp_path, role, workspace, "clawfedora_impact",
        {"scope": "project-snapshot", "changed_paths": ["compose.yaml"]},
    )
    assert "README.md" in result["changes"][0]["direct_references"]
    with pytest.raises(ValueError):
        invoke(tmp_path, role, workspace, "clawfedora_impact",
               {"scope": "../../outside", "changed_paths": ["compose.yaml"]})
    with pytest.raises(ValueError):
        invoke(tmp_path, role, workspace, "clawfedora_doc_review",
               {"kind": "readme", "content": "# Test"})
    other = tmp_path / "workspaces" / writer
    report = invoke(tmp_path, writer, other, "clawfedora_doc_review",
                    {"kind": "readme", "content": "# Test"})
    assert report["reader_situations"][0]["verdict"] == "NOT_EVALUATED"


def test_operational_scenario_is_only_a_separate_proposal() -> None:
    from clawfedora.project_proofs import lab_request

    request = {
        "validator": "shellcheck",
        "files": ["work/diagnostic/script.sh"],
        "expected": "Script vérifiable statiquement",
        "scenario": "restore",
        "target": "VM d'essai sans données réelles",
        "initial_state": "Archive test présente et base vide",
        "expected_observation": "Donnée témoin relue après restauration",
        "stop_condition": "Données inattendues ou permission absente",
        "recovery": "Détruire uniquement la VM jetable autorisée",
    }
    report = lab_request(request)
    assert report["status"] == "PROPOSED" and report["executed"] is False
    assert report["scenario_plan"]["proof"] == "NOT_COLLECTED"
    assert report["scenario_plan"]["state"] == "PROPOSED_NEEDS_OPERATOR_EXECUTION"
    assert "contrôle uniquement" in report["scenario_plan"]["note"]
    assert "scenario_plan" not in lab_request({key: value for key, value
                                               in request.items() if key not in
                                               {"scenario", "target", "initial_state",
                                                "expected_observation", "stop_condition",
                                                "recovery"}})
    with pytest.raises(ValueError):
        lab_request({**request, "recovery": ""})


def test_doc_review_respects_fence_type_and_length_and_reports_navigation() -> None:
    body = (
        "# Projet\n\n~~~~bash\n# Fausse installation\n~~~\n## Faux test\n"
        "~~~~\n\n## Préparer\nTexte\n## Préparer\nTexte\n\n"
        "````text\n```\n## Faux rollback\n"
    )
    report = inspect_document(body, "readme")
    assert [item["title"] for item in report["headings"]] == [
        "Projet", "Préparer", "Préparer",
    ]
    structure = report["structure"]
    assert structure["repeated_heading_lines"] == [11]
    assert structure["unclosed_code_fence_at"] == 14
    assert all(item["verdict"] == "NOT_EVALUATED" for item in report["reader_situations"])
