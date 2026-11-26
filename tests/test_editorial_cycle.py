"""The real worker cycles a bounded Markdown draft through a separate auditor."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from test_daily_worker import ROOT
from test_daily_worker import planned as planned

from clawfedora import editorial_cycle as ec
from clawfedora.project_common import read_json
from clawfedora.project_engine import _validate_plan
from clawfedora.project_worker import run_project_tasks

OUTPUT = "deliverables/redaction/guide.md"
TASK = {
    "id": "redaction", "role": "redacteur-pedagogique",
    "title": "Guide", "objective": "Expliquer le mécanisme",
    "depends_on": [], "expected_outputs": [OUTPUT],
    "acceptance_criteria": ["[revue éditoriale] Expliquer le mécanisme et ses limites"],
}
INITIAL = "# Guide\n\nUn service traite une requête.\n"
REVISED = "# Guide\n\nUn service traite une requête et renvoie une réponse.\n"


def verdict(content: str, *, revise: bool = False) -> dict[str, Any]:
    return {"checks": {
        key: {"state": "REVISE" if revise and key == "writing" else "PASS",
              "quote": content.splitlines()[0], "reason": "Examen simulé",
              "action": "Préciser le mécanisme" if revise else "Conserver"}
        for key in ec.CRITERIA
    }}


def test_cycle_never_accepts_same_draft_or_unbounded_revisions():
    calls = []
    def audit(content, _structure):
        calls.append(content)
        return "session", verdict(content, revise=True)
    _, record = ec.run(INITIAL, audit, lambda content, *_: content)
    assert record["state"] == "NO_PROGRESS" and len(calls) == 1
    calls.clear()
    _, record = ec.run(INITIAL, audit, lambda content, *_: content + "\nDétail.")
    assert record["state"] == "REVISION_LIMIT" and len(calls) == 3


def test_cycle_requires_quote_and_structure():
    def wrong(content, _structure):
        answer = verdict(content)
        answer["checks"]["accuracy"]["quote"] = "Extrait absent"
        return "session", answer
    with pytest.raises(ValueError, match="extrait absent"):
        ec.run(INITIAL, wrong, lambda *_: REVISED)
    _, result = ec.run(
        INITIAL + '~~~bash\n', lambda content, _: ("session", verdict(content)),
        lambda *_: REVISED,
    )
    assert result["state"] == "MODEL_REVIEW_PASSED"
    assert result["rounds"][0]["structure_issues"]


@pytest.mark.parametrize("planned", [[TASK]], indirect=True)
def test_worker_revises_before_collecting(planned):
    runtime, project = planned
    calls = []
    sessions = set()

    def runner(role, prompt, session):
        assert session not in sessions
        sessions.add(session)
        calls.append(role)
        assert not (project / OUTPUT).exists()
        if role == "auditeur-qualite":
            payload = json.loads(prompt.split("\n", 1)[1])
            content = payload["document"]
            assert (runtime / "workspaces/auditeur-qualite/projects/editorial-reviews"
                    / session / "context/tasks/redaction.json").is_file()
            return verdict(content, revise=content == INITIAL)
        return {"files": {OUTPUT: INITIAL if len(calls) == 1 else REVISED},
                "summary": "Brouillon de test"}

    result = run_project_tasks(ROOT, runtime, project, runner=runner)
    assert calls == ["redacteur-pedagogique", "auditeur-qualite",
                     "redacteur-pedagogique", "auditeur-qualite"]
    assert result[0]["status"] == "PASS"
    assert (project / OUTPUT).read_text() == REVISED
    receipt = next((project / "evidence/redaction").glob("editorial-cycle-*.json"))
    record = read_json(receipt)
    assert record["candidate_sha256"] == hashlib.sha256(REVISED.encode()).hexdigest()
    assert record["qualification"] == "MODEL_REVIEW_ONLY_NOT_NATIVE_CERTIFIED"
    assert len(record["rounds"]) == 2
    assert read_json(project / "project.json")["status"] == "VALIDATING"
    assert not (project / "evidence/validation_report.json").exists()


@pytest.mark.parametrize("planned", [[TASK]], indirect=True)
def test_worker_does_not_collect_rejected_draft(planned):
    runtime, project = planned
    def runner(role, prompt, _session):
        if role == "auditeur-qualite":
            return verdict(INITIAL, revise=True)
        return {"files": {OUTPUT: INITIAL}, "summary": "Brouillon"}
    result = run_project_tasks(ROOT, runtime, project, runner=runner)
    assert result[0]["status"] == "FAIL"
    assert not (project / OUTPUT).exists()
    receipt = next((project / "evidence/redaction").glob("editorial-cycle-*.json"))
    assert read_json(receipt)["state"] == "NO_PROGRESS"


@pytest.mark.parametrize("override", [
    {"role": "ingenieur-devops"},
    {"learning_mode": "guided"},
    {"expected_outputs": [OUTPUT, "deliverables/redaction/guide.pdf"]},
    {"acceptance_criteria": [ec.MARKER + " Qualité", "[preuve ci] invalide"]},
])
def test_plan_limits_revision_to_approved_markdown(override):
    with pytest.raises(ValueError, match="revue éditoriale"):
        _validate_plan([{**TASK, **override}])
