"""Small project learning contract and human checkpoints; no skill scores inferred."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from clawfedora.project_common import now, read_json, validate_task_id, write_json


def initialize(project: Path, mode: str = "guided", goals: list[str] | None = None) -> None:
    if mode not in {"guided", "direct"}:
        raise ValueError("accompagnement guided ou direct requis")
    goals = goals or []
    if (
        not isinstance(goals, list)
        or len(goals) > 3
        or any(not isinstance(g, str) or not g.strip() or len(g) > 160 for g in goals)
    ):
        raise ValueError("au plus trois objectifs d’apprentissage courts")
    write_json(
        project / "context/learning/contract.json",
        {
            "schema_version": "1.0.0",
            "mode": mode,
            "goals": goals,
            "specialty": "DevOps infrastructure/OPS",
            "instruction": "Une étape à la fois; l’apprenant produit et vérifie son travail.",
            "skill_acquisition": "Aucune compétence acquise automatiquement.",
        },
    )


def contract(project: Path) -> dict[str, Any]:
    path = project / "context/learning/contract.json"
    if not path.is_file():
        # Existing approved plans keep their behavior; no silent retrofit of human gates.
        return {"mode": "direct", "goals": [], "legacy": True}
    value = read_json(path)
    if value.get("mode") not in {"guided", "direct"}:
        raise ValueError("contrat d’apprentissage invalide")
    return value


def checkpoint_path(project: Path, task_id: str) -> Path:
    return project / "context/learning/tasks" / f"{validate_task_id(task_id)}.json"


def checkpoints(project: Path) -> list[dict[str, Any]]:
    return [read_json(p) for p in sorted((project / "context/learning/tasks").glob("*.json"))]


def awaiting(project: Path) -> list[dict[str, Any]]:
    return [item for item in checkpoints(project) if item.get("status") == "AWAITING_PRACTICE"]


def instructions(project: Path) -> str:
    value = contract(project)
    goals = "; ".join(value.get("goals", [])) or "comprendre le mécanisme et apprendre à vérifier"
    if value["mode"] == "direct":
        return f"Mode direct choisi: résultat complet autorisé, expliquer l’utile. {goals}. "
    return (
        f"Mode guidé. Objectifs: {goals}. Ne fais pas l’exercice à la place de l’apprenant. "
        "Dans summary: problème, mécanisme simple, petit exemple distinct et prochaine action. "
        "Dans files: amorce courte ou trame à compléter, avec TODO explicites, pas une solution "
        "entière. Au plus trois notions. L’apprenant complétera ces fichiers et soumettra son "
        "raisonnement/résultat observé; cette proposition ne valide aucune tâche. "
    )


def stage(project: Path, task: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    task_id = str(task["id"])
    path = checkpoint_path(project, task_id)
    if path.is_file() and read_json(path).get("status") == "AWAITING_PRACTICE":
        raise ValueError("une étape guidée attend déjà le travail de l’apprenant")
    value = {
        "task_id": task_id,
        "role": task["role"],
        "status": "AWAITING_PRACTICE",
        "created_at": now(),
        "guidance": str(response.get("summary", "")),
        "files": response["files"],
        "acceptance_criteria": task["acceptance_criteria"],
        "skill_acquired": False,
    }
    write_json(path, value)
    return value


def submit(
    repo: Path, runtime: Path, project: Path, task_id: str, data: dict[str, Any]
) -> dict[str, Any]:
    from clawfedora.project_control import write_progress
    from clawfedora.project_engine import (
        all_tasks_pass,
        current_status,
        record_task_result,
        transition_project,
    )
    from clawfedora.project_intake import validate_input_integrity
    from clawfedora.project_worker import _collect, worker_lock

    with worker_lock(runtime, allow_gaming=True):
        if data.get("human_approved") is not True:
            raise ValueError("soumission humaine explicite requise")
        if current_status(project) != "IN_PROGRESS" or contract(project)["mode"] != "guided":
            raise ValueError("étape guidée active requise")
        if validate_input_integrity(project):
            raise ValueError("intégrité des sources invalide")
        requested = validate_task_id(task_id)
        checkpoint = next(
            (item for item in checkpoints(project) if item.get("task_id") == requested), None
        )
        if checkpoint is None:
            raise ValueError("aucune étape guidée connue pour cette tâche")
        # The request selects an existing checkpoint; only its managed identity builds paths.
        task_id = str(checkpoint["task_id"])
        if checkpoint.get("status") != "AWAITING_PRACTICE":
            raise ValueError("aucune pratique en attente pour cette tâche")
        explanation = data.get("explanation")
        observations = data.get("observations", "Pas d’exécution réelle déclarée.")
        if not isinstance(explanation, str) or not 1 <= len(explanation.strip()) <= 2000:
            raise ValueError("expliquer brièvement le travail effectué")
        if not isinstance(observations, str) or len(observations) > 4000:
            raise ValueError("résultats observés limités à 4000 caractères")
        files = data.get("files")
        if not isinstance(files, dict) or any(not isinstance(v, str) for v in files.values()):
            raise ValueError("contenus des fichiers requis")
        if sum(len(v.encode()) for v in files.values()) > 60000:
            raise ValueError("soumission limitée à 60000 octets")
        task = read_json(project / "context/tasks" / f"{validate_task_id(task_id)}.json")["task"]
        outputs = _collect(repo, project, task, {"files": files})
        result = record_task_result(
            repo,
            project,
            task_id=task_id,
            agent=str(task["role"]),
            status="PASS",
            outputs=outputs,
            summary="Travail soumis par l’apprenant; audits techniques encore requis.",
        )
        checkpoint.update(
            status="SUBMITTED",
            submitted_at=now(),
            files=files,
            explanation=explanation.strip(),
            observations=observations.strip(),
            origin="human_self_report",
            runtime_tested=False,
            skill_acquired=False,
        )
        write_json(checkpoint_path(project, task_id), checkpoint)
        if all_tasks_pass(repo, project):
            transition_project(
                repo, project, "VALIDATING", actor="human", reason="practice_submitted"
            )
            write_progress(runtime, project, "awaiting_validation")
        else:
            write_progress(runtime, project, "awaiting_next_step")
        return result
