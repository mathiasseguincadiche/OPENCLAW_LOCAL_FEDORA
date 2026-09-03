from __future__ import annotations

import json
from pathlib import Path

import pytest

from clawfedora.project_common import read_json
from clawfedora.project_engine import (
    create_assignments,
    create_clarifications,
    record_task_result,
    store_analysis,
    store_plan,
    transition_project,
)
from clawfedora.project_intake import create_project

ROOT = Path(__file__).resolve().parents[1]


def test_corrupt_result_history_is_rejected_before_task_promotion(
    tmp_path: Path,
) -> None:
    request = tmp_path / "request.md"
    request.write_text("Créer une sortie.", encoding="utf-8")
    project = create_project(
        ROOT,
        tmp_path / "runtime",
        "transaction-project",
        "Transaction",
        intake_items=[request],
    )
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
    store_analysis(
        ROOT,
        project,
        {
            "summary": "Créer une sortie.",
            "objectives": ["sortie"],
            "constraints": [],
            "deliverables": [],
            "ambiguities": [],
            "missing_information": [],
            "risks": [],
            "decisions_required": [],
            "source_coverage": coverage,
        },
    )
    create_clarifications(ROOT, project)
    transition_project(
        ROOT,
        project,
        "ANALYZED",
        actor="chef-operations",
        reason="analysis",
    )
    store_plan(
        ROOT,
        project,
        {
            "workstreams": ["build"],
            "tasks": [
                {
                    "id": "build-output",
                    "role": "ingenieur-devops",
                    "title": "Build",
                    "objective": "Créer le résultat",
                    "depends_on": [],
                    "expected_outputs": ["work/build-output/result.txt"],
                    "acceptance_criteria": ["présent"],
                }
            ],
        },
    )
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

    history = project / "evidence" / "task_results.json"
    history.write_text(json.dumps({"results": {}}), encoding="utf-8")
    output = project / "work" / "build-output" / "result.txt"
    output.parent.mkdir(parents=True)
    output.write_text("PASS", encoding="utf-8")

    with pytest.raises(ValueError, match="task_results: results invalide"):
        record_task_result(
            ROOT,
            project,
            task_id="build-output",
            agent="ingenieur-devops",
            status="PASS",
            outputs=["work/build-output/result.txt"],
            summary="should-not-promote",
        )

    assignments = read_json(project / "context" / "task_assignments.json")
    tasks = assignments["tasks"]
    assert isinstance(tasks, list)
    assert tasks[0]["status"] == "PENDING"
    assert tasks[0]["attempts"] == 0
    assert not (project / "context" / "exchange" / "build-output").exists()
