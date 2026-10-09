"""Creating and framing a project from the chat: the same steps and gates as the atelier.

``!creer`` makes the project from the user's previous message, ``!analyser`` and ``!planifier``
ask the chief role for a draft in the background, ``!valider`` shows the draft and the phrase that
approves it, ``!questions`` and ``!repondre`` handle the clarifications. Every state change goes
through ``project_ui`` (so through the engine's gates); what the chat adds is only who may trigger
it: commands come from the user's last message, and an approval needs the single-use phrase of
``chat_approvals``. A model draft never approves itself.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from clawfedora import chat_approvals, chat_projects, project_cloud, project_ui
from clawfedora.chat_projects import BUSY, _cell, bridge_reply, open_project
from clawfedora.chat_proposals import confined
from clawfedora.project_common import read_json, validate_project_id, write_json
from clawfedora.project_control import worker_active
from clawfedora.project_worker import worker_lock

FLOW_COMMANDS = ("creer", "analyser", "planifier", "valider", "questions", "repondre")
JOBS = "state/chat-jobs"
MAX_TITLE = 200
MAX_BRIEF_BYTES = 12000
MAX_ANSWER = 1500
PREVIEW = 600
KINDS = {"analysis": "analyse", "plan": "plan"}
NEXT_STEP = {
    "INTAKE_READY": "`!analyser` demande une analyse au rôle chef d'opérations.",
    "CLARIFICATION_REQUIRED": "`!questions` liste les précisions attendues, `!repondre` y répond.",
    "ANALYZED": "`!planifier` demande un plan au rôle chef d'opérations.",
    "PLANNED": "Plan approuvé : le travail se lance dans l'atelier (le chat le pilotera plus tard).",
    "ASSIGNED": "Plan approuvé : le travail se lance dans l'atelier (le chat le pilotera plus tard).",
}


@dataclass(frozen=True)
class Flow:
    repo_root: Path
    runtime: Path
    current: str | None
    brief: str | None
    runner: Callable[..., dict[str, Any]]


# -- background drafts ------------------------------------------------------------------
_threads: dict[str, threading.Thread] = {}
_guard = threading.Lock()


def _job_path(runtime: Path, project_id: str) -> Path:
    directory = runtime / JOBS
    for part in (runtime / "state", directory):
        if part.is_symlink():
            raise ValueError("dossier de tâches lié interdit")
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{validate_project_id(project_id)}.json"


def _record(runtime: Path, project_id: str, **fields: Any) -> None:
    write_json(_job_path(runtime, project_id), fields)


def job_line(runtime: Path, project_id: str) -> str | None:
    """One line about the last background draft of the project, for ``!etat``."""
    try:
        path = _job_path(runtime, project_id)
        value = read_json(path) if path.is_file() else None
    except (OSError, ValueError):
        return None
    if not value:
        return None
    what = {"analysis": "analyse", "plan": "plan"}.get(str(value.get("kind")), "brouillon")
    status = str(value.get("status"))
    with _guard:
        alive = project_id in _threads and _threads[project_id].is_alive()
    if status == "running":
        if not alive:
            return f"Le brouillon de {what} a été interrompu (service redémarré) : relancez-le."
        return f"Un brouillon de {what} est en cours de rédaction : `!etat` pour suivre."
    if status == "done":
        return f"Brouillon de {what} prêt : `!valider` pour le relire et l'approuver."
    if status == "paused":
        return f"Le brouillon de {what} est en pause : {_cell(value.get('message', ''), 300)}"
    return f"Le brouillon de {what} a échoué : {_cell(value.get('message', ''), 300)}"


def wait_idle(timeout: float = 10.0) -> None:
    """Wait for background drafts (used by tests and by a clean shutdown)."""
    deadline = time.monotonic() + timeout
    with _guard:
        threads = list(_threads.values())
    for thread in threads:
        thread.join(max(0.0, deadline - time.monotonic()))


def _draft_job(flow: Flow, project: Path, kind: str) -> None:
    runtime = flow.runtime
    started = time.time()
    try:
        runner = project_cloud.project_runner(
            flow.repo_root, runtime, project, base=flow.runner
        )
        project_ui.propose(flow.repo_root, runtime, project, kind, runner=runner)
        _record(runtime, project.name, kind=kind, status="done", started=started, ended=time.time())
    except project_cloud.CloudPause as exc:
        _record(runtime, project.name, kind=kind, status="paused", message=str(exc)[:300],
                started=started, ended=time.time())
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        _record(runtime, project.name, kind=kind, status="failed", message=str(exc)[:300],
                started=started, ended=time.time())


def _start_draft(flow: Flow, project: Path, kind: str) -> str:
    if worker_active(flow.runtime):
        return BUSY
    if (flow.runtime / "state/gaming-mode").exists():
        return "Le mode jeux est actif : reprenez le profil quotidien avant une génération."
    with _guard:
        if any(t.is_alive() for t in _threads.values()):
            return "Un brouillon est déjà en cours de rédaction : `!etat` pour suivre."
        _record(flow.runtime, project.name, kind=kind, status="running", started=time.time())
        thread = threading.Thread(target=_draft_job, args=(flow, project, kind), daemon=True)
        _threads[project.name] = thread
        thread.start()
    what = "l'analyse" if kind == "analysis" else "le plan"
    return (
        f"Rédaction de {what} lancée en arrière-plan : cela prend quelques minutes. `!etat` "
        "donne l'avancement ; quand c'est prêt, `!valider` montre le brouillon et la phrase "
        "qui l'approuve. Pendant ce temps, les questions au modèle répondent « occupé »."
    )


# -- drafts ------------------------------------------------------------------------------
def pending_draft(runtime: Path, project: Path) -> dict[str, Any] | None:
    try:
        path = confined(runtime, project) / "context/ui_draft.json"
        value = read_json(path) if path.is_file() and not path.is_symlink() else None
    except (OSError, ValueError):
        return None
    if (
        value is None
        or value.get("kind") not in KINDS
        or not isinstance(value.get("proposal"), dict)
        or value.get("approved") is not False
    ):
        return None
    return value


def digest(kind: str, proposal: dict[str, Any]) -> str:
    text = json.dumps({"kind": kind, "proposal": proposal}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode()).hexdigest()


def _draft_digest(runtime: Path, project: Path, kind: str) -> str | None:
    value = pending_draft(runtime, project)
    return digest(kind, value["proposal"]) if value and value["kind"] == kind else None


def _items(values: Any, limit: int = 6) -> list[str]:
    rows = []
    for value in values if isinstance(values, list) else []:
        if isinstance(value, dict):
            value = value.get("question") or value.get("description") or value.get("text") or ""
        text = _cell(value, 180)
        if text:
            rows.append(text)
    shown = [f"- {t}" for t in rows[:limit]]
    if len(rows) > limit:
        shown.append(f"- … et {len(rows) - limit} autre(s)")
    return shown


def render_analysis(proposal: dict[str, Any]) -> str:
    lines = [f"**Résumé** : {_cell(proposal.get('summary', ''), 500)}"]
    for key, label in (
        ("objectives", "Objectifs"),
        ("constraints", "Contraintes"),
        ("deliverables", "Livrables"),
        ("ambiguities", "Ambiguïtés"),
        ("missing_information", "Informations manquantes"),
        ("risks", "Risques"),
        ("decisions_required", "Décisions à prendre"),
    ):
        items = _items(proposal.get(key))
        if items:
            lines += ["", f"**{label}**", *items]
    coverage = proposal.get("source_coverage")
    if isinstance(coverage, list) and coverage:
        lines += ["", "**Lecture des documents (déclarée par le modèle, à vérifier)**"]
        lines += [
            f"- `{_cell(c.get('document_id', ''), 40)}` : {_cell(c.get('status', ''), 20)} "
            f"({_cell(c.get('method', ''), 30)})"
            for c in coverage[:12]
            if isinstance(c, dict)
        ]
    return "\n".join(lines)


def render_plan(proposal: dict[str, Any]) -> str:
    tasks = proposal.get("tasks")
    rows = ["| Tâche | Rôle | Titre | Sorties attendues | Dépend de |", "|---|---|---|---|---|"]
    for task in tasks[:6] if isinstance(tasks, list) else []:
        if not isinstance(task, dict):
            continue
        outputs = ", ".join(_cell(o, 60) for o in task.get("expected_outputs") or [])
        after = ", ".join(_cell(d, 30) for d in task.get("depends_on") or []) or "—"
        rows.append(
            f"| `{_cell(task.get('id', ''), 40)}` | {_cell(task.get('role', ''), 30)} | "
            f"{_cell(task.get('title', ''), 60)} | {outputs} | {after} |"
        )
    criteria = []
    for task in tasks[:6] if isinstance(tasks, list) else []:
        if isinstance(task, dict):
            for item in (task.get("acceptance_criteria") or [])[:3]:
                criteria.append(f"- `{_cell(task.get('id', ''), 40)}` : {_cell(item, 160)}")
    return "\n".join([*rows, "", "**Critères de vérification**", *criteria])


# -- commands ----------------------------------------------------------------------------
def _project(flow: Flow) -> Path | None:
    return open_project(flow.runtime, flow.current) if flow.current else None


def _no_project() -> str:
    return bridge_reply(None, "Aucun projet sélectionné. Faites `!projets`, puis `!projet <id>`.")


def _payload_digest(payload: dict[str, Any] | None) -> str | None:
    if not payload or not isinstance(payload.get("title"), str):
        return None
    text = json.dumps(
        {"title": payload["title"], "brief": payload.get("brief")}, sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(text.encode()).hexdigest()


def _create(flow: Flow, title: str) -> str:
    title = " ".join(title.split())
    if not title or len(title) > MAX_TITLE:
        return bridge_reply(
            flow.current,
            "Donnez un titre : `!creer <titre>`. La demande est votre **message précédent** "
            "(écrivez-la d'abord, avec le contexte, le but et les contraintes).",
        )
    brief = (flow.brief or "").strip()
    if not brief:
        return bridge_reply(
            flow.current,
            "Aucune demande trouvée avant la commande. Écrivez d'abord la demande du projet "
            "dans un message, puis `!creer <titre>`.",
        )
    if len(brief.encode()) > MAX_BRIEF_BYTES:
        return bridge_reply(
            flow.current,
            f"La demande dépasse {MAX_BRIEF_BYTES // 1000} Ko : résumez-la, ou importez les "
            "documents dans l'atelier.",
        )
    payload = {"title": title, "brief": brief}
    pending = chat_approvals.issue(
        flow.runtime, chat_approvals.GLOBAL, "creation", "new", _payload_digest(payload) or "",
        f"créer « {title} »", payload=payload,
    )
    preview = brief[:PREVIEW] + ("…" if len(brief) > PREVIEW else "")
    return bridge_reply(
        flow.current,
        f"**Créer le projet « {_cell(title, 120)} »** à partir de votre message précédent "
        f"({len(brief.encode()) // 1000 + 1} Ko) :\n\n> {preview.replace(chr(10), chr(10) + '> ')}"
        "\n\nPour confirmer, tapez exactement, comme message à part (valable 15 minutes, une "
        f"seule fois) :\n\n```\n{pending.phrase()}\n```",
    )


def _validate(flow: Flow) -> str:
    project = _project(flow)
    if project is None or flow.current is None:
        return _no_project()
    value = pending_draft(flow.runtime, project)
    if value is None:
        return bridge_reply(
            flow.current, "Aucun brouillon à valider. `!analyser` ou `!planifier` en demande un."
        )
    kind = str(value["kind"])
    body = (
        render_analysis(value["proposal"]) if kind == "analysis" else render_plan(value["proposal"])
    )
    pending = chat_approvals.issue(
        flow.runtime, flow.current, KINDS[kind], kind, digest(kind, value["proposal"]),
        f"brouillon de {KINDS[kind]}",
    )
    title = "Analyse proposée" if kind == "analysis" else "Plan proposé"
    return bridge_reply(
        flow.current,
        f"**{title}** (rédigé par le modèle, à relire : il peut se tromper).\n\n{body}\n\n"
        "Pour **approuver exactement ce brouillon**, tapez comme message à part (valable "
        f"15 minutes, une seule fois) :\n\n```\n{pending.phrase()}\n```\n\n"
        "Pour le refaire, relancez `!analyser` ou `!planifier`.",
    )


def _clarifications(runtime: Path, project: Path) -> list[dict[str, Any]]:
    try:
        path = confined(runtime, project) / "context/clarifications.json"
        items = read_json(path).get("items", []) if path.is_file() else []
    except (OSError, ValueError):
        return []
    return [i for i in items if isinstance(i, dict)] if isinstance(items, list) else []


def _questions(flow: Flow) -> str:
    project = _project(flow)
    if project is None:
        return _no_project()
    items = _clarifications(flow.runtime, project)
    if not items:
        return bridge_reply(flow.current, "Aucune question de précision pour ce projet.")
    rows = ["| N° | Question | Bloquante | État |", "|---|---|---|---|"]
    for index, item in enumerate(items[:30], 1):
        resolved = item.get("status") == "RESOLVED"
        state = "✅ " + _cell(item.get("answer", ""), 60) if resolved else "⏳"
        rows.append(
            f"| {index} | {_cell(item.get('question', ''), 220)} | "
            f"{'oui' if item.get('blocking') else 'non'} | {state} |"
        )
    return bridge_reply(
        flow.current, "\n".join(rows) + "\n\nRépondez avec `!repondre <n°> <votre réponse>`."
    )


def _answer(flow: Flow, args: str) -> str:
    project = _project(flow)
    if project is None or flow.current is None:
        return _no_project()
    word, _, text = args.strip().partition(" ")
    items = _clarifications(flow.runtime, project)
    chosen = None
    if word.isdecimal() and 1 <= int(word) <= len(items):
        chosen = items[int(word) - 1]
    else:
        chosen = next((i for i in items if i.get("id") == word), None)
    text = text.strip()
    if chosen is None or not text or len(text) > MAX_ANSWER:
        return bridge_reply(
            flow.current,
            f"Usage : `!repondre <n°> <réponse>` ({MAX_ANSWER} caractères au plus). "
            "`!questions` donne les numéros.",
        )
    try:
        project_ui.clarify(flow.repo_root, flow.runtime, project, str(chosen["id"]), text)
    except ValueError as exc:
        return bridge_reply(flow.current, BUSY if "worker" in str(exc) else f"Impossible : {exc}.")
    after = project_ui_status(project)
    hint = NEXT_STEP.get(after, "")
    return bridge_reply(flow.current, f"Réponse enregistrée pour la précision {word}. {hint}")


def project_ui_status(project: Path) -> str:
    from clawfedora.project_engine import current_status

    return current_status(project)


def next_step(runtime: Path, project: Path) -> str:
    status = project_ui_status(project)
    draft = pending_draft(runtime, project)
    if draft is not None and (
        (draft["kind"] == "analysis" and status in {"INTAKE_READY", "CLARIFICATION_REQUIRED"})
        or (draft["kind"] == "plan" and status == "ANALYZED")
        or (draft["kind"] == "analysis" and status == "ANALYZED")
    ):
        return "Un brouillon attend votre relecture : `!valider`."
    return NEXT_STEP.get(status, "")


def run_command(flow: Flow, name: str, args: str) -> str:
    if name == "creer":
        return _create(flow, args)
    project = _project(flow)
    if project is None:
        return _no_project()
    if name == "valider":
        return _validate(flow)
    if name == "questions":
        return _questions(flow)
    if name == "repondre":
        return _answer(flow, args)
    kind = "analysis" if name == "analyser" else "plan"
    status = project_ui_status(project)
    allowed = (
        {"INTAKE_READY", "ANALYZED", "CLARIFICATION_REQUIRED"} if kind == "analysis" else {"ANALYZED"}
    )
    if status not in allowed:
        return bridge_reply(
            flow.current,
            f"Impossible maintenant : le projet est « {chat_projects.STATES.get(status, status)} ». "
            + NEXT_STEP.get(status, ""),
        )
    return bridge_reply(flow.current, _start_draft(flow, project, kind))


# -- approvals ---------------------------------------------------------------------------
REFUSALS = {
    "unknown": "Code inconnu, expiré ou déjà utilisé. Refaites la commande pour en obtenir un.",
    "changed": "Le contenu a changé depuis la génération du code : rien n'est approuvé. "
    "Refaites la commande.",
    "blocked": "Trop d'essais invalides : les codes en attente sont annulés. Attendez quelques "
    "minutes puis refaites la commande.",
}


def apply_approval(
    repo_root: Path, runtime: Path, action: str, code: str, current: str | None
) -> str:
    """The user typed an approval phrase (creation, analysis or plan) as the last message."""
    project = open_project(runtime, current) if current else None
    if action != "creation" and (project is None or current is None):
        return bridge_reply(
            None,
            "Aucun projet sélectionné : cette confirmation ne correspond à rien. "
            "Faites `!projet <id>`, puis `!valider`.",
        )
    kind = next((k for k, a in KINDS.items() if a == action), "")
    scope = chat_approvals.GLOBAL if action == "creation" else str(current)
    try:
        # The lock comes first: when busy, the code is not spent and can be typed again.
        with worker_lock(runtime, allow_gaming=True):
            if action == "creation":
                outcome = chat_approvals.consume(
                    runtime, scope, action, code, lambda p: _payload_digest(p.payload)
                )
            else:
                assert project is not None
                outcome = chat_approvals.consume(
                    runtime, scope, action, code, lambda p: _draft_digest(runtime, project, kind)
                )
            if outcome.ok and outcome.pending is not None:
                if action == "creation":
                    return _do_create(repo_root, runtime, outcome.pending)
                assert project is not None
                return _do_approve(repo_root, runtime, project, kind)
    except (OSError, ValueError, KeyError) as exc:
        return bridge_reply(current, BUSY if "worker" in str(exc) else f"Impossible : {exc}.")
    return bridge_reply(current, "⛔ " + REFUSALS.get(outcome.reason, "Confirmation refusée."))


def _do_create(repo_root: Path, runtime: Path, pending: chat_approvals.Pending) -> str:
    payload = pending.payload or {}
    project = project_ui.create_from_browser(
        repo_root, runtime, {"title": payload["title"], "brief": payload["brief"]}, lock=False
    )
    return bridge_reply(
        project.name,
        f"✅ Projet **{_cell(payload['title'], 120)}** créé (`{project.name}`) et sélectionné. "
        "Les sources sont la demande que vous avez écrite ; aucun accord cloud n'est donné "
        "(le projet reste local). " + NEXT_STEP["INTAKE_READY"],
    )


def _do_approve(repo_root: Path, runtime: Path, project: Path, kind: str) -> str:
    value = pending_draft(runtime, project)
    if value is None or value["kind"] != kind:
        raise ValueError("le brouillon n'existe plus")
    project_ui.approve(repo_root, runtime, project, kind, value["proposal"], lock=False)
    what = "Analyse" if kind == "analysis" else "Plan"
    return bridge_reply(
        project.name,
        f"✅ {what} approuvé(e). {next_step(runtime, project)} Rien n'est encore exécuté.",
    )
