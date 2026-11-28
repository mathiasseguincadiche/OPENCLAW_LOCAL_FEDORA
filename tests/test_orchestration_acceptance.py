"""Exercise C03 and C04 on one Atlas mission with deterministic model doubles."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from clawfedora import (
    atelier_chat,
    chat_projects,
    chat_proposals,
    github_refresh,
    milestone_evidence,
    project_engine,
    project_resume,
    project_roadmap,
    project_ui,
    source_connectors,
)
from clawfedora.agents import deploy_workspaces
from clawfedora.knowledge import build_index
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
REPOSITORY = "example/atlas"
INITIAL_COMMIT = "a" * 40
UPDATED_COMMIT = "b" * 40
MILESTONE = "restauration"
DECISION = "Modèle de restauration retenu"
QUESTION = "Quel délai de restauration confirmer ?"
PRIVATE_THREAD_MARKER = "Hypothèse privée du premier fil"
FOREIGN_PROJECT = "Autre dossier isolé"
INITIAL_TEXT = "Protocole de restauration Atlas initial. Fenêtre du matin."
UPDATED_TEXT = "Protocole de restauration Atlas révisé. Fenêtre du soir."


def _output(task: str) -> str:
    return f"deliverables/{task}/report.md"


def _task(task_id: str, role: str, reason: str, dependencies: list[str]) -> dict[str, Any]:
    return {
        "id": task_id, "role": role, "role_reason": reason, "title": task_id,
        "objective": "Documenter le mécanisme et ses limites", "depends_on": dependencies,
        "expected_outputs": [_output(task_id)], "acceptance_criteria": ["Justification vérifiable"],
    }


def _plan(runtime: Path, prepare_sources: Callable[[Path], None]) -> Path:
    deploy_workspaces(ROOT, runtime)
    project = project_ui.create_from_browser(ROOT, runtime, {
        "title": "Atlas — reprise des sauvegardes",
        "brief": "Comparer deux options de sauvegarde et expliquer la restauration.",
        "learning_mode": "direct",
    })
    prepare_sources(project)
    analysis: dict[str, Any] = {key: [] for key in project_engine.ANALYSIS_FIELDS}
    analysis["summary"] = "Comparer et documenter deux options de sauvegarde."
    analysis["objectives"] = ["Comparer les options de restauration"]
    analysis["ambiguities"] = [{"question": QUESTION, "blocking": False}]
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


def _atlas_sources(
    runtime: Path, monkeypatch: pytest.MonkeyPatch,
) -> Callable[[Path], None]:
    def local_snapshot(dest: Path, repo: str, commit: str) -> dict[str, Any]:
        assert repo == REPOSITORY and commit in {INITIAL_COMMIT, UPDATED_COMMIT}
        content = INITIAL_TEXT if commit == INITIAL_COMMIT else UPDATED_TEXT
        (dest / "protocole.md").write_text(content, encoding="utf-8")
        return {"provider": "github", "repository": repo, "commit": commit,
                "file_count": 1, "skipped": 0}

    def prepare(project: Path) -> None:
        source_connectors.import_snapshot(
            ROOT, runtime, project.name, github=REPOSITORY, commit=INITIAL_COMMIT,
        )
        build_index(ROOT, project)

    monkeypatch.setattr(source_connectors, "_github_snapshot", local_snapshot)
    return prepare


def _record_continuity_inputs(runtime: Path, project: Path) -> dict[str, Any]:
    project_roadmap.initialize(project, {"milestones": [
        {"id": MILESTONE, "title": "Restaurer la sauvegarde", "depends_on": []},
    ]}, apply=True)
    proposal = chat_proposals.save(
        runtime, project, "Consigner le choix de restauration pour la prochaine revue.",
        DECISION, "local", "atlas-synthetique",
    )
    chat_proposals.accept(runtime, project, proposal["number"], proposal["sha256"])
    args = {
        "milestone_id": MILESTONE, "repository": REPOSITORY, "commit": INITIAL_COMMIT,
        "environment": "atlas-local", "kind": "simulation", "procedure": "Lire le protocole",
        "expected": "Une fenêtre de restauration", "observed": "Fenêtre du matin",
    }
    preview = milestone_evidence.capture(runtime, project.name, **args)
    return milestone_evidence.capture(
        runtime, project.name, **args, apply=True, approve=preview["approval_sha256"],
    )


def _resume(runtime: Path, project: Path, role: str) -> tuple[dict[str, Any], str]:
    before = _project_hashes(project)
    thread = atelier_chat.create(runtime, project.name, role)
    assert thread["messages"] == []
    complete = atelier_chat.send(ROOT, runtime, thread["id"], "!continuer")
    report = project_resume.overview(runtime, project, repo_root=ROOT, check_evidence=True)
    assert _project_hashes(project) == before
    return report, str(complete["messages"][-1]["content"])


def _project_hashes(project: Path) -> dict[str, str]:
    return {path.relative_to(project).as_posix(): sha256_file(path)
            for path in project.rglob("*") if path.is_file()}


def _check_source_update(
    runtime: Path, project: Path, receipt: dict[str, Any],
) -> dict[str, Any]:
    question = "Quel protocole de restauration ?"
    initial = chat_projects.project_context(ROOT, runtime, project, question,
                                            include_revisions=True)
    assert INITIAL_TEXT in initial and UPDATED_TEXT not in initial
    preview = github_refresh.refresh(runtime, project.name, REPOSITORY, UPDATED_COMMIT)
    github_refresh.refresh(
        runtime, project.name, REPOSITORY, UPDATED_COMMIT,
        apply=True, approve=preview["approve_sha256"],
    )
    before = _project_hashes(project)
    context = chat_projects.project_context(ROOT, runtime, project, question,
                                            include_revisions=True)
    passages = json.loads(context.split("\n", 1)[1])["passages"]
    cited, = [row for row in passages if row["kind"] == "github-approved-revision"]
    assert cited["commit"] == UPDATED_COMMIT and UPDATED_TEXT in cited["text"]
    assert INITIAL_TEXT not in context
    assert cited["representation_sha256"] == sha256_file(project / cited["representation_path"])
    assert _project_hashes(project) == before

    updated, reply = _resume(runtime, project, "expert-recherche")
    evidence = updated["milestone_evidence"]
    ref, = evidence["references"]
    assert evidence["to_requalify"] == 1 and "REQUALIFY" in reply
    assert ref["commit"] == INITIAL_COMMIT and ref["source"] == receipt["record_path"]
    assert ref["verification"] == "REQUALIFY"
    assert ref["record_sha256"] == read_json(project / receipt["record_path"])["record_sha256"]
    return {"approved_commit": UPDATED_COMMIT, "initial_receipt_sha256": ref["record_sha256"],
            "receipt_state": ref["verification"]}


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
) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
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
    report, reply = _resume(runtime, project, "chef-operations")
    mission = report["mission"]
    assert mission["next_action"] == "PUBLICATION_PENDING"
    assert mission["pending_publication"] == {"task_id": DESIGN, "attempt": 1}
    assert "Publication à terminer" in reply and QUESTION in reply and DECISION in reply
    bundle = project / "context/exchange/design/self/run-001/manifest.json"
    original_bundle = sha256_file(bundle)
    resumed = run_project_tasks(ROOT, runtime, project, runner=exercise.produce, resume=True)
    assert resumed[0]["task_id"] == DESIGN and resumed[0]["attempt"] == 1
    assert exercise.calls.count(DESIGN) == 1 and sha256_file(bundle) == original_bundle
    assert not (project / project_engine.TASK_PROMOTION_PATH).exists()
    assert len(read_json(history)["results"]) == 3
    return resumed, original_bundle, mission["pending_publication"]


def test_atlas_orchestration_acceptance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = tmp_path / "runtime"
    project = _plan(runtime, _atlas_sources(runtime, monkeypatch))
    receipt = _record_continuity_inputs(runtime, project)

    def no_model(*_args: Any) -> str:
        pytest.fail("Les reprises Atlas doivent rester en lecture seule sans modèle")

    monkeypatch.setattr(atelier_chat, "_policy_answer", no_model)
    prior = atelier_chat.create(runtime, project.name, "architecte-solutions")
    atelier_chat.send(ROOT, runtime, prior["id"], "!continuer " + PRIVATE_THREAD_MARKER)
    foreign = project_ui.create_from_browser(ROOT, runtime, {
        "title": FOREIGN_PROJECT, "brief": "Dossier étranger à la mission Atlas.",
    })
    foreign_before = _project_hashes(foreign)
    exercise = Exercise(runtime, project)
    first_results, original_bundle, pending = _interrupt_publication(exercise, monkeypatch)
    assert {row["task_id"] for row in first_results} == {DESIGN, CHECK, GLOSSARY}
    assert exercise.handoff_attempts == [1]
    plan_hash = sha256_file(project / "context/project_plan.json")
    glossary_hash = sha256_file(project / _output(GLOSSARY))
    continued, same_project = _resume(runtime, project, "redacteur-pedagogique")
    other_report, other_project = _resume(runtime, foreign, "redacteur-pedagogique")
    assert continued["mission"]["next_action"] == "VALIDATING"
    assert continued["mission"]["counts"] == {"COLLECTED": 3}
    assert DECISION in same_project and QUESTION in same_project
    assert PRIVATE_THREAD_MARKER not in same_project and FOREIGN_PROJECT not in same_project
    assert DECISION not in other_project and QUESTION not in other_project
    assert other_report["project_id"] == foreign.name
    assert other_report["accepted_decisions"]["items"] == []
    assert continued["clarifications_pending"]["items"][0]["status"] == "TO_CONFIRM"
    note, = continued["accepted_decisions"]["items"]
    assert note["note_sha256"] == sha256_file(project / note["note_path"])
    source_update = _check_source_update(runtime, project, receipt)
    assert sha256_file(project / "context/project_plan.json") == plan_hash

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
    revised, revision_text = _resume(runtime, project, "architecte-solutions")
    assert revised["mission"]["project_revision"] == 1 and "Révision 1" in revision_text
    assert revised["mission"]["next_action"] == "READY"
    assert revised["audit_references"] == []
    assert not (project / _output(DESIGN)).exists()

    blocked, = run_project_tasks(ROOT, runtime, project, runner=exercise.produce)
    assert exercise.checked_correction and blocked["failure_code"] == "no_progress"
    assert blocked["attempt"] == 2 and not (project / _output(DESIGN)).exists()
    assert run_project_tasks(ROOT, runtime, project, runner=exercise.produce, resume=True) == []
    assert exercise.calls.count(DESIGN) == 2
    assert not (project / _output(CHECK)).exists()
    stalled, stalled_text = _resume(runtime, project, "chef-operations")
    assert stalled["mission"]["next_action"] == "BLOCKED"
    assert stalled["mission"]["counts"]["STOPPED_NO_PROGRESS"] == 1
    assert "correction inchangée" in stalled_text

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
    final, done_text = _resume(runtime, project, "auditeur-qualite")
    assert final["mission"]["next_action"] == "COMPLETE" and "Révision 2" in done_text
    assert [row["status"] for row in final["audit_references"]] == ["CURRENT", "CURRENT"]
    assert [row["source_sha256"] for row in final["audit_references"]] == [
        sha256_file(validation), sha256_file(review),
    ]
    assert final["milestone_evidence"]["to_requalify"] == 1
    assert _project_hashes(foreign) == foreign_before

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

    continuity = {
        "publication_pending": pending,
        "fresh_thread_isolation": {"project_state": continued["mission"]["next_action"]},
        "recorded_decision_and_open_question": {
            "note_sha256": note["note_sha256"],
            "register_sha256": continued["clarifications_pending"]["source_sha256"],
        },
        "source_refresh": source_update,
        "approved_correction": {"revision": revised["mission"]["project_revision"],
                                "blocked_attempt": blocked["attempt"]},
        "final_reaudit": {"revision": final["mission"]["project_revision"],
                          "review_sha256": sha256_file(review)},
    }
    continuation_report = {
        **report,
        "assessment": "C04_SYNTHETIC_ACCEPTANCE_PASSED",
        "cases": [
            {"id": key, "status": "CONFORME", **value} for key, value in continuity.items()
        ],
    }
    if output := os.environ.get("CLAWFEDORA_CONTINUITY_ACCEPTANCE_EVIDENCE"):
        payload = {**continuation_report, "report_sha256": _digest(continuation_report)}
        Path(output).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
