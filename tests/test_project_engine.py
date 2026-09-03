from __future__ import annotations

import os
from pathlib import Path

import pytest

from clawfedora.artifact_exchange import validate_bundle
from clawfedora.project_common import read_json
from clawfedora.project_engine import (
    create_assignments,
    create_clarifications,
    current_status,
    package_project,
    ready_tasks,
    record_task_result,
    resolve_clarification,
    store_analysis,
    store_plan,
    store_verdict,
    transition_project,
)
from clawfedora.project_intake import create_project

ROOT = Path(__file__).resolve().parents[1]


def _project(tmp_path: Path) -> Path:
    request = tmp_path / "request.md"
    request.write_text("Construire et documenter.", encoding="utf-8")
    return create_project(
        ROOT,
        tmp_path / "runtime",
        "engine-project",
        "Engine",
        intake_items=[request],
    )


def _analysis(project: Path) -> dict[str, object]:
    index = read_json(project / "context" / "ingestion" / "index.json")
    documents = index["documents"]
    assert isinstance(documents, list)
    coverage = [
        {
            "document_id": item["document_id"],
            "status": "READ",
            "method": item["method"],
        }
        for item in documents
        if isinstance(item, dict)
    ]
    return {
        "summary": "Projet compris.",
        "objectives": ["produire"],
        "constraints": ["local"],
        "deliverables": ["rapport"],
        "ambiguities": [],
        "missing_information": [],
        "risks": [],
        "decisions_required": [],
        "source_coverage": coverage,
    }


def _plan() -> dict[str, object]:
    return {
        "workstreams": ["build", "doc"],
        "tasks": [
            {
                "id": "build-output",
                "role": "ingenieur-devops",
                "title": "Construire",
                "objective": "Créer la sortie technique",
                "depends_on": [],
                "expected_outputs": ["work/build-output/result.txt"],
                "acceptance_criteria": ["fichier présent"],
            },
            {
                "id": "write-doc",
                "role": "redacteur-technique",
                "title": "Documenter",
                "objective": "Créer la documentation",
                "depends_on": ["build-output"],
                "expected_outputs": ["deliverables/write-doc/final.md"],
                "acceptance_criteria": ["documentation présente"],
            },
        ],
    }


def _analyze(project: Path) -> None:
    store_analysis(ROOT, project, _analysis(project))
    create_clarifications(ROOT, project)
    transition_project(
        ROOT,
        project,
        "ANALYZED",
        actor="chef-operations",
        reason="analysis",
    )


def _start_single_task(project: Path) -> None:
    _analyze(project)
    plan = _plan()
    tasks = plan["tasks"]
    assert isinstance(tasks, list)
    plan["tasks"] = [tasks[0]]
    store_plan(ROOT, project, plan)
    transition_project(
        ROOT,
        project,
        "PLANNED",
        actor="chef-operations",
        reason="plan",
    )
    create_assignments(ROOT, project)
    transition_project(
        ROOT,
        project,
        "ASSIGNED",
        actor="chef-operations",
        reason="assign",
    )
    transition_project(
        ROOT,
        project,
        "IN_PROGRESS",
        actor="chef-operations",
        reason="execute",
    )


def _pass_single_task(project: Path) -> None:
    output = project / "work" / "build-output" / "result.txt"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("PASS", encoding="utf-8")
    record_task_result(
        ROOT,
        project,
        task_id="build-output",
        agent="ingenieur-devops",
        status="PASS",
        outputs=["work/build-output/result.txt"],
        summary="ok",
    )


def test_complete_project_lifecycle_requires_human_approval(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _analyze(project)
    store_plan(ROOT, project, _plan())
    transition_project(
        ROOT,
        project,
        "PLANNED",
        actor="chef-operations",
        reason="plan",
    )
    create_assignments(ROOT, project)
    transition_project(
        ROOT,
        project,
        "ASSIGNED",
        actor="chef-operations",
        reason="assign",
    )
    transition_project(
        ROOT,
        project,
        "IN_PROGRESS",
        actor="chef-operations",
        reason="execute",
    )

    first = project / "work" / "build-output" / "result.txt"
    first.parent.mkdir(parents=True)
    first.write_text("PASS", encoding="utf-8")
    record_task_result(
        ROOT,
        project,
        task_id="build-output",
        agent="ingenieur-devops",
        status="PASS",
        outputs=["work/build-output/result.txt"],
        summary="construction validée",
    )
    assert [item["task_id"] for item in ready_tasks(ROOT, project)] == [
        "write-doc"
    ]

    second = project / "deliverables" / "write-doc" / "final.md"
    second.parent.mkdir(parents=True)
    second.write_text("# Final\n", encoding="utf-8")
    record_task_result(
        ROOT,
        project,
        task_id="write-doc",
        agent="redacteur-technique",
        status="PASS",
        outputs=["deliverables/write-doc/final.md"],
        summary="documentation validée",
    )
    transition_project(
        ROOT,
        project,
        "VALIDATING",
        actor="auditeur-qualite",
        reason="tasks-pass",
    )
    store_verdict(
        ROOT,
        project,
        "validation",
        "PASS",
        [],
        reviewer="auditeur-qualite",
    )
    transition_project(
        ROOT,
        project,
        "REVIEW",
        actor="auditeur-qualite",
        reason="validation-pass",
    )
    store_verdict(
        ROOT,
        project,
        "review",
        "PASS",
        [],
        reviewer="auditeur-qualite",
    )
    manifest_path, report_path = package_project(
        ROOT,
        project,
        actor="ingenieur-release-forges",
    )
    assert manifest_path.is_file() and report_path.is_file()
    with pytest.raises(PermissionError, match="humaine"):
        transition_project(
            ROOT,
            project,
            "COMPLETE",
            actor="robot",
            reason="no",
            human_approved=False,
        )
    transition_project(
        ROOT,
        project,
        "COMPLETE",
        actor="human-owner",
        reason="approved",
        human_approved=True,
    )
    assert current_status(project) == "COMPLETE"


def test_plan_cycle_is_rejected(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _analyze(project)
    bad = _plan()
    tasks = bad["tasks"]
    assert isinstance(tasks, list)
    tasks[0]["depends_on"] = ["write-doc"]
    with pytest.raises(ValueError, match="cycle"):
        store_plan(ROOT, project, bad)


def test_pdf_requires_real_pdf_tool_coverage(tmp_path: Path) -> None:
    pdf = tmp_path / "spec.pdf"
    pdf.write_bytes(b"%PDF-1.7\n")
    project = create_project(
        ROOT,
        tmp_path / "runtime",
        "pdf-project",
        "PDF",
        intake_items=[pdf],
    )
    analysis = _analysis(project)
    coverage = analysis["source_coverage"]
    assert isinstance(coverage, list)
    coverage[0]["method"] = "raw_file"
    with pytest.raises(ValueError, match="lecture réelle via pdf"):
        store_analysis(ROOT, project, analysis)
    coverage[0]["method"] = "pdf"
    store_analysis(ROOT, project, analysis)


def test_input_tamper_blocks_analysis(tmp_path: Path) -> None:
    project = _project(tmp_path)
    source = project / "intake" / "request.md"
    if os.name != "nt":
        source.chmod(0o644)
    source.write_text("TAMPER", encoding="utf-8")
    with pytest.raises(ValueError, match="intégrité des entrées invalide"):
        store_analysis(ROOT, project, _analysis(project))


def test_blocking_clarification_must_be_resolved(tmp_path: Path) -> None:
    project = _project(tmp_path)
    analysis = _analysis(project)
    analysis["ambiguities"] = ["Quelle cible de livraison ?"]
    store_analysis(ROOT, project, analysis)
    create_clarifications(ROOT, project)
    transition_project(
        ROOT,
        project,
        "ANALYZED",
        actor="chef-operations",
        reason="analysis",
    )
    transition_project(
        ROOT,
        project,
        "CLARIFICATION_REQUIRED",
        actor="chef-operations",
        reason="blocking-question",
    )
    with pytest.raises(ValueError, match="non résolues"):
        transition_project(
            ROOT,
            project,
            "ANALYZED",
            actor="human",
            reason="too-early",
        )
    resolve_clarification(
        ROOT,
        project,
        "clarification-001",
        "Livraison Markdown",
    )
    transition_project(
        ROOT,
        project,
        "ANALYZED",
        actor="human",
        reason="resolved",
    )
    assert current_status(project) == "ANALYZED"


def test_validation_is_reserved_to_quality_auditor(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _start_single_task(project)
    _pass_single_task(project)
    transition_project(
        ROOT,
        project,
        "VALIDATING",
        actor="auditeur-qualite",
        reason="tasks-pass",
    )
    with pytest.raises(PermissionError, match="auditeur-qualite"):
        store_verdict(
            ROOT,
            project,
            "validation",
            "PASS",
            [],
            reviewer="ingenieur-devops",
        )


def test_bundle_tamper_blocks_validation(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _start_single_task(project)
    output = project / "work" / "build-output" / "result.txt"
    output.parent.mkdir(parents=True)
    output.write_text("PASS", encoding="utf-8")
    result = record_task_result(
        ROOT,
        project,
        task_id="build-output",
        agent="ingenieur-devops",
        status="PASS",
        outputs=["work/build-output/result.txt"],
        summary="ok",
    )
    bundle = project / result["bundles"][0]
    artifact = bundle / "artifacts" / "work" / "build-output" / "result.txt"
    if os.name != "nt":
        assert artifact.stat().st_mode & 0o222 == 0
        artifact.chmod(0o644)
    artifact.write_text("TAMPER", encoding="utf-8")
    assert validate_bundle(project, bundle)
    with pytest.raises(ValueError, match="artifact exchange invalide"):
        transition_project(
            ROOT,
            project,
            "VALIDATING",
            actor="auditeur-qualite",
            reason="tampered",
        )


def test_package_tamper_blocks_complete(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _start_single_task(project)
    _pass_single_task(project)
    transition_project(
        ROOT,
        project,
        "VALIDATING",
        actor="auditeur-qualite",
        reason="tasks-pass",
    )
    store_verdict(
        ROOT,
        project,
        "validation",
        "PASS",
        [],
        reviewer="auditeur-qualite",
    )
    transition_project(
        ROOT,
        project,
        "REVIEW",
        actor="auditeur-qualite",
        reason="validation-pass",
    )
    store_verdict(
        ROOT,
        project,
        "review",
        "PASS",
        [],
        reviewer="auditeur-qualite",
    )
    deliverable = project / "deliverables" / "build-output" / "final.md"
    deliverable.parent.mkdir(parents=True, exist_ok=True)
    deliverable.write_text("original", encoding="utf-8")
    package_project(ROOT, project, actor="ingenieur-release-forges")
    deliverable.write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="package final invalide"):
        transition_project(
            ROOT,
            project,
            "COMPLETE",
            actor="human-owner",
            reason="approved",
            human_approved=True,
        )
