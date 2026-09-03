from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from clawfedora.core_config import resolve_runtime_root
from clawfedora.project_common import project_path, read_json
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


def _load_object(path: str) -> dict[str, Any]:
    payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON objet requis: {path}")
    return payload


def add_project_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    project = subparsers.add_parser("project", help="moteur de projets multi-agents")
    commands = project.add_subparsers(dest="project_command", required=True)

    create = commands.add_parser("create", help="créer et ingérer un projet")
    create.add_argument("--runtime-root")
    create.add_argument("--project-id", required=True)
    create.add_argument("--title", required=True)
    create.add_argument("--intake", action="append", default=[])
    create.add_argument("--source", action="append", default=[])
    create.add_argument("--deliverable", action="append", default=[])

    status = commands.add_parser("status")
    status.add_argument("--runtime-root")
    status.add_argument("--project-id", required=True)

    analysis = commands.add_parser("analysis")
    analysis.add_argument("--runtime-root")
    analysis.add_argument("--project-id", required=True)
    analysis.add_argument("--file", required=True)

    clarifications = commands.add_parser("clarifications")
    clarifications.add_argument("--runtime-root")
    clarifications.add_argument("--project-id", required=True)

    resolve = commands.add_parser("resolve")
    resolve.add_argument("--runtime-root")
    resolve.add_argument("--project-id", required=True)
    resolve.add_argument("--id", required=True)
    resolve.add_argument("--answer", required=True)
    resolve.add_argument("--actor", default="human")

    plan = commands.add_parser("plan")
    plan.add_argument("--runtime-root")
    plan.add_argument("--project-id", required=True)
    plan.add_argument("--file", required=True)

    assign = commands.add_parser("assign")
    assign.add_argument("--runtime-root")
    assign.add_argument("--project-id", required=True)

    ready = commands.add_parser("ready")
    ready.add_argument("--runtime-root")
    ready.add_argument("--project-id", required=True)

    result = commands.add_parser("result")
    result.add_argument("--runtime-root")
    result.add_argument("--project-id", required=True)
    result.add_argument("--task-id", required=True)
    result.add_argument("--agent", required=True)
    result.add_argument("--status", choices=("PASS", "FAIL"), required=True)
    result.add_argument("--output", action="append", default=[])
    result.add_argument("--summary", required=True)

    transition = commands.add_parser("transition")
    transition.add_argument("--runtime-root")
    transition.add_argument("--project-id", required=True)
    transition.add_argument("--to", required=True)
    transition.add_argument("--actor", required=True)
    transition.add_argument("--reason", required=True)
    transition.add_argument("--human-approved", action="store_true")

    verdict = commands.add_parser("verdict")
    verdict.add_argument("--runtime-root")
    verdict.add_argument("--project-id", required=True)
    verdict.add_argument("--kind", choices=("validation", "review"), required=True)
    verdict.add_argument("--verdict", choices=("PASS", "FAIL"), required=True)
    verdict.add_argument("--reviewer", default="auditeur-qualite")
    verdict.add_argument("--findings-file")

    package = commands.add_parser("package")
    package.add_argument("--runtime-root")
    package.add_argument("--project-id", required=True)
    package.add_argument("--actor", default="ingenieur-release-forges")

    commands.add_parser(
        "selftest",
        help="cycle projet synthétique complet, local et sans réseau",
    )


def _runtime(args: argparse.Namespace) -> Path:
    return resolve_runtime_root(getattr(args, "runtime_root", None))


def _project(args: argparse.Namespace) -> Path:
    return project_path(_runtime(args), str(args.project_id))


def _selftest(repo_root: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="clawfedora-project-") as temporary:
        base = Path(temporary)
        runtime = base / "runtime"
        source = base / "request.md"
        source.write_text(
            "# Demande\nProduire un livrable texte validé.\n",
            encoding="utf-8",
        )
        project = create_project(
            repo_root,
            runtime,
            "selftest-project",
            "Self-test projet",
            intake_items=[source],
            expected_deliverables=["deliverables/write-report/final.md"],
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
            repo_root,
            project,
            {
                "summary": "Créer puis vérifier un livrable texte.",
                "objectives": ["livrable validé"],
                "constraints": ["local-first"],
                "deliverables": ["final.md"],
                "ambiguities": [],
                "missing_information": [],
                "risks": [],
                "decisions_required": [],
                "source_coverage": coverage,
            },
        )
        create_clarifications(repo_root, project)
        transition_project(
            repo_root,
            project,
            "ANALYZED",
            actor="chef-operations",
            reason="analysis_ready",
        )
        store_plan(
            repo_root,
            project,
            {
                "workstreams": ["documentation"],
                "tasks": [
                    {
                        "id": "write-report",
                        "role": "redacteur-technique",
                        "title": "Rédiger le rapport",
                        "objective": "Produire le livrable final",
                        "depends_on": [],
                        "expected_outputs": ["deliverables/write-report/final.md"],
                        "acceptance_criteria": ["fichier non vide"],
                    }
                ],
            },
        )
        transition_project(
            repo_root,
            project,
            "PLANNED",
            actor="chef-operations",
            reason="plan_ready",
        )
        create_assignments(repo_root, project)
        transition_project(
            repo_root,
            project,
            "ASSIGNED",
            actor="chef-operations",
            reason="tasks_assigned",
        )
        transition_project(
            repo_root,
            project,
            "IN_PROGRESS",
            actor="chef-operations",
            reason="execution_start",
        )
        output = project / "deliverables" / "write-report" / "final.md"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("# Livrable\nSelf-test PASS.\n", encoding="utf-8")
        record_task_result(
            repo_root,
            project,
            task_id="write-report",
            agent="redacteur-technique",
            status="PASS",
            outputs=["deliverables/write-report/final.md"],
            summary="livrable créé",
        )
        transition_project(
            repo_root,
            project,
            "VALIDATING",
            actor="auditeur-qualite",
            reason="tasks_pass",
        )
        store_verdict(
            repo_root,
            project,
            "validation",
            "PASS",
            [],
            reviewer="auditeur-qualite",
        )
        transition_project(
            repo_root,
            project,
            "REVIEW",
            actor="auditeur-qualite",
            reason="validation_pass",
        )
        store_verdict(
            repo_root,
            project,
            "review",
            "PASS",
            [],
            reviewer="auditeur-qualite",
        )
        package_project(repo_root, project, actor="ingenieur-release-forges")
        transition_project(
            repo_root,
            project,
            "COMPLETE",
            actor="selftest-human",
            reason="synthetic_selftest_approval",
            human_approved=True,
        )
        return {
            "verdict": "PASS",
            "project_id": "selftest-project",
            "status": current_status(project),
        }


def run_project_command(repo_root: Path, args: argparse.Namespace) -> int:
    try:
        command = str(args.project_command)
        if command == "create":
            project = create_project(
                repo_root,
                _runtime(args),
                str(args.project_id),
                str(args.title),
                intake_items=[Path(value) for value in args.intake],
                source_items=[Path(value) for value in args.source],
                expected_deliverables=list(args.deliverable),
            )
            print(f"PROJECT_CREATE_RESULT=PASS path={project}")
        elif command == "status":
            project_manifest = read_json(_project(args) / "project.json")
            print(json.dumps(project_manifest, indent=2, ensure_ascii=False))
        elif command == "analysis":
            path = store_analysis(
                repo_root,
                _project(args),
                _load_object(args.file),
            )
            print(f"PROJECT_ANALYSIS={path}")
        elif command == "clarifications":
            path = create_clarifications(repo_root, _project(args))
            print(f"PROJECT_CLARIFICATIONS={path}")
        elif command == "resolve":
            item = resolve_clarification(
                repo_root,
                _project(args),
                args.id,
                args.answer,
                actor=args.actor,
            )
            print(json.dumps(item, ensure_ascii=False))
        elif command == "plan":
            path = store_plan(
                repo_root,
                _project(args),
                _load_object(args.file),
            )
            print(f"PROJECT_PLAN={path}")
        elif command == "assign":
            path = create_assignments(repo_root, _project(args))
            print(f"PROJECT_ASSIGNMENTS={path}")
        elif command == "ready":
            ready = ready_tasks(repo_root, _project(args))
            print(json.dumps(ready, indent=2, ensure_ascii=False))
        elif command == "result":
            result = record_task_result(
                repo_root,
                _project(args),
                task_id=args.task_id,
                agent=args.agent,
                status=args.status,
                outputs=list(args.output),
                summary=args.summary,
            )
            print(json.dumps(result, indent=2, ensure_ascii=False))
        elif command == "transition":
            payload = transition_project(
                repo_root,
                _project(args),
                args.to,
                actor=args.actor,
                reason=args.reason,
                human_approved=bool(args.human_approved),
            )
            print(f"PROJECT_STATUS={payload['status']}")
        elif command == "verdict":
            findings: list[dict[str, Any]] = []
            if args.findings_file:
                raw = json.loads(
                    Path(args.findings_file).read_text(encoding="utf-8")
                )
                if not isinstance(raw, list) or any(
                    not isinstance(item, dict) for item in raw
                ):
                    raise ValueError(
                        "findings-file doit contenir une liste JSON d'objets"
                    )
                findings = raw
            path = store_verdict(
                repo_root,
                _project(args),
                args.kind,
                args.verdict,
                findings,
                reviewer=args.reviewer,
            )
            print(f"PROJECT_VERDICT={path}")
        elif command == "package":
            package, report = package_project(
                repo_root,
                _project(args),
                actor=args.actor,
            )
            print(f"PROJECT_PACKAGE=PASS manifest={package} report={report}")
        elif command == "selftest":
            print(json.dumps(_selftest(repo_root), ensure_ascii=False))
        else:
            raise ValueError(f"commande project inconnue: {command}")
    except (
        FileNotFoundError,
        FileExistsError,
        KeyError,
        OSError,
        PermissionError,
        ValueError,
    ) as exc:
        print(f"PROJECT_RESULT=FAIL error={exc}")
        return 2
    return 0
