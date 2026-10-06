from __future__ import annotations

import base64
import json
import threading
from pathlib import Path
from typing import Any

import pytest
from test_daily_worker import planned as planned
from test_dashboard import request
from test_dashboard import server as server

from clawfedora import dashboard, project_ui
from clawfedora.dashboard import DashboardHandler, DashboardServer
from clawfedora.learning import awaiting, initialize
from clawfedora.project_common import read_json
from clawfedora.project_engine import ANALYSIS_FIELDS, current_status
from clawfedora.project_worker import review_project, run_project_tasks, worker_lock

ROOT = Path(__file__).resolve().parents[1]


def test_guided_submission_and_revision_api_require_local_explicit_human_action(
    server: DashboardServer,
) -> None:
    project = server.runtime / "projects/daily-project"
    initialize(project)

    def guide(_role: str, prompt: str, _session: str) -> dict[str, Any]:
        task = json.loads(prompt.split("\n", 1)[1])
        return {
            "files": {path: "# Amorce\n\nTODO: choisir.\n" for path in task["expected_outputs"]},
            "summary": "Comparer, choisir et vérifier.",
        }

    run_project_tasks(ROOT, server.runtime, project, runner=guide)
    item = awaiting(project)[0]
    body = {
        "project_id": project.name,
        "task_id": item["task_id"],
        "files": {path: "# Mon choix\n\nComparaison motivée." for path in item["files"]},
        "explanation": "J’ai comparé les compromis.",
        "human_approved": True,
    }
    assert request(server, "/api/practice", body, origin=False)[0] == 403
    assert request(server, "/api/practice", {**body, "human_approved": False})[0] == 400
    assert awaiting(project)
    assert request(server, "/api/practice", body)[0] == 202
    assert not awaiting(project)
    change = {"project_id": project.name, "task_id": item["task_id"], "reason": "Revoir le choix"}
    assert request(server, "/api/revision-impact", change)[1]["affected_tasks"] == [
        "design-choice",
        "research-check",
    ]
    assert request(server, "/api/revise", change)[0] == 400
    assert request(server, "/api/revise", {**change, "human_approved": True})[0] == 200
    assert current_status(project) == "IN_PROGRESS"
    assert not (project / "deliverables/design-choice/report.md").exists()


def analysis(project: Path) -> dict[str, Any]:
    value: dict[str, Any] = {key: [] for key in ANALYSIS_FIELDS}
    value["summary"] = "Comparer et expliquer une stratégie OPS"
    value["source_coverage"] = [
        {"document_id": item["document_id"], "status": "READ", "method": item["method"]}
        for item in read_json(project / "context/ingestion/index.json")["documents"]
    ]
    return value


def test_browser_workflow_uses_real_gates_and_collector_with_simulated_models(
    server: DashboardServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    status, created = request(
        server,
        "/api/create",
        {
            "title": "Sauvegarde OPS",
            "learning_mode": "direct",
            "brief": "Comparer deux stratégies; fournir critères, mécanismes et rollback.",
            "files": [
                {"name": "besoin.txt", "content": base64.b64encode(b"Fedora personnel").decode()}
            ],
        },
    )
    assert status == 201
    identifier = created["project_id"]
    project = server.runtime / "projects" / identifier
    base = {"project_id": identifier}
    assert current_status(project) == "INTAKE_READY"
    assert request(server, "/api/project?project=" + identifier)[1]["documents"]
    expected = "deliverables/choix/adr.md"
    plan = {
        "workstreams": ["documentation OPS"],
        "tasks": [
            {
                "id": "choix",
                "role": "architecte-solutions",
                "title": "Choisir",
                "objective": "Comparer et expliquer",
                "depends_on": [],
                "expected_outputs": [expected],
                "acceptance_criteria": ["Deux stratégies, choix et rollback"],
            }
        ],
    }
    handler = object.__new__(DashboardHandler)
    handler.server = server
    values = [analysis(project), plan]
    values[0]["missing_information"] = ["Quelle fréquence de sauvegarde ?"]
    monkeypatch.setattr(
        project_ui,
        "openclaw_runner",
        lambda *_args, **_kwargs: lambda *_call: {"text": json.dumps(values.pop(0))},
    )
    handler._prepare(project, "analysis")
    data = request(server, "/api/project?project=" + identifier)[1]
    assert data["draft"]["approved"] is False
    assert current_status(project) == "INTAKE_READY"
    proposal = data["draft"]["proposal"]
    assert (
        request(server, "/api/approve", {**base, "kind": "analysis", "proposal": proposal})[0] == 400
    )
    assert (
        request(
            server,
            "/api/approve",
            {**base, "kind": "analysis", "proposal": proposal, "human_approved": True},
        )[0]
        == 202
    )
    assert current_status(project) == "CLARIFICATION_REQUIRED"
    assert (
        request(server, "/api/clarify", {**base, "id": "clarification-001", "answer": "Chaque nuit"})[
            0
        ]
        == 202
    )
    assert current_status(project) == "ANALYZED"
    handler._prepare(project, "plan")
    assert (
        request(
            server, "/api/approve", {**base, "kind": "plan", "proposal": plan, "human_approved": True}
        )[0]
        == 202
    )
    assert current_status(project) == "ASSIGNED"
    worker_done = threading.Event()

    def work(*_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        try:
            return run_project_tasks(
                ROOT,
                server.runtime,
                project,
                runner=lambda *_call: {
                    "files": {
                        expected: "Deux stratégies: copie simple ou snapshot. Choix: snapshot. "
                        "Vérifier restauration. Rollback: restaurer la précédente version."
                    },
                    "summary": "Choix documenté",
                },
            )
        finally:
            worker_done.set()

    monkeypatch.setattr(dashboard, "run_project_tasks", work)
    assert request(server, "/api/resume", base)[0] == 202
    assert worker_done.wait(timeout=5)
    assert current_status(project) == "VALIDATING"
    assert (project / expected).is_file()
    assert request(server, "/api/artifact?project=" + identifier + "&path=" + expected)[0] == 200
    assert (
        request(
            server, "/api/artifact?project=" + identifier + "&path=../../state/webui/bridge.token"
        )[0]
        == 400
    )

    def audited(_repo: Path, _runtime: Path, _project: Path, kind: str) -> Path:
        def reviewer(_role: str, prompt: str, _session: str) -> dict[str, Any]:
            criteria = json.loads(prompt.split("\n", 1)[1])
            return {
                "verdict": "PASS",
                "findings": [],
                "criteria": {
                    task: [
                        {
                            "passed": True,
                            "evidence": "Deux options, choix et rollback présents dans l’ADR simulé",
                        }
                        for _ in requirements
                    ]
                    for task, requirements in criteria.items()
                },
            }

        return review_project(ROOT, server.runtime, project, kind, runner=reviewer)

    monkeypatch.setattr(dashboard, "review_project", audited)
    handler._prepare(project, "validation")
    assert current_status(project) == "REVIEW"
    handler._prepare(project, "review")
    assert current_status(project) == "PACKAGING"
    assert request(server, "/api/complete", base)[0] == 400
    assert request(server, "/api/complete", {**base, "human_approved": True})[0] == 202
    assert current_status(project) == "COMPLETE"
    assert read_json(project / "evidence/final_report.json")["status"] == "PACKAGING"


@pytest.mark.parametrize(
    "files",
    [
        [{"name": "secret.env", "content": "eA=="}],
        [{"name": "bad.pdf", "content": "invalid-base64"}],
        [{"name": "x.txt", "content": "eA=="}] * 4,
    ],
)
def test_uploads_reject_unsupported_or_unbounded_inputs(
    server: DashboardServer, files: list[Any]
) -> None:
    before = list((server.runtime / "projects").iterdir())
    assert request(server, "/api/create", {"title": "x", "brief": "x", "files": files})[0] == 400
    assert list((server.runtime / "projects").iterdir()) == before


def test_draft_failure_does_not_promote_state_or_inputs(server: DashboardServer) -> None:
    _, created = request(server, "/api/create", {"title": "x", "brief": "x"})
    project = server.runtime / "projects" / created["project_id"]
    original = (project / "intake/demande.md").read_text()

    def mutate(*_args: Any) -> dict[str, Any]:
        (project / "intake/demande.md").chmod(0o600)
        (project / "intake/demande.md").write_text("injected")
        return {"text": json.dumps(analysis(project))}

    with pytest.raises(ValueError, match="Guard"):
        project_ui.propose(ROOT, server.runtime, project, "analysis", runner=mutate)
    assert current_status(project) == "INTAKE_READY"
    assert not (project / "context/ui_draft.json").exists()
    (project / "intake/demande.md").write_text(original)
    with worker_lock(server.runtime), pytest.raises(ValueError, match="déjà actif"):
        project_ui.propose(ROOT, server.runtime, project, "analysis", runner=lambda *_args: {})
