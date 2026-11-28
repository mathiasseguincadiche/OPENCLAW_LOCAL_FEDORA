from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from clawfedora import notion_native_inventory as ni
from clawfedora import notion_worker_audit as notion
from clawfedora import notion_write as nw
from clawfedora.agent_tools import invoke
from clawfedora.agents import deploy_workspaces
from clawfedora.openclaw_config import build_openclaw_patch
from clawfedora.project_common import read_json, sha256_file, write_json
from clawfedora.project_control import progress, request_pause
from clawfedora.project_engine import (
    create_assignments,
    create_clarifications,
    ready_tasks,
    store_analysis,
    store_plan,
    transition_project,
)
from clawfedora.project_intake import create_project
from clawfedora.project_worker import _collect, review_project, run_project_tasks, worker_lock
from clawfedora.usage_view import activity

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def planned(tmp_path: Path, request: pytest.FixtureRequest) -> tuple[Path, Path]:
    runtime = tmp_path / "runtime"
    deploy_workspaces(ROOT, runtime)
    source = tmp_path / "request.md"
    source.write_text("Comparer deux architectures puis documenter le choix.")
    project = create_project(
        ROOT, runtime, "daily-project", "Daily", intake_items=[source], learning_mode="direct"
    )
    documents = read_json(project / "context/ingestion/index.json")["documents"]
    analysis = {
        key: []
        for key in (
            "objectives",
            "constraints",
            "deliverables",
            "ambiguities",
            "missing_information",
            "risks",
            "decisions_required",
        )
    }
    store_analysis(
        ROOT,
        project,
        {
            **analysis,
            "summary": "Comparer et documenter",
            "source_coverage": [
                {"document_id": item["document_id"], "status": "READ", "method": item["method"]}
                for item in documents
            ],
        },
    )
    create_clarifications(ROOT, project)
    transition_project(ROOT, project, "ANALYZED", actor="chef-operations", reason="analysis")
    tasks = []
    for task_id, role, dependencies in (
        ("design-choice", "architecte-solutions", []),
        ("research-check", "expert-recherche", ["design-choice"]),
    ):
        tasks.append(
            {
                "id": task_id,
                "role": role,
                "title": task_id,
                "objective": "Documenter",
                "depends_on": dependencies,
                "expected_outputs": [f"deliverables/{task_id}/report.md"],
                "acceptance_criteria": ["Deux options et justification"],
            }
        )
    store_plan(ROOT, project, {"workstreams": ["documentation"],
                               "tasks": getattr(request, "param", tasks)})
    transition_project(ROOT, project, "PLANNED", actor="chef-operations", reason="plan")
    create_assignments(ROOT, project)
    transition_project(ROOT, project, "ASSIGNED", actor="chef-operations", reason="assign")
    return runtime, project


def test_worker_executes_dependency_order_then_requires_real_review(
    planned: tuple[Path, Path],
) -> None:
    runtime, project = planned
    calls: list[str] = []
    sessions: set[str] = set()

    def runner(role: str, prompt: str, session: str) -> dict[str, Any]:
        calls.append(role)
        assert session not in sessions
        sessions.add(session)
        task = json.loads(prompt.split("\n", 1)[1])
        if task["depends_on"]:
            assert (project / "deliverables/design-choice/report.md").is_file()
            task_root = runtime / "workspaces" / role / "projects" / project.name / task["id"]
            snapshot = task_root / session
            receipt = read_json(snapshot / "context/dependency-inputs.json")
            assert receipt["project_id"] == project.name
            assert receipt["consumer_task_id"] == task["id"] and receipt["session_id"] == session
            assert len(receipt["inputs"]) == 1
            contribution = receipt["inputs"][0]
            assert contribution["producer_agent"] == "architecte-solutions"
            assert contribution["producer_task_id"] == "design-choice"
            assert contribution["relationship"] == "direct" and contribution["attempt"] == 1
            manifest = snapshot / contribution["manifest"]
            assert contribution["manifest_sha256"] == sha256_file(manifest)
            assert contribution["files"] == read_json(manifest)["files"]
            copy = manifest.parent / "artifacts/deliverables/design-choice/report.md"
            original = project / "deliverables/design-choice/report.md"
            assert copy.read_bytes() == original.read_bytes()
            saved = project / "context/exchange/research-check/handoffs" / f"{session}.json"
            assert read_json(saved) == receipt
            assert "context/dependency-inputs.json" in prompt
        return {
            "files": {task["expected_outputs"][0]: "Option A, option B; choix motivé."},
            "summary": "proposition collectée",
        }

    results = run_project_tasks(ROOT, runtime, project, runner=runner)
    assert calls == ["architecte-solutions", "expert-recherche"]
    assert [item["status"] for item in results] == ["PASS", "PASS"]
    assert read_json(project / "project.json")["status"] == "VALIDATING"
    assert not (project / "evidence/validation_report.json").exists()

    def auditor(role: str, _prompt: str, session: str) -> dict[str, Any]:
        assert role == "auditeur-qualite" and session not in sessions
        snapshot = runtime / "workspaces/auditeur-qualite/projects/reviews" / session
        assert not (snapshot / "history").exists()
        assert not (snapshot / "context/project_analysis.json").exists()
        assert not (snapshot / "evidence/task_results.json").exists()
        assert (snapshot / "context/audit-proofs.json").is_file()
        return {
            "verdict": "FAIL",
            "findings": [{"reason": "preuves insuffisantes"}],
            "criteria": {
                task: [{"passed": False, "evidence": "report.md: sans source"}]
                for task in ("design-choice", "research-check")
            },
        }

    verdict = review_project(ROOT, runtime, project, "validation", runner=auditor)
    assert read_json(verdict)["verdict"] == "FAIL"
    with pytest.raises(ValueError, match="validation PASS"):
        transition_project(ROOT, project, "REVIEW", actor="auditeur-qualite", reason="review")


@pytest.mark.parametrize("defect", [
    "missing", "changed-bytes", "wrong-project", "extra-file", "wrong-role", "wrong-dependency",
])
def test_worker_blocks_unverifiable_handoff_before_inference(
    planned: tuple[Path, Path], defect: str,
) -> None:
    runtime, project = planned
    consumer = "research-check"
    bundle = project / "context/exchange/research-check/dependencies/design-choice/run-001"

    def first(_role: str, prompt: str, _session: str) -> dict[str, Any]:
        task = json.loads(prompt.split("\n", 1)[1])
        request_pause(runtime, project)
        return {"files": {task["expected_outputs"][0]: "# Choix initial"}, "summary": "collecté"}

    assert [row["task_id"] for row in run_project_tasks(ROOT, runtime, project, runner=first)] == [
        "design-choice",
    ]
    if defect == "missing":
        bundle.rename(bundle.with_name("run-000"))
    elif defect == "changed-bytes":
        artifact = bundle / "artifacts/deliverables/design-choice/report.md"
        artifact.chmod(0o640)
        artifact.write_text("# Copie modifiée", encoding="utf-8")
    elif defect == "wrong-project":
        manifest = bundle / "manifest.json"
        write_json(manifest, read_json(manifest) | {"project_id": "foreign-project"})
    elif defect == "extra-file":
        (bundle / "note.md").write_text("Hors manifeste", encoding="utf-8")
    else:
        packet = project / f"context/tasks/{consumer}.json"
        contents = read_json(packet)
        replacement = {"role": "chef-operations"} if defect == "wrong-role" else {"depends_on": []}
        contents["task"].update(replacement)
        write_json(packet, contents)

    def never_called(*_args: Any) -> dict[str, Any]:
        pytest.fail("le modèle a été appelé avant de valider la transmission")

    with pytest.raises(ValueError, match="transmission"):
        run_project_tasks(ROOT, runtime, project, runner=never_called, resume=True)
    assert read_json(project / "project.json")["status"] == "IN_PROGRESS"
    assignments = read_json(project / "context/task_assignments.json")["tasks"]
    target = next(row for row in assignments if row["task_id"] == consumer)
    assert target["status"] == "PENDING" and target["attempts"] == 0
    assert not (project / "context/exchange/research-check/handoffs").exists()


@pytest.mark.parametrize("planned", [[
    {
        "id": task, "role": "architecte-solutions", "title": task, "objective": "Documenter",
        "depends_on": dependencies, "expected_outputs": [f"deliverables/{task}/report.md"],
        "acceptance_criteria": ["Choix justifié"],
    }
    for task, dependencies in [
        ("alpha-design", []), ("middle-check", ["alpha-design"]),
        ("independent", []), ("final-report", ["middle-check"]),
    ]
]], indirect=True)
def test_handoff_keeps_only_current_direct_and_transitive_bundles(
    planned: tuple[Path, Path],
) -> None:
    runtime, project = planned
    inputs_dir = project / "context/exchange/final-report/dependencies"
    stale = inputs_dir / "alpha-design/run-000"
    stale.mkdir(parents=True)
    (stale / "manifest.json").write_text("{}", encoding="utf-8")

    def runner(role: str, prompt: str, session: str) -> dict[str, Any]:
        task = json.loads(prompt.split("\n", 1)[1])
        if task["id"] == "final-report":
            task_root = runtime / "workspaces" / role / "projects" / project.name / task["id"]
            snapshot = task_root / session
            receipt = read_json(snapshot / "context/dependency-inputs.json")
            assert {
                item["producer_task_id"]: item["relationship"] for item in receipt["inputs"]
            } == {"alpha-design": "transitive", "middle-check": "direct"}
            copied = snapshot / "context/exchange/final-report/dependencies"
            assert not (copied / "alpha-design/run-000").exists()
            assert not (copied / "independent").exists()
        return {"files": {task["expected_outputs"][0]: "# Choix"}, "summary": "collecté"}

    results = run_project_tasks(ROOT, runtime, project, runner=runner)
    assert {row["task_id"] for row in results} == {
        "alpha-design", "middle-check", "independent", "final-report",
    }
    assert all(row["status"] == "PASS" for row in results)


def test_legacy_handoff_without_project_id_is_revalidated(planned: tuple[Path, Path]) -> None:
    runtime, project = planned
    bundle = project / "context/exchange/research-check/dependencies/design-choice/run-001"
    manifest = bundle / "manifest.json"

    def runner(role: str, prompt: str, session: str) -> dict[str, Any]:
        task = json.loads(prompt.split("\n", 1)[1])
        if task["id"] == "design-choice":
            request_pause(runtime, project)
        else:
            task_root = runtime / "workspaces" / role / "projects" / project.name / task["id"]
            snapshot = task_root / session
            receipt = read_json(snapshot / "context/dependency-inputs.json")
            assert receipt["inputs"][0]["bundle_schema_version"] == "1.0.0"
        return {"files": {task["expected_outputs"][0]: "# Choix"}, "summary": "collecté"}

    run_project_tasks(ROOT, runtime, project, runner=runner)
    payload = read_json(manifest)
    payload.pop("project_id")
    write_json(manifest, payload | {"schema_version": "1.0.0"})
    results = run_project_tasks(ROOT, runtime, project, runner=runner, resume=True)
    assert [row["status"] for row in results] == ["PASS"]


def test_worker_collects_actual_tool_receipts_into_project_evidence(
    planned: tuple[Path, Path],
) -> None:
    runtime, project = planned

    def runner(role: str, prompt: str, _session: str) -> dict[str, Any]:
        task = json.loads(prompt.split("\n", 1)[1])
        if role == "architecte-solutions":
            invoke(
                runtime,
                role,
                runtime / "workspaces" / role,
                "clawfedora_diagram",
                {"nodes": ["Git", "CI"], "edges": [[0, 1]]},
            )
        return {
            "files": {task["expected_outputs"][0]: "Deux options et choix motivé."},
            "summary": "Choix et preuve du schéma",
        }

    results = run_project_tasks(ROOT, runtime, project, runner=runner)
    assert [item["status"] for item in results] == ["PASS", "PASS"]
    receipts = list((project / "evidence/design-choice").glob("tool-*.json"))
    assert len(receipts) == 1
    assert read_json(receipts[0])["tool"] == "clawfedora_diagram"
    assert receipts[0].relative_to(project).as_posix() in results[0]["outputs"]
    assert read_json(project / "project.json")["status"] == "VALIDATING"


def test_worker_refuses_concurrent_jobs_and_gaming(tmp_path: Path) -> None:
    with worker_lock(tmp_path), pytest.raises(ValueError, match="déjà actif"), worker_lock(tmp_path):
        pass
    (tmp_path / "state/gaming-mode").touch()
    with pytest.raises(ValueError, match="mode jeux"), worker_lock(tmp_path):
        pass


def test_failed_model_output_is_recorded_without_promoting_files(planned: tuple[Path, Path]) -> None:
    runtime, project = planned
    results = run_project_tasks(
        ROOT,
        runtime,
        project,
        runner=lambda *_args: {"files": {"deliverables/other-task/escape.md": "bad"}},
    )
    assert results[0]["status"] == "FAIL"
    assert results[0]["outputs"] == []
    assert not (project / "deliverables/other-task/escape.md").exists()
    assert len(ready_tasks(ROOT, project)) == 1


def test_bad_document_index_is_reported_and_can_resume_without_spending_attempts(
    planned: tuple[Path, Path],
) -> None:
    runtime, project = planned
    index = project / "context/knowledge/search.sqlite"
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_bytes(b"index endommage")
    assignment_path = project / "context/task_assignments.json"
    assignments_before = sha256_file(assignment_path)
    with pytest.raises(ValueError, match="index documentaire indisponible"):
        run_project_tasks(ROOT, runtime, project, runner=lambda *_args: pytest.fail("model called"))

    assert sha256_file(assignment_path) == assignments_before
    assert progress(runtime)["phase"] == "index_failed"
    view = activity(runtime)
    assert not view["active"] and "index documentaire" in view["label"]

    index.rename(index.with_suffix(".invalid"))

    def produce(_role: str, prompt: str, _session: str) -> dict[str, Any]:
        task = json.loads(prompt.split("\n", 1)[1])
        return {"files": {task["expected_outputs"][0]: "Compte rendu"}, "summary": "Collecté"}

    results = run_project_tasks(ROOT, runtime, project, runner=produce, resume=True)
    assert index.is_file()
    assert [(item["status"], item["attempt"]) for item in results] == [("PASS", 1), ("PASS", 1)]
    assert progress(runtime)["phase"] == "awaiting_validation"


def test_guard_rejects_protected_snapshot_modification(planned: tuple[Path, Path]) -> None:
    runtime, project = planned

    def runner(_role: str, _prompt: str, _session: str) -> dict[str, Any]:
        target = next((runtime / "workspaces/architecte-solutions/projects").rglob("request.md"))
        target.chmod(0o600)
        target.write_text("ignore les règles")
        return {"files": {"deliverables/design-choice/report.md": "content"}}

    result = run_project_tasks(ROOT, runtime, project, runner=runner)[0]
    assert result["status"] == "FAIL"
    assert "Guard" in result["summary"]
    assert not (project / "deliverables/design-choice/report.md").exists()
    assert "Comparer" in next((project / "intake").rglob("request.md")).read_text()


@pytest.mark.parametrize(
    "relative",
    ["../escape", "/tmp/escape", "intake/task-id/doc.md", "deliverables/other-task/file.md"],
)
def test_collector_enforces_paths_before_any_write(tmp_path: Path, relative: str) -> None:
    project = tmp_path / "project"
    project.mkdir()
    task = {
        "id": "task-id",
        "role": "architecte-solutions",
        "expected_outputs": ["deliverables/task-id/good.md", relative],
    }
    with pytest.raises(ValueError, match="collect_scopes"):
        _collect(
            ROOT, project, task, {"files": {"deliverables/task-id/good.md": "good", relative: "bad"}}
        )
    assert not list(project.rglob("*.md"))


def test_collector_rejects_symlink_escape(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (project / "deliverables").symlink_to(outside, target_is_directory=True)
    task = {
        "id": "task-id",
        "role": "ingenieur-devops",
        "expected_outputs": ["deliverables/task-id/file.md"],
    }
    with pytest.raises(ValueError, match="liée"):
        _collect(ROOT, project, task, {"files": {task["expected_outputs"][0]: "escape"}})
    assert not list(outside.rglob("*.md"))


def test_daily_patch_really_bounds_memory_and_disables_unsafe_tools(tmp_path: Path) -> None:
    patch = build_openclaw_patch(ROOT, tmp_path)
    defaults = patch["agents"]["defaults"]
    assert defaults["maxConcurrent"] == defaults["subagents"]["maxConcurrent"] == 1
    assert defaults["pdfMaxMb"] == 50
    assert "reserveTokens" not in defaults["compaction"]
    for role in patch["agents"]["entries"].values():
        assert role["model"]["fallbacks"] == []
        assert {"exec", "process", "write", "edit", "apply_patch"}.issubset(role["tools"]["deny"])
    models = patch["models"]["providers"]["ollama"]["models"]
    assert len(models) == 3
    assert {model["id"] for model in models} == {
        "qwen3.5:9b-q4_K_M", "ornith-1.5:9b", "gemma4:12b-it-q4_K_M",
    }
    assert all(model["params"] == {
        "num_ctx": 32768,
        "num_predict": 4096,
        "keep_alive": "3m",
    } for model in models)
    assert all(model["reasoning"] is (model["id"] != "gemma4:12b-it-q4_K_M")
               for model in models)
    # The model must never be able to update OpenClaw or chain a three-step tool search.
    assert {"gateway", "presence"} <= set(patch["tools"]["deny"])
    assert patch["tools"]["toolSearch"] is False


def _two_outputs(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    project = tmp_path / "project"
    (project / "deliverables/task-id").mkdir(parents=True)
    task = {
        "id": "task-id",
        "role": "architecte-solutions",
        "expected_outputs": ["deliverables/task-id/a.md", "deliverables/task-id/b.md"],
    }
    return project, task


def test_collector_recovers_from_staging_files_left_by_a_crash(tmp_path: Path) -> None:
    """A09: a fixed staging name used to make every later attempt fail (FileExistsError)."""
    project, task = _two_outputs(tmp_path)
    out = project / "deliverables/task-id"
    (out / "a.md.worker-tmp").write_bytes(b"partiel")  # previous fixed name
    (out / ".a.md.x1y2z3.worker-tmp").write_bytes(b"partiel")  # per-attempt name
    for attempt in (1, 2):
        files = {f"deliverables/task-id/{n}.md": f"{n}{attempt}" for n in ("a", "b")}
        assert _collect(ROOT, project, task, {"files": files}) == task["expected_outputs"]
    assert sorted(p.name for p in out.iterdir()) == ["a.md", "b.md"]
    assert (out / "a.md").read_text() == "a2" and (out / "b.md").read_text() == "b2"


def test_collector_failure_while_staging_keeps_previous_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tempfile

    from clawfedora import project_worker

    project, task = _two_outputs(tmp_path)
    out = project / "deliverables/task-id"
    (out / "a.md").write_text("ancienne version")
    real = tempfile.mkstemp
    calls: list[str] = []

    def failing_second(*args: Any, **kwargs: Any) -> tuple[int, str]:
        calls.append(str(kwargs.get("prefix")))
        if len(calls) == 2:
            raise OSError("disque plein simulé")
        return real(*args, **kwargs)

    monkeypatch.setattr(project_worker.tempfile, "mkstemp", failing_second)
    files = {f"deliverables/task-id/{n}.md": f"{n}-nouveau" for n in ("a", "b")}
    with pytest.raises(OSError, match="disque plein"):
        _collect(ROOT, project, task, {"files": files})
    assert (out / "a.md").read_text() == "ancienne version"  # nothing promoted
    assert sorted(p.name for p in out.iterdir()) == ["a.md"]  # staging cleaned


def test_changed_output_blocks_audit_before_inference(planned: tuple[Path, Path]) -> None:
    runtime, project = planned

    def producer(_role: str, prompt: str, _session: str) -> dict[str, Any]:
        task = json.loads(prompt.split("\n", 1)[1])
        return {"files": {task["expected_outputs"][0]: "validated"}, "summary": "ready"}

    run_project_tasks(ROOT, runtime, project, runner=producer)
    (project / "deliverables/design-choice/report.md").write_text("changed")

    def forbidden(*_args: Any) -> dict[str, Any]:
        pytest.fail("audit must not invoke a model after an integrity failure")

    with pytest.raises(ValueError, match="artifact exchange invalide avant audit"):
        review_project(ROOT, runtime, project, "validation", runner=forbidden)
    assert not (project / "evidence/validation_report.json").exists()


@pytest.mark.parametrize(
    "planned",
    [[
        {"id": "design", "role": "architecte-solutions", "title": "Design",
         "objective": "Concevoir", "depends_on": [],
         "expected_outputs": ["deliverables/design/report.md"],
         "acceptance_criteria": ["Schéma lisible"]},
        {"id": "code", "role": "ingenieur-devops", "title": "Code",
         "objective": "Corriger", "depends_on": [],
         "expected_outputs": ["deliverables/code/report.md"],
         "acceptance_criteria": ["Validation mesurée"]},
        {"id": "docs", "role": "expert-recherche", "title": "Documentation",
         "objective": "Expliquer", "depends_on": [],
         "expected_outputs": ["deliverables/docs/report.md"],
         "acceptance_criteria": ["Sources identifiées"]},
    ]],
    indirect=True,
)
def test_model_affinity_preserves_approved_dependencies(
    planned: tuple[Path, Path],
) -> None:
    runtime, project = planned
    transition_project(
        ROOT, project, "IN_PROGRESS", actor="chef-operations", reason="test"
    )
    assert ready_tasks(ROOT, project, prefer_model="ornith-code")[0]["role"] == (
        "ingenieur-devops"
    )
    assert ready_tasks(ROOT, project, prefer_model="gemma-expert")[0]["role"] == (
        "architecte-solutions"
    )
    assert len(ready_tasks(ROOT, project, prefer_model="gemma-expert")) == 1


def test_exhausted_local_attempts_require_operator_intervention(
    planned: tuple[Path, Path],
) -> None:
    from clawfedora.project_control import progress

    runtime, project = planned
    def bad(*_args: object) -> dict[str, object]:
        return {"files": {"deliverables/other-task/escape.md": "bad"}}
    assert run_project_tasks(ROOT, runtime, project, runner=bad)[0]["status"] == "FAIL"
    assert run_project_tasks(ROOT, runtime, project, runner=bad)[0]["status"] == "FAIL"
    assert progress(runtime)["phase"] == "blocked_local"
    assert run_project_tasks(ROOT, runtime, project, runner=bad) == []


@pytest.mark.parametrize(
    "planned",
    [[
        {"id": "design", "role": "architecte-solutions", "title": "Design",
         "objective": "Comparer", "depends_on": [],
         "expected_outputs": ["deliverables/design/report.md"],
         "acceptance_criteria": ["Deux choix"]},
        {"id": "code", "role": "ingenieur-devops", "title": "Code",
         "objective": "Documenter", "depends_on": [],
         "expected_outputs": ["deliverables/code/report.md"],
         "acceptance_criteria": ["Validation"]},
        {"id": "followup", "role": "ingenieur-devops", "title": "Suite",
         "objective": "Documenter", "depends_on": ["design"],
         "expected_outputs": ["deliverables/followup/report.md"],
         "acceptance_criteria": ["Preuve"]},
    ]],
    indirect=True,
)
def test_worker_reuses_resident_model_on_entry_without_skipping_dependencies(
    planned: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch,
) -> None:
    from clawfedora import ollama_api, project_worker
    from clawfedora.lifecycle import model_plan
    from clawfedora.project_common import write_json

    runtime, project = planned
    models = model_plan(ROOT)
    identities = [
        {**item, "digest": str(index + 1) * 64, "quantization_level": "Q4_K_M"}
        for index, item in enumerate(models)
    ]
    write_json(runtime / "state/model-identities.json", {
        "models": {item["runtime_id"]: item for item in identities},
    })
    resident = next(item for item in identities if item["alias"] == "ornith-code")
    reads: list[str] = []

    def request(url: str, **_kwargs: Any) -> dict[str, Any]:
        reads.append(url)
        if url.endswith("/api/tags"):
            return {"models": [
                {"name": item["runtime_id"], "digest": item["digest"],
                 "details": {"quantization_level": "Q4_K_M"}}
                for item in identities
            ]}
        assert url.endswith("/api/ps")
        return {"models": [{
            "name": resident["runtime_id"], "digest": resident["digest"],
            "context_length": 32768, "size": 8 * 1024**3,
        }]}

    tasks: list[str] = []

    def invoke_local(_role: str, prompt: str, _session: str) -> dict[str, Any]:
        task = json.loads(prompt.split("\n", 1)[1])
        tasks.append(task["id"])
        return {"files": {task["expected_outputs"][0]: "Choix et preuve."},
                "summary": "Document collecté"}

    monkeypatch.setattr(ollama_api, "request_json", request)
    monkeypatch.setattr(project_worker, "project_runner", lambda *_args: invoke_local)
    result = run_project_tasks(ROOT, runtime, project)
    assert tasks == ["code", "design", "followup"]
    assert all(row["status"] == "PASS" for row in result)
    assert reads == [
        "http://127.0.0.1:11434/api/tags", "http://127.0.0.1:11434/api/ps",
    ]
    assert read_json(project / "project.json")["status"] == "VALIDATING"


def _notion_inventory() -> tuple[str, dict[str, Any]]:
    root = "a" * 32
    row = {
        "category": "page", "id": root, "parent_id": None, "position": None,
        "sha256": "b" * 64, "observable_sha256": "c" * 64,
        "cover_present": False, "icon_present": False,
    }
    report = {
        "schema": 2, "classification": "private_local_only", "root_page": root,
        "assessment": ni.ASSESSMENT, "api_version": ni.VERSION,
        "captured_at": datetime.now(UTC).isoformat(), "requests": 2, "counts": {"page": 1},
        "objects": [row], "structure_sha256": nw._digest([row]),
        "limitations": sorted(ni.BASE_LIMITS), "native_render_verified": False,
        "remote_write": False,
    }
    report["inventory_sha256"] = nw._digest(report)
    return root, report


def test_worker_runs_approved_notion_tool_and_collects_only_summary(
    planned: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, project = planned
    root, inventory = _notion_inventory()
    approval = notion.approve(
        runtime, project.name, "design-choice", root, ["plan", "inventory"],
        {"inventory": inventory},
    )
    assert notion.approve(
        runtime, project.name, "design-choice", root, ["inventory", "plan"],
        {"inventory": inventory}, replace_sha256=approval,
    ) == approval
    receipts = []

    def runner(role: str, prompt: str, session: str) -> dict[str, Any]:
        task = json.loads(prompt.split("\n", 1)[1])
        scope = f"projects/{project.name}/{task['id']}/{session}"
        workspace = runtime / "workspaces" / role
        if task["id"] == "design-choice":
            assert notion.TOOL in prompt and (workspace / scope / notion.MARKER).is_file()
            assert root not in (workspace / scope / notion.MARKER).read_text()
            args = {"scope": scope, "operation": "plan"}
            with pytest.raises(ValueError, match="hors du snapshot"):
                invoke(runtime, role, workspace, notion.TOOL,
                       {**args, "scope": scope.replace(project.name, "other-project")})
            with pytest.raises(ValueError, match="non approuvée"):
                invoke(runtime, role, workspace, notion.TOOL, {**args, "operation": "duplicates"})
            value = invoke(runtime, role, workspace, notion.TOOL, args)
            assert value["status"] == "REVIEW_REQUIRED" and value["counts"] == {"issues": 0}
            assert root not in json.dumps(value)
            report = notion.verify(
                runtime, project.name, task["id"], session, "plan", value["artifact_sha256"],
            )
            assert report.stat().st_mode & 0o777 == 0o600
            assert read_json(report)["report"]["executable"] is False
            receipts.append(Path(value["receipt"]).name)
        else:
            assert notion.TOOL not in prompt
            with pytest.raises(ValueError, match="interdit pour ce rôle"):
                invoke(runtime, role, workspace, notion.TOOL,
                       {"scope": scope, "operation": "inventory"})
        return {"files": {task["expected_outputs"][0]: "# Résultat\n"}, "summary": "Vérification"}

    def no_network(*args: Any) -> None:
        raise AssertionError("worker audit contacted Notion")

    monkeypatch.setattr(ni, "_get", no_network)
    results = run_project_tasks(ROOT, runtime, project, runner=runner)
    assert results[0]["status"] == "PASS"
    collected = project / "evidence/design-choice" / f"tool-{receipts[0]}"
    proof = read_json(collected)
    assert proof["approval_sha256"] == approval
    assert "report" not in proof and root not in json.dumps(proof)
    with pytest.raises(ValueError, match="tâche locale active"):
        invoke(runtime, "architecte-solutions", runtime / "workspaces/architecte-solutions",
               notion.TOOL, {"scope": proof["scope"], "operation": "inventory"})


def test_worker_rejects_a_changed_notion_artifact_before_collecting(
    planned: tuple[Path, Path],
) -> None:
    runtime, project = planned
    root, inventory = _notion_inventory()
    notion.approve(runtime, project.name, "design-choice", root, ["inventory"],
                   {"inventory": inventory})

    def runner(role: str, prompt: str, session: str) -> dict[str, Any]:
        task = json.loads(prompt.split("\n", 1)[1])
        scope = f"projects/{project.name}/{task['id']}/{session}"
        value = invoke(runtime, role, runtime / "workspaces" / role, notion.TOOL,
                       {"scope": scope, "operation": "inventory"})
        path = notion.verify(
            runtime, project.name, task["id"], session, "inventory", value["artifact_sha256"],
        )
        modified = read_json(path)
        modified["counts"]["page"] = 42
        write_json(path, modified)
        path.chmod(0o600)
        return {"files": {task["expected_outputs"][0]: "# Résultat\n"}, "summary": "Vérification"}

    results = run_project_tasks(ROOT, runtime, project, runner=runner)
    assert results[0]["status"] == "FAIL"
    assert "empreinte de preuve Notion divergente" in results[0]["summary"]
    assert not list((project / "evidence/design-choice").glob("tool-*.json"))


def test_notion_approval_is_bound_to_worker_task_and_role(planned: tuple[Path, Path]) -> None:
    runtime, project = planned
    root, inventory = _notion_inventory()
    with pytest.raises(ValueError, match="non autorisée pour le rôle"):
        notion.approve(runtime, project.name, "research-check", root, ["inventory"],
                       {"inventory": inventory})
    task_path = project / "context/tasks/design-choice.json"
    contract = read_json(task_path)
    contract["task"]["role"] = "auditeur-qualite"
    write_json(task_path, contract)
    with pytest.raises(ValueError, match="non autorisée pour le rôle"):
        notion.approve(runtime, project.name, "design-choice", root, ["plan"],
                       {"inventory": inventory})

    digest = notion.approve(runtime, project.name, "design-choice", root, ["inventory"],
                            {"inventory": inventory})
    with pytest.raises(ValueError, match="remplacée entre-temps"):
        notion.approve(runtime, project.name, "design-choice", root, ["inventory"],
                       {"inventory": inventory}, replace_sha256="f" * 64)
    snapshot = runtime / "workspaces/auditeur-qualite/projects/temporary"
    original = contract["task"]
    assert notion.bind_snapshot(runtime, project.name, original, snapshot, local=False) is None
    marker = notion.bind_snapshot(runtime, project.name, original, snapshot, local=True)
    assert marker is not None and marker["approval_sha256"] == digest
    with pytest.raises(ValueError, match="périmée"):
        notion.bind_snapshot(
            runtime, project.name, {**original, "objective": "Autre"}, snapshot, local=True,
        )
