"""Drive an approved project from Open WebUI without giving the model control-plane rights.

Every command below is parsed by the bridge, not by the LLM. Long work runs in a background
thread but still goes through the same project worker, locks, cloud consent, audit and human gates
as the dashboard. Destructive revisions and final delivery need a single-use approval phrase.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path
from typing import Any

from clawfedora import chat_approvals, chat_files
from clawfedora.learning import awaiting, checkpoint_path, pending_feedback, submit
from clawfedora.learning_feedback import review_submission
from clawfedora.project_cloud import project_runner
from clawfedora.project_common import (
    assert_no_symlinks,
    read_json,
    sha256_file,
    validate_project_id,
    write_json,
)
from clawfedora.project_control import request_pause, worker_active
from clawfedora.project_engine import current_status, transition_project
from clawfedora.project_revision import impact, revise
from clawfedora.project_ui import _complete_locked
from clawfedora.project_worker import (
    review_project,
    run_project_tasks,
    worker_lock,
)

COMMANDS = (
    "lancer", "pause", "reprendre", "auditer", "relire", "livrer", "modifier",
    "pratique", "soumettre", "importer",
)
_threads: dict[str, threading.Thread] = {}
_guard = threading.Lock()


def _job_path(runtime: Path, project_id: str) -> Path:
    root = runtime / "state/chat-jobs"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{project_id}.json"


def _record(runtime: Path, project: Path, kind: str, status: str, detail: str = "") -> None:
    path = _job_path(runtime, project.name)
    write_json(
        path,
        {
            "project_id": project.name,
            "kind": kind,
            "status": status,
            "detail": detail[:1000],
        },
    )
    path.chmod(0o600)


def job_line(runtime: Path, project_id: str) -> str:
    path = _job_path(runtime, project_id)
    if not path.is_file():
        return ""
    try:
        item = read_json(path)
    except (OSError, ValueError):
        return "Traitement chat : état illisible."
    labels = {
        "run": "exécution",
        "feedback": "retour pédagogique",
        "validation": "audit de validation",
        "review": "relecture indépendante",
    }
    label = labels.get(str(item.get("kind")), str(item.get("kind", "traitement")))
    status = str(item.get("status", ""))
    detail = str(item.get("detail", "")).strip()
    if status in {"queued", "running"}:
        return f"Traitement chat : **{label} en cours**."
    if status == "failed":
        return f"Traitement chat : **{label} en échec** — {detail[:300]}"
    if status == "done":
        return f"Dernier traitement chat : {label} terminé."
    return ""


def wait_idle(timeout: float = 10.0) -> None:
    """Tests and maintenance helper; production never waits synchronously for a job."""
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with _guard:
            running = [thread for thread in _threads.values() if thread.is_alive()]
        if not running:
            return
        for thread in running:
            thread.join(timeout=0.02)
    raise TimeoutError("traitement chat encore actif")


def _start(runtime: Path, project: Path, kind: str, action: Callable[[], str]) -> str:
    if worker_active(runtime):
        raise ValueError("Une tâche ou discussion est déjà active; utilisez !etat.")
    key = project.name
    with _guard:
        if (thread := _threads.get(key)) is not None and thread.is_alive():
            raise ValueError("Un traitement chat est déjà en cours pour ce projet.")
        _record(runtime, project, kind, "queued")

        def target() -> None:
            _record(runtime, project, kind, "running")
            try:
                detail = action()
            except (OSError, ValueError, KeyError, RuntimeError) as exc:
                _record(runtime, project, kind, "failed", str(exc))
            else:
                _record(runtime, project, kind, "done", detail)

        thread = threading.Thread(target=target, name=f"clawfedora-chat-{kind}", daemon=False)
        _threads[key] = thread
        thread.start()
    return f"{kind} lancé en arrière-plan. Suivez avec `!etat`."


def _project_digest(
    runtime: Path, project: Path, *, extra: dict[str, Any] | None = None
) -> str:
    """Hash only a project under the verified workspace root, never an arbitrary path."""
    root = os.path.realpath(os.fspath(runtime / "projects"))
    supplied = os.path.normpath(os.fspath(project))
    candidate = os.path.realpath(supplied)
    # CodeQL recognizes normalization followed by a checked directory prefix as
    # a path-safety barrier. The separator prevents sibling prefix collisions.
    if not candidate.startswith(root + os.sep):
        raise ValueError("projet hors de la racine autorisée")
    if (
        os.path.commonpath((root, candidate)) != root
        or os.path.dirname(candidate) != root
        or supplied != candidate
    ):
        raise ValueError("projet hors de la racine autorisée")
    if validate_project_id(os.path.basename(candidate)) != os.path.basename(candidate):
        raise ValueError("identifiant du projet invalide")
    project = Path(candidate)
    assert_no_symlinks(project, label="projet soumis à confirmation")
    records: list[tuple[str, str]] = []
    for relative in (
        "project.json",
        "context/task_assignments.json",
        "evidence/validation_report.json",
        "evidence/review_report.json",
    ):
        path = project / relative
        if path.is_file():
            records.append((relative, sha256_file(path)))
    for root in ("deliverables", "diagrams", "evidence"):
        base = project / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file() and not path.is_symlink():
                records.append((path.relative_to(project).as_posix(), sha256_file(path)))
    raw = json.dumps({"records": records, "extra": extra or {}}, sort_keys=True).encode()
    return sha256(raw).hexdigest()


def _audit(repo: Path, runtime: Path, project: Path, kind: str) -> str:
    path = review_project(repo, runtime, project, kind)
    verdict = str(read_json(path).get("verdict", ""))
    if verdict != "PASS":
        raise ValueError(f"audit {kind} en échec; consulter {path.relative_to(project)}")
    target = "REVIEW" if kind == "validation" else "PACKAGING"
    with worker_lock(runtime, allow_gaming=True):
        transition_project(
            repo,
            project,
            target,
            actor="auditeur-qualite",
            reason=f"chat_{kind}_passed",
        )
    return f"{kind} PASS; état={target}"


def _practice(project: Path, task_id: str) -> str:
    rows = awaiting(project) + pending_feedback(project)
    if task_id:
        rows = [row for row in rows if str(row.get("task_id")) == task_id]
    if not rows:
        return "Aucune étape guidée n'attend de travail ou de retour."
    parts = []
    for row in rows[:5]:
        task = str(row.get("task_id", ""))
        parts.append(
            f"**{task}** — {row.get('status')}\n"
            f"{str(row.get('guidance', ''))[:1500]}\n"
            f"Sorties : {', '.join(sorted(dict(row.get('files', {})))) or 'voir le plan'}"
        )
    return "\n\n".join(parts)


def run_command(
    repo: Path,
    runtime: Path,
    project: Path,
    name: str,
    args: str,
    *,
    attachments: object = None,
) -> str:
    status = current_status(project)
    if name in {"lancer", "reprendre"}:
        if status not in {"ASSIGNED", "IN_PROGRESS"}:
            raise ValueError("Le projet doit être ASSIGNED ou IN_PROGRESS.")
        label = "run"
        return _start(
            runtime,
            project,
            label,
            lambda: json.dumps(
                run_project_tasks(repo, runtime, project, resume=True), ensure_ascii=False
            )[:900],
        )
    if name == "pause":
        if status not in {"ASSIGNED", "IN_PROGRESS"}:
            raise ValueError("Aucun travail exécutable à mettre en pause.")
        request_pause(runtime, project)
        return (
            "Pause demandée. La génération en cours finit proprement; "
            "aucune nouvelle tâche ne démarre."
        )
    if name == "auditer":
        if status != "VALIDATING":
            raise ValueError("L'audit de validation exige l'état VALIDATING.")
        return _start(
            runtime, project, "validation", lambda: _audit(repo, runtime, project, "validation")
        )
    if name == "relire":
        if status != "REVIEW":
            raise ValueError("La relecture finale exige l'état REVIEW.")
        return _start(runtime, project, "review", lambda: _audit(repo, runtime, project, "review"))
    if name == "pratique":
        return _practice(project, args.strip())
    if name == "importer":
        names = chat_files.import_inbox(repo, runtime, project)
        return (
            f"✅ {len(names)} fichier(s) importé(s) depuis le dossier de secours : "
            + ", ".join(names)
            + ". Lancez !analyser quand les sources sont complètes."
        )
    if name == "soumettre":
        task_id, _, explanation = args.strip().partition(" ")
        if not task_id or not explanation.strip():
            raise ValueError(
                "Usage : joignez les fichiers attendus puis "
                "!soumettre <tâche> <ce que vous avez fait>."
            )
        files = chat_files.practice_files(runtime, project, task_id, attachments)
        result = submit(
            repo,
            runtime,
            project,
            task_id,
            {
                "human_approved": True,
                "files": files,
                "explanation": explanation.strip(),
            },
        )

        def feedback() -> str:
            with worker_lock(runtime, allow_gaming=True):
                checkpoint = read_json(checkpoint_path(project, task_id))
                reviewed = review_submission(
                    repo,
                    runtime,
                    project,
                    checkpoint,
                    project_runner(repo, runtime, project),
                )
            return json.dumps(reviewed, ensure_ascii=False)[:900]

        _start(runtime, project, "feedback", feedback)
        return (
            f"✅ Soumission reçue pour **{result['task_id']}**. "
            "Le spécialiste la relit maintenant en arrière-plan; suivez avec !etat."
        )
    if name == "modifier":
        task_id, _, reason = args.strip().partition(" ")
        if not task_id or not reason.strip():
            raise ValueError("Usage : !modifier <tâche> <raison précise>.")
        affected = impact(project, task_id)
        payload = {"task_id": task_id, "reason": reason.strip(), "affected": affected}
        digest = _project_digest(runtime, project, extra=payload)
        pending = chat_approvals.issue(
            runtime,
            project.name,
            "revision",
            task_id,
            digest,
            f"réviser {task_id}; tâches affectées: {', '.join(affected)}",
            payload=payload,
        )
        return (
            f"Révision proposée pour **{task_id}**. Tâches affectées : "
            f"{', '.join(affected)}. Pour confirmer :\n\n```\n{pending.phrase()}\n```"
        )
    if name == "livrer":
        if status != "PACKAGING":
            raise ValueError("La livraison finale exige l'état PACKAGING après les deux audits PASS.")
        digest = _project_digest(runtime, project)
        pending = chat_approvals.issue(
            runtime,
            project.name,
            "livraison",
            project.name,
            digest,
            "générer le paquet final et marquer le projet COMPLETE",
        )
        return (
            "La livraison fige les livrables audités et termine le projet. Pour confirmer :\n\n"
            f"```\n{pending.phrase()}\n```"
        )
    raise ValueError(f"commande de conduite inconnue: {name}")


def apply_approval(
    repo: Path,
    runtime: Path,
    project: Path,
    action: str,
    code: str,
) -> str:
    if action not in {"revision", "livraison"}:
        raise ValueError("confirmation de conduite inconnue")
    with worker_lock(runtime, allow_gaming=True):
        outcome = chat_approvals.consume(
            runtime,
            project.name,
            action,
            code,
            lambda pending: _project_digest(runtime, project, extra=pending.payload)
            if action == "revision"
            else _project_digest(runtime, project),
        )
        if not outcome.ok or outcome.pending is None:
            reasons = {
                "unknown": "Code inconnu, expiré ou déjà utilisé.",
                "changed": "Le projet a changé depuis la confirmation : recommencez la commande.",
                "blocked": "Trop d'essais invalides : attendez l'expiration des anciens codes.",
            }
            return "⛔ " + reasons.get(outcome.reason, "Confirmation refusée.")
        if action == "revision":
            payload = outcome.pending.payload or {}
            result = revise(
                project,
                str(payload["task_id"]),
                str(payload["reason"]),
                human_approved=True,
            )
            return (
                f"✅ Révision approuvée pour **{payload['task_id']}**. "
                f"Tâches remises en travail : {', '.join(result['affected_tasks'])}."
            )
        # Final packaging happens without releasing the same lock used for the approval
        # digest: another project operation cannot change evidence between these steps.
        _complete_locked(repo, project)
        return "✅ Livraison finale approuvée. Le paquet est validé et le projet est **COMPLETE**."
