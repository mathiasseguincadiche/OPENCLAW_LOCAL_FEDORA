"""Small project learning contract and human checkpoints; no skill scores inferred."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from clawfedora.drawio import normalize_diagram
from clawfedora.project_common import now, read_json, validate_task_id, write_json


def initialize(project: Path, mode: str = "direct", goals: list[str] | None = None) -> None:
    if mode not in {"adaptive", "guided", "direct"}:
        raise ValueError("accompagnement adaptive, guided ou direct requis")
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
            "practice_opt_in_required": True,
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
    if value.get("mode") not in {"adaptive", "guided", "direct"}:
        raise ValueError("contrat d’apprentissage invalide")
    return value


def checkpoint_path(project: Path, task_id: str) -> Path:
    return project / "context/learning/tasks" / f"{validate_task_id(task_id)}.json"


def checkpoints(project: Path) -> list[dict[str, Any]]:
    return [read_json(p) for p in sorted((project / "context/learning/tasks").glob("*.json"))]


def awaiting(project: Path) -> list[dict[str, Any]]:
    return [item for item in checkpoints(project) if item.get("status") == "AWAITING_PRACTICE"]


def task_mode(project: Path, task: dict[str, Any]) -> str:
    policy = contract(project)
    mode = policy["mode"]
    if mode != "adaptive":
        return str(mode)
    # Existing approved v1.0 contracts retain their original behaviour.
    # New adaptive projects need an affirmative choice to create a practice gate.
    if policy.get("practice_opt_in_required") is True:
        return ("guided" if task.get("learning_mode") == "guided"
                and task.get("practice_opt_in") is True else "direct")
    # Only the approved plan can choose task-level support; no model-selected runtime gate.
    return str(
        task.get(
            "learning_mode",
            "guided" if task["role"] in {"architecte-solutions", "ingenieur-devops"} else "direct",
        )
    )


def pending_feedback(project: Path) -> list[dict[str, Any]]:
    return [item for item in checkpoints(project) if item.get("status") == "AWAITING_FEEDBACK"]


def instructions(project: Path, task: dict[str, Any] | None = None) -> str:
    value = contract(project)
    goals = "; ".join(value.get("goals", [])) or "comprendre le mécanisme et apprendre à vérifier"
    selected = task_mode(project, task) if task is not None else (
        "direct" if value["mode"] == "adaptive"
        and value.get("practice_opt_in_required") is True else value["mode"]
    )
    if selected == "direct":
        return f"Mode direct choisi: résultat complet autorisé, expliquer l’utile. {goals}. "
    return (
        f"Mode guidé. Objectifs: {goals}. Ne fais pas l’exercice à la place de l’apprenant. "
        "Dans summary: besoin OPS, mécanisme, petit exemple expliqué distinct et prochaine action. "
        "Dans files: amorce courte ou trame à compléter, avec TODO explicites, pas une solution "
        "entière. Aucun TODO sans explication. Demander une prévision ou observation utile, "
        "pas un quiz systématique; réduire les indices selon les essais reçus. Au plus trois "
        "notions nouvelles. L’apprenant complétera ces fichiers et soumettra son "
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
    from clawfedora.project_engine import current_status
    from clawfedora.project_intake import validate_input_integrity
    from clawfedora.project_worker import _collection_targets, worker_lock

    with worker_lock(runtime, allow_gaming=True):
        if data.get("human_approved") is not True:
            raise ValueError("soumission humaine explicite requise")
        if current_status(project) != "IN_PROGRESS" or contract(project)["mode"] == "direct":
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
        if checkpoint.get("status") not in {"AWAITING_PRACTICE", "AWAITING_FEEDBACK"}:
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
        if set(files) != set(task["expected_outputs"]):
            raise ValueError("sorties différentes des chemins attendus")
        files = {
            path: normalize_diagram(content) if path.lower().endswith(".drawio") else content
            for path, content in files.items()
        }
        if sum(len(v.encode()) for v in files.values()) > 60000:
            raise ValueError("soumission décompressée limitée à 60000 octets")
        _collection_targets(repo, project, task, {"files": files})
        # Keep drafts out of published artifacts and dependency bundles until feedback.
        previous = checkpoint.get("submissions", [])
        if len(previous) >= 20:
            raise ValueError("20 essais conservés: demander une reprise approuvée de cette tâche")
        previous.append(
            {
                "at": now(),
                "files": files,
                "explanation": explanation.strip(),
                "observations": observations.strip(),
            }
        )
        checkpoint.update(
            status="AWAITING_FEEDBACK",
            submitted_at=now(),
            submission_id=str(uuid.uuid4()),
            files=files,
            explanation=explanation.strip(),
            observations=observations.strip(),
            origin="human_self_report",
            runtime_tested=False,
            skill_acquired=False,
            submissions=previous,
            feedback_attempts=0,
        )
        write_json(checkpoint_path(project, task_id), checkpoint)
        assignments_path = project / "context/task_assignments.json"
        assignments = read_json(assignments_path)
        for item in assignments["tasks"]:
            if item["task_id"] == task_id:
                item["status"] = "AWAITING_FEEDBACK"
        write_json(assignments_path, assignments)
        write_progress(runtime, project, "awaiting_feedback", task=task_id)
        return {"task_id": task_id, "status": "AWAITING_FEEDBACK"}
