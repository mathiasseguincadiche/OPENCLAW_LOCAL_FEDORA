"""Exercise C03 in one local project with real state and deterministic model doubles."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import pytest

from clawfedora import project_engine, project_ui
from clawfedora.agents import deploy_workspaces
from clawfedora.notion_write import _digest
from clawfedora.project_common import read_json, sha256_file
from clawfedora.project_control import progress
from clawfedora.project_proofs import collect_operator_proof, receipt_path
from clawfedora.project_revision import audit_corrections, revise
from clawfedora.project_worker import review_project, run_project_tasks

ROOT = Path(__file__).resolve().parents[1]
DESIGN = "design"
CHECK = "cross-check"
GLOSSARY = "glossary"
REMOVED = "optional-check"
OLD = "# Option retenue\n\nPrendre un instantané.\n"
NEW = OLD + "\nCe choix réduit le temps de restauration par rapport à une copie complète.\n"


def _output(task: str) -> str:
    return f"deliverables/{task}/report.md"


def _task(task_id: str, role: str, reason: str, dependencies: list[str]) -> dict[str, Any]:
    return {
        "id": task_id, "role": role, "role_reason": reason, "title": task_id,
        "objective": "Documenter le mécanisme et ses limites", "depends_on": dependencies,
        "expected_outputs": [_output(task_id)], "acceptance_criteria": ["Justification vérifiable"],
    }


def _plan(runtime: Path) -> Path:
    deploy_workspaces(ROOT, runtime)
    project = project_ui.create_from_browser(ROOT, runtime, {
        "title": "Atlas — reprise des sauvegardes",
        "brief": "Comparer deux options de sauvegarde et expliquer la restauration.",
        "learning_mode": "direct",
    })
    analysis: dict[str, Any] = {key: [] for key in project_engine.ANALYSIS_FIELDS}
    analysis["summary"] = "Comparer et documenter deux options de sauvegarde."
    documents = read_json(project / "context/ingestion/index.json")["documents"]
    analysis["source_coverage"] = [
        {"document_id": row["document_id"], "status": "READ", "method": row["method"]}
        for row in documents
    ]
    project_ui.approve(ROOT, runtime, project, "analysis", analysis)
    glossary = _task(GLOSSARY, "redacteur-pedagogique", "Expliquer le vocabulaire.", [])
    glossary.update(writing_scope="intermediate", acceptance_criteria=[
        f"[preuve observation atlas-local {_output(GLOSSARY)}] Le glossaire couvre les deux termes",
    ])
    proposed = {"workstreams": ["Restauration"], "tasks": [
        _task(DESIGN, "architecte-solutions", "Comparer les mécanismes de restauration.", []),
        _task(CHECK, "expert-recherche", "Relire le choix et ses limites.", [DESIGN]),
        glossary,
        _task(REMOVED, "ingenieur-securite", "Proposer un contrôle supplémentaire.", []),
    ]}

    def chief(role: str, prompt: str, _session: str) -> dict[str, str]:
        assert role == "chef-operations" and "role_reason" in prompt
        return {"text": json.dumps(proposed)}

    draft = project_ui.propose(ROOT, runtime, project, "plan", runner=chief)
    assert project_engine.current_status(project) == "ANALYZED" and not draft["approved"]
    approved = {**draft["proposal"], "tasks": draft["proposal"]["tasks"][:-1]}
    project_ui.approve(ROOT, runtime, project, "plan", approved)
    return project


class Exercise:
    def __init__(self, runtime: Path, project: Path) -> None:
        self.runtime = runtime
        self.project = project
        self.design = OLD
        self.calls: list[str] = []
        self.audit_sessions: list[str] = []
        self.producer_sessions: set[str] = set()
        self.handoff_attempts: list[int] = []
        self.checked_correction = False

    def produce(self, role: str, prompt: str, session: str) -> dict[str, Any]:
        task = json.loads(prompt.split("\n", 1)[1])
        task_id = task["id"]
        assert role == task["role"] and session not in self.producer_sessions
        self.calls.append(task_id)
        self.producer_sessions.add(session)
        root = self.runtime / "workspaces" / role / "projects" / self.project.name
        context = root / task_id / session / "context"
        assert task_id != REMOVED and task["role_reason"]
        if (context / "audit-correction.json").is_file():
            assert task_id == DESIGN
            correction = read_json(context / "audit-correction.json")
            assert correction["audit"]["session_id"] == self.audit_sessions[-1]
            assert correction["findings"][0]["number"] == 1
            previous = context / "previous-outputs" / _output(DESIGN)
            assert previous.read_text(encoding="utf-8") == OLD
            assert previous.stat().st_mode & 0o222 == 0
            self.checked_correction = True
        if task_id == CHECK:
            record = read_json(context / "dependency-inputs.json")
            upstream, = record["inputs"]
            assert upstream["producer_task_id"] == DESIGN and upstream["relationship"] == "direct"
            manifest = context.parent / upstream["manifest"]
            assert sha256_file(manifest) == upstream["manifest_sha256"]
            upstream_file = manifest.parent / "artifacts" / _output(DESIGN)
            assert upstream_file.read_text(encoding="utf-8") == self.design
            self.handoff_attempts.append(upstream["attempt"])
        content = {
            DESIGN: self.design, CHECK: "# Vérification\n\nLe choix est rattaché au dossier.\n",
            GLOSSARY: "# Glossaire\n\nInstantané et restauration.\n",
        }[task_id]
        return {"files": {_output(task_id): content}, "summary": "Contribution collectée"}

    def audit(self, role: str, _prompt: str, session: str) -> dict[str, Any]:
        assert role == "auditeur-qualite"
        assert session not in self.audit_sessions and session not in self.producer_sessions
        self.audit_sessions.append(session)
        root = self.runtime / "workspaces/auditeur-qualite/projects/reviews" / session
        path = root / _output(DESIGN)
        assert path.stat().st_mode & 0o222 == 0
        assert not (root / "history").exists() and not (root / "evidence/task_results.json").exists()
        passed = path.read_text(encoding="utf-8") == NEW
        return {
            "verdict": "PASS" if passed else "FAIL", "findings": [],
            "criteria": {
                DESIGN: [{
                    "passed": passed, "evidence": "Comparaison vérifiée." if passed else
                    "La comparaison avec la copie complète manque.",
                    "reference": _output(DESIGN),
                }],
                CHECK: [{"passed": True, "evidence": "Contribution présente.",
                         "reference": _output(CHECK)}],
                GLOSSARY: [{"passed": True, "evidence": "Observation Atlas liée au fichier.",
                            "reference": receipt_path(GLOSSARY, 1)}],
            },
        }


def _interrupt_publication(
    exercise: Exercise, monkeypatch: pytest.MonkeyPatch,
) -> tuple[list[dict[str, Any]], str]:
    runtime, project = exercise.runtime, exercise.project
    history = project / "evidence/task_results.json"
    original = project_engine.write_json

    def interrupt(path: Path, value: dict[str, Any]) -> None:
        original(path, value)
        if path == history:
            raise KeyboardInterrupt

    with monkeypatch.context() as injection:
        injection.setattr(project_engine, "write_json", interrupt)
        with pytest.raises(KeyboardInterrupt):
            run_project_tasks(ROOT, runtime, project, runner=exercise.produce)
    assert progress(runtime)["phase"] == "interrupted"
    bundle = project / "context/exchange/design/self/run-001/manifest.json"
    original_bundle = sha256_file(bundle)
    resumed = run_project_tasks(ROOT, runtime, project, runner=exercise.produce, resume=True)
    assert resumed[0]["task_id"] == DESIGN and resumed[0]["attempt"] == 1
    assert exercise.calls.count(DESIGN) == 1 and sha256_file(bundle) == original_bundle
    assert not (project / project_engine.TASK_PROMOTION_PATH).exists()
    assert len(read_json(history)["results"]) == 3
    return resumed, original_bundle


def test_atlas_orchestration_acceptance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = tmp_path / "runtime"
    project = _plan(runtime)
    exercise = Exercise(runtime, project)
    first_results, original_bundle = _interrupt_publication(exercise, monkeypatch)
    assert {row["task_id"] for row in first_results} == {DESIGN, CHECK, GLOSSARY}
    assert exercise.handoff_attempts == [1]
    plan_hash = sha256_file(project / "context/project_plan.json")
    glossary_hash = sha256_file(project / _output(GLOSSARY))

    with pytest.raises(ValueError, match="preuves"):
        review_project(ROOT, runtime, project, "validation", runner=exercise.audit)
    assert exercise.audit_sessions == []
    proof = collect_operator_proof(
        project, GLOSSARY, 1, apply=True, outcome="PASS",
        observation="Dans la fixture Atlas, le glossaire contient Instantané et restauration.",
    )
    assert proof["binding"]["targets"] == {_output(GLOSSARY): glossary_hash}
    failed = review_project(ROOT, runtime, project, "validation", runner=exercise.audit)
    assert read_json(failed)["verdict"] == "FAIL"
    candidate = audit_corrections(project)
    assert candidate is not None and candidate["sha256"] == sha256_file(failed)
    assert [task["task_id"] for task in candidate["tasks"]] == [DESIGN]
    with pytest.raises(PermissionError):
        revise(project, DESIGN, "Justifier le choix", audit_sha256=candidate["sha256"])
    targeted = revise(
        project, DESIGN, "Ajouter la comparaison avec la copie complète.", human_approved=True,
        audit_sha256=candidate["sha256"],
    )
    assert targeted["affected_tasks"] == [DESIGN, CHECK]

    blocked, = run_project_tasks(ROOT, runtime, project, runner=exercise.produce)
    assert exercise.checked_correction and blocked["failure_code"] == "no_progress"
    assert blocked["attempt"] == 2 and not (project / _output(DESIGN)).exists()
    assert run_project_tasks(ROOT, runtime, project, runner=exercise.produce, resume=True) == []
    assert exercise.calls.count(DESIGN) == 2
    assert not (project / _output(CHECK)).exists()

    revise(project, DESIGN, "Expliquer le délai de restauration.", human_approved=True)
    exercise.design = NEW
    corrected = run_project_tasks(ROOT, runtime, project, runner=exercise.produce)
    assert [(row["task_id"], row["attempt"]) for row in corrected] == [(DESIGN, 3), (CHECK, 2)]
    assert exercise.handoff_attempts == [1, 3] and exercise.calls.count(GLOSSARY) == 1
    assert sha256_file(project / _output(GLOSSARY)) == glossary_hash
    validation = review_project(ROOT, runtime, project, "validation", runner=exercise.audit)
    assert read_json(validation)["verdict"] == "PASS"
    project_engine.transition_project(
        ROOT, project, "REVIEW", actor="auditeur-qualite", reason="atlas_validation",
    )
    review = review_project(ROOT, runtime, project, "review", runner=exercise.audit)
    assert read_json(review)["verdict"] == "PASS" and len(exercise.audit_sessions) == 3
    project_ui.complete(ROOT, runtime, project)
    assert project_engine.current_status(project) == "COMPLETE"

    commit = os.environ.get("GITHUB_SHA")
    assert commit is None or re.fullmatch(r"[a-f0-9]{40}", commit)
    assertions = {
        "role_selection": {"tasks": len(first_results), "plan_sha256": plan_hash},
        "interrupted_publication": {"attempt": 1, "bundle_sha256": original_bundle},
        "handoff_provenance": {"producer_attempts": exercise.handoff_attempts},
        "required_evidence": {"receipt_sha256": sha256_file(project / receipt_path(GLOSSARY, 1))},
        "targeted_correction": {"audit_sha256": targeted["audit"]["sha256"], "stopped_attempt": 2},
        "independent_reaudit": {"sessions": len(exercise.audit_sessions),
                               "report_sha256": sha256_file(review)},
    }
    report = {
        "schema": 1, "assessment": "C03_SYNTHETIC_ACCEPTANCE_PASSED", "campaign_verdict": "CONFORME",
        "tested_commit": commit, "synthetic": True, "real_model_calls": 0, "final_state": "COMPLETE",
        "cases": [{"id": key, "status": "CONFORME", **value} for key, value in assertions.items()],
    }
    if output := os.environ.get("CLAWFEDORA_ORCHESTRATION_ACCEPTANCE_EVIDENCE"):
        payload = {**report, "report_sha256": _digest(report)}
        Path(output).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
