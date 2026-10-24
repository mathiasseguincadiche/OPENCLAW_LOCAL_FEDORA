"""Read-only guidance shared by the WebUI shortcuts and the project dashboard."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from clawfedora import chat_flow, chat_projects
from clawfedora.core_config import AGENT_IDS
from clawfedora.project_common import validate_project_id
from clawfedora.project_control import is_paused, progress

PHASES = {
    "chat": "Une discussion utilise l’atelier",
    "preparing": "Préparation du projet",
    "running": "Rédaction d’une étape",
    "reviewing": "Relecture des livrables",
    "feedback": "Retour sur votre travail",
}


def activity(runtime: Path) -> dict[str, Any]:
    """Report the shared lock and the last recorded phase; never infer a percentage."""
    working = progress(runtime)
    active = bool(working["active"])
    phase = str(working.get("phase", ""))
    label = (
        PHASES.get(phase, "Une opération utilise l’atelier")
        if active
        else "Le dernier traitement a été interrompu"
        if phase == "interrupted"
        else "L’atelier est disponible"
    )
    elapsed: int | None = None
    if active and phase in PHASES:
        try:
            started = datetime.fromisoformat(str(working.get("started_at", "")))
            delta = (datetime.now(UTC) - started).total_seconds()
            if 0 <= delta <= 7 * 86400:
                elapsed = int(delta)
        except (ValueError, TypeError):
            pass
    elapsed_label = ""
    if elapsed is not None:
        minutes, seconds = divmod(elapsed, 60)
        elapsed_label = f"{minutes} min {seconds:02d} s" if minutes else f"{seconds} s"
    project_id = str(working.get("project_id", ""))
    try:
        project_id = validate_project_id(project_id) if project_id else ""
    except ValueError:
        project_id = ""
    return {
        "active": active,
        "label": label,
        "elapsed_seconds": elapsed,
        "elapsed_label": elapsed_label,
        "project_id": project_id if active else "",
        "role": working.get("role") if active and working.get("role") in AGENT_IDS else "",
        "hint": "Attendez la fin avant de lancer une autre génération."
        if active
        else "Consultez l’état du projet avant de reprendre."
        if phase == "interrupted"
        else "Vous pouvez poser une question ou ouvrir un projet.",
    }


def project_hint(runtime: Path, project: Path) -> str:
    from clawfedora.learning import awaiting, pending_feedback

    if is_paused(runtime, project):
        return "Le projet est en pause : consultez son état et la raison avant de reprendre."
    if awaiting(project):
        return "Complétez l’étape guidée, puis soumettez vos fichiers depuis le projet."
    if pending_feedback(project):
        return "Votre travail est reçu : demandez le retour du spécialiste."
    return chat_flow.next_step(runtime, project)


def overview(repo: Path, runtime: Path, current: str | None = None) -> dict[str, Any]:
    """Small metadata only. No prompt, source text, secret, write, model or network call."""
    rows = []
    for row in chat_projects.list_projects(repo, runtime):
        try:
            identifier = validate_project_id(row["id"])
        except ValueError:
            continue
        if chat_projects.open_project(runtime, identifier) is None:
            continue
        rows.append(
            {
                "id": identifier,
                "title": chat_projects._cell(row["title"], 120),
                "state": chat_projects._cell(row["state"], 60),
                "cloud": row["cloud"],
            }
        )
    selected: dict[str, Any] | None = None
    if current:
        validate_project_id(current)
        project = chat_projects.open_project(runtime, current)
        if project is None:
            raise ValueError("Ce projet est introuvable. Choisissez un projet dans la liste.")
        selected = {"id": current, "next_step": project_hint(runtime, project)}
    return {"projects": rows, "selected": selected, "activity": activity(runtime)}
