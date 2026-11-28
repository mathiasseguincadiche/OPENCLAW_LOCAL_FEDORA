"""Read-only continuity briefing for long projects and new chat threads.

No model summaries, chat histories, external services or automatic task execution.
Only persisted operator/project metadata is read. This is never a proof of competence.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from clawfedora import chat_proposals, milestone_evidence, project_engine, project_roadmap
from clawfedora.core_config import AGENT_IDS
from clawfedora.project_common import assert_no_symlinks, read_json, sha256_file, validate_task_id
from clawfedora.project_control import is_paused
from clawfedora.project_intake import validate_input_integrity

MAX_ACTIVE = 4
MAX_READY = 4
MAX_DECISIONS = 5
MAX_OBJECTIVES = 5
MAX_CLARIFICATIONS = 5
MAX_EVIDENCE = 5
MAX_MISSION_TASKS = 6


def _display(value: object, limit: int = 120) -> str:
    """Bound displayed metadata; never turn project titles into markup or commands."""
    cleaned = re.sub(r"[\x00-\x1f\x7f|\x60<>\[\]]+", " ", str(value))
    return re.sub(r"\s+", " ", cleaned).strip()[:limit]


def _roadmap(project: Path) -> dict[str, Any]:
    path = project / project_roadmap.ROADMAP_FILE
    if not path.exists():
        return {"status": "ABSENT", "source": project_roadmap.ROADMAP_FILE}
    try:
        doc = project_roadmap.load(project)
        entries = doc["milestones"]
        counts = {
            state: sum(entry["state"] == state for entry in entries)
            for state in ("PLANNED", "IN_PROGRESS", "BLOCKED", "IMPLEMENTED")
        }
        done = {entry["id"] for entry in entries if entry["state"] == "IMPLEMENTED"}
        active = [
            entry for entry in entries if entry["state"] in {"IN_PROGRESS", "BLOCKED"}
        ][:MAX_ACTIVE]
        ready = [
            entry for entry in entries if entry["state"] == "PLANNED"
            and all(dependency in done for dependency in entry["depends_on"])
        ][:MAX_READY]

        def brief(entry: dict[str, Any]) -> dict[str, str]:
            return {
                "id": entry["id"], "title": _display(entry["title"]),
                "state": entry["state"], "verification": "NOT_VERIFIED",
            }

        return {
            "status": "AVAILABLE",
            "source": project_roadmap.ROADMAP_FILE,
            "source_sha256": sha256_file(path),
            "total": len(entries),
            "counts": counts,
            "active": [brief(item) for item in active],
            "ready": [brief(item) for item in ready],
            "truncated": {
                "active": counts["IN_PROGRESS"] + counts["BLOCKED"] > MAX_ACTIVE,
                "ready": sum(
                    item["state"] == "PLANNED"
                    and all(dep in done for dep in item["depends_on"])
                    for item in entries
                ) > MAX_READY,
            },
        }
    except (OSError, ValueError, KeyError, TypeError):
        # A corrupt or linked roadmap is not usable evidence or a next-action signal.
        return {"status": "UNVERIFIED", "source": project_roadmap.ROADMAP_FILE}


def _timestamp(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.isoformat() if parsed.tzinfo is not None else None


def decision_references(
    runtime: Path, project: Path, *, limit: int = MAX_DECISIONS, include_excerpt: bool = False,
) -> dict[str, Any]:
    source = "accepted_chat_proposals"
    try:
        notes, unverified = chat_proposals.accepted_references(
            runtime, project, limit=limit, include_excerpt=include_excerpt,
        )
        items: list[dict[str, Any]] = []
        for item in notes:
            date = _timestamp(item["accepted_at"])
            if date is None:
                unverified += 1
                continue
            items.append({**item, "title": _display(item["title"]), "accepted_at": date})
        return {"status": "AVAILABLE", "source": source, "items": items, "unverified": unverified}
    except (OSError, ValueError, KeyError, TypeError):
        return {"status": "UNVERIFIED", "source": source, "items": []}


def _evidence(project: Path, roadmap_status: str) -> dict[str, Any]:
    if roadmap_status != "AVAILABLE":
        return {"status": "NOT_VERIFIED"}
    try:
        report = milestone_evidence.report(project)
        rows = [record for row in report["milestones"] for record in row.get("recorded", [])]
        rows.sort(key=lambda row: (row["captured_at"], row["id"]), reverse=True)
        references: list[dict[str, Any]] = []
        for row in rows[:MAX_EVIDENCE]:
            date = _timestamp(row["captured_at"])
            milestone = validate_task_id(row["milestone_id"])
            identifier, commit = row["id"], row["commit"]
            kind, digest, verification = row["kind"], row["record_sha256"], row["verification"]
            if (
                date is None or not re.fullmatch(r"[0-9a-f]{32}", identifier)
                or not re.fullmatch(r"[0-9a-f]{40}", commit)
                or not milestone_evidence.HEX64.fullmatch(digest)
                or kind not in milestone_evidence.KINDS
                or verification not in ("NOT_VERIFIED", "CI_RUN_SUCCESS_ONLY", "REQUALIFY")
            ):
                raise ValueError("référence de preuve invalide")
            references.append({
                "id": identifier, "milestone_id": milestone, "kind": kind,
                "captured_at": date, "commit": commit, "record_sha256": digest,
                "source": f"{milestone_evidence.FOLDER}/{milestone}/{identifier}/record.json",
                "verification": verification,
            })
        return {
            "status": "CHECKED",
            "total": report["total"],
            "to_requalify": sum(row["to_requalify"] for row in report["milestones"]),
            "references": references,
            "scope": "RECEIPTS_ONLY_NOT_SKILL_CERTIFICATION",
        }
    except (OSError, ValueError, KeyError, TypeError):
        return {"status": "UNVERIFIED"}


def _sources(project: Path) -> str:
    if not (project / "context/ingestion/index.json").is_file():
        return "MANIFEST_ABSENT"
    try:
        return "PASS" if not validate_input_integrity(project) else "CHANGED"
    except (OSError, ValueError, KeyError, TypeError):
        return "UNVERIFIED"


_MISSION_NEXT = {
    "INTAKE_READY": "Cadrer la mission avant de proposer un plan.",
    "ANALYZED": "Relire et approuver un plan de travail.",
    "CLARIFICATION_REQUIRED": "Répondre aux clarifications en attente.",
    "PLANNED": "Préparer les assignations du plan approuvé.",
    "ASSIGNED": "Lancer les tâches assignées dans l’atelier.",
    "VALIDATING": "Consulter ou lancer la validation des livrables.",
    "REVIEW": "Consulter ou lancer la relecture indépendante.",
    "PACKAGING": "Relire le dossier et décider de la livraison.",
    "COMPLETE": "Consulter la livraison du projet.",
    "PUBLICATION_PENDING": "Reprendre pour terminer l’enregistrement de la tentative.",
    "PAUSED": "Reprendre le projet quand il est prêt à être relancé.",
    "AWAITING_FEEDBACK": "Demander le retour sur le travail soumis.",
    "AWAITING_PRACTICE": "Compléter et soumettre l’exercice guidé.",
    "READY": "Reprendre les tâches dont les dépendances sont satisfaites.",
    "COLLECTED": "Reprendre pour terminer la collecte avant l’audit.",
    "BLOCKED": "Examiner les tâches bloquées avant une nouvelle reprise.",
    "UNVERIFIED": "Vérifier les fichiers de suivi avant de reprendre.",
}
_TASK_STATES = {
    "READY": "prête",
    "AWAITING_DEPENDENCIES": "dépendances en attente",
    "AWAITING_FEEDBACK": "retour attendu",
    "AWAITING_PRACTICE": "travail de l’apprenant attendu",
    "ATTEMPTS_EXHAUSTED": "tentatives épuisées",
    "STOPPED_NO_PROGRESS": "correction inchangée",
    "COLLECTED": "sorties collectées",
}
_EXECUTION_STATES = {"ASSIGNED", "IN_PROGRESS", "VALIDATING", "REVIEW", "PACKAGING", "COMPLETE"}


def _mission_source(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("fichier de suivi invalide")
    return value, sha256(raw).hexdigest()


def recorded_objectives(repo_root: Path, project: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    if manifest.get("status") == "INTAKE_READY":
        return {"status": "NOT_RECORDED"}
    try:
        source = project_engine._artifact(repo_root, project, "analysis")
        if not source.is_file():
            return {"status": "NOT_RECORDED"}
        analysis, digest = _mission_source(source)
        date = _timestamp(analysis.get("generated_at"))
        rows = analysis.get("objectives")
        if date is None or not isinstance(rows, list):
            raise ValueError("cadrage sans date ou objectifs exploitables")
        items = []
        for position, row in enumerate(rows, 1):
            value = (row.get("text") or row.get("description")) if isinstance(row, dict) else row
            if isinstance(value, str) and (label := _display(value, 180)):
                items.append({"position": position, "objective": label})
        return {
            "status": "RECORDED", "source": source.relative_to(project).as_posix(),
            "source_sha256": digest, "recorded_at": date, "items": items[:MAX_OBJECTIVES],
            "truncated": len(items) > MAX_OBJECTIVES,
        }
    except (OSError, ValueError, KeyError, TypeError):
        return {"status": "UNVERIFIED"}


def pending_clarifications(
    repo_root: Path, project: Path, manifest: dict[str, Any], *, limit: int = MAX_CLARIFICATIONS,
) -> dict[str, Any]:
    """Read pending questions from the canonical register, never from model prose."""
    if manifest.get("status") == "INTAKE_READY":
        return {"status": "NOT_RECORDED", "items": []}
    try:
        source = project_engine._artifact(repo_root, project, "clarifications")
        if not source.is_file():
            return {"status": "NOT_RECORDED", "items": []}
        register, digest = _mission_source(source)
        date = _timestamp(register.get("generated_at"))
        rows = register.get("items")
        if date is None or not isinstance(rows, list):
            raise ValueError("registre des clarifications invalide")
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            identifier, status = row["id"], row["status"]
            if (
                not re.fullmatch(r"clarification-[0-9]{3,}", identifier) or identifier in seen
                or status not in ("OPEN", "RESOLVED")
                or not isinstance(row["question"], str) or type(row["blocking"]) is not bool
            ):
                raise ValueError("clarification invalide")
            seen.add(identifier)
            if status == "OPEN" and (question := _display(row["question"], 180)):
                items.append({
                    "id": identifier, "question": question, "blocking": row["blocking"],
                    "status": "TO_CONFIRM",
                })
        items.sort(key=lambda item: not item["blocking"])
        return {
            "status": "RECORDED", "source": source.relative_to(project).as_posix(),
            "source_sha256": digest, "recorded_at": date,
            "count": len(items), "items": items[:limit],
        }
    except (OSError, ValueError, KeyError, TypeError):
        return {"status": "UNVERIFIED", "items": []}


def _audits(repo_root: Path, project: Path) -> list[dict[str, Any]]:
    audits: list[dict[str, Any]] = []
    for kind in ("validation", "review"):
        try:
            source = project_engine._artifact(repo_root, project, kind)
            if not source.is_file():
                continue
            report, digest = _mission_source(source)
            date = _timestamp(report.get("generated_at"))
            verdict = report.get("verdict")
            if (
                date is None or verdict not in ("PASS", "FAIL")
                or report.get("reviewer") != "auditeur-qualite"
                or not isinstance(report.get("sealed_inventory"), dict)
                or not isinstance(report.get("proof_hashes", {}), dict)
            ):
                raise ValueError("verdict sans provenance exploitable")
            stale = project_engine.stale_audits(repo_root, project, (kind,))
            if sha256_file(source) != digest:
                raise ValueError("audit modifié pendant le contrôle")
            session = report.get("session_id")
            origin = "AUDITOR_SESSION" if isinstance(session, str) and session else "RECORDED_VERDICT"
            audits.append({
                "kind": kind, "status": "STALE" if stale else "CURRENT",
                "source": source.relative_to(project).as_posix(), "source_sha256": digest,
                "recorded_at": date, "verdict": verdict,
                "origin": origin,
            })
        except (OSError, ValueError, KeyError, TypeError):
            audits.append({"kind": kind, "status": "UNVERIFIED"})
    return audits


def _pending_publication(
    project: Path, journal: dict[str, Any], assignments: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    result = journal.get("result")
    if (
        journal.get("schema_version") != "1.0.0" or journal.get("project_id") != project.name
        or not isinstance(result, dict) or not isinstance(result.get("task_id"), str)
    ):
        raise ValueError("journal de publication non vérifiable")
    task_id = result["task_id"]
    assignment = assignments.get(task_id)
    attempt = result.get("attempt")
    if (
        assignment is None or type(attempt) is not int or attempt < 1
        or result.get("agent") != assignment["role"] or result.get("status") not in ("PASS", "FAIL")
        or journal.get("revision") != assignment.get("revision", 0)
        or (assignment["attempts"], assignment["status"]) not in (
            (attempt - 1, journal.get("previous_status")), (attempt, result["status"]),
        )
    ):
        raise ValueError("journal différent de la tentative attendue")
    return {"task_id": task_id, "attempt": attempt}


def _task_rows(
    plan: dict[str, Any], assignments: dict[str, Any], maximum: int,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    planned, assigned = plan.get("tasks"), assignments.get("tasks")
    if not isinstance(planned, list) or not planned or not isinstance(assigned, list):
        raise ValueError("plan ou assignations invalides")
    by_id: dict[str, dict[str, Any]] = {}
    for row in assigned:
        if (
            not isinstance(row, dict) or not isinstance(row.get("task_id"), str)
            or row["task_id"] in by_id or type(row.get("attempts")) is not int
            or row["attempts"] < 0 or row.get("status") not in (
                "PENDING", "PASS", "FAIL", "AWAITING_PRACTICE", "AWAITING_FEEDBACK",
            )
        ):
            raise ValueError("assignation invalide")
        by_id[row["task_id"]] = row
    rows: list[dict[str, Any]] = []
    matched: set[str] = set()
    for task in planned:
        if not isinstance(task, dict) or not isinstance(task.get("id"), str):
            raise ValueError("tâche du plan invalide")
        task_id = validate_task_id(task["id"])
        current = by_id.get(task_id)
        dependencies = task.get("depends_on", [])
        role = task.get("role")
        if (
            current is None or task_id in matched or role not in AGENT_IDS
            or current.get("role") != role or current.get("depends_on") != dependencies
            or not isinstance(dependencies, list)
            or any(str(dep) not in by_id for dep in dependencies)
        ):
            raise ValueError("assignations différentes du plan")
        matched.add(task_id)
        activity = project_engine.task_readiness(current, by_id, maximum)
        rows.append({
            "task_id": task_id, "role": role, "activity": activity,
            "title": _display(task.get("title", task_id)),
            "objective": _display(task.get("objective", ""), 180),
            "attempts": current["attempts"],
        })
    if matched != by_id.keys():
        raise ValueError("assignations hors plan")
    return rows, by_id


def _mission(
    runtime: Path, project: Path, repo_root: Path, manifest: dict[str, Any],
) -> dict[str, Any]:
    status = manifest.get("status")
    if not isinstance(status, str):
        return {"status": "UNVERIFIED", "next_action": "UNVERIFIED"}
    next_action = status if status in _MISSION_NEXT else "UNVERIFIED"
    if status not in _EXECUTION_STATES:
        return {"status": "NOT_ASSIGNED", "next_action": next_action}
    try:
        plan_path = project_engine._artifact(repo_root, project, "plan")
        assignments_path = project_engine._artifact(repo_root, project, "assignments")
        journal_path = project / project_engine.TASK_PROMOTION_PATH
        plan, plan_hash = _mission_source(plan_path)
        assignments, assignments_hash = _mission_source(assignments_path)
        maximum = int(project_engine._policy(repo_root)["execution"]["max_task_attempts"])
        rows, by_id = _task_rows(plan, assignments, maximum)
        counts = Counter(row["activity"] for row in rows)
        paused = is_paused(runtime, project)
        pending = None
        journal_hash = None
        if journal_path.is_file():
            journal, journal_hash = _mission_source(journal_path)
            if status != "IN_PROGRESS":
                raise ValueError("publication en dehors de la mission active")
            pending = _pending_publication(project, journal, by_id)
        if status in {"ASSIGNED", "IN_PROGRESS"}:
            if pending is not None:
                next_action = "PUBLICATION_PENDING"
            elif paused:
                next_action = "PAUSED"
            elif status == "IN_PROGRESS":
                next_action = next((
                    key for key in ("AWAITING_FEEDBACK", "AWAITING_PRACTICE", "READY")
                    if counts[key]
                ), "COLLECTED" if counts["COLLECTED"] == len(rows) else "BLOCKED")
        if (
            sha256_file(plan_path) != plan_hash or sha256_file(assignments_path) != assignments_hash
            or (sha256_file(journal_path) if journal_path.is_file() else None) != journal_hash
            or is_paused(runtime, project) != paused
            or read_json(project / "project.json") != manifest
        ):
            raise ValueError("état de la mission modifié pendant la lecture")
        priority = sorted(rows, key=lambda row: row["activity"] == "COLLECTED")
        return {
            "status": "AVAILABLE", "next_action": next_action, "task_count": len(rows),
            "counts": dict(counts), "tasks": priority[:MAX_MISSION_TASKS],
            "truncated": len(rows) > MAX_MISSION_TASKS, "pending_publication": pending,
            "project_revision": int(manifest.get("revision", 0)),
            "updated_at": _display(manifest.get("updated_at", ""), 40),
            "sources": {"plan_sha256": plan_hash, "assignments_sha256": assignments_hash},
        }
    except (OSError, ValueError, KeyError, TypeError):
        return {"status": "UNVERIFIED", "next_action": "UNVERIFIED"}


def overview(
    runtime: Path, project: Path, *, check_evidence: bool = False, repo_root: Path | None = None,
) -> dict[str, Any]:
    """Read the selected project's authoritative metadata, without changing anything.

    `check_evidence` performs receipt/hash verification and is reserved for
    explicit `!continuer`: the ordinary chat path stays bounded and inexpensive.
    """
    assert_no_symlinks(project, label="projet à reprendre")
    manifest = read_json(project / "project.json")
    if manifest.get("project_id") != project.name:
        raise ValueError("Reprise refusée : identité du projet divergente")
    roadmap = _roadmap(project)
    result: dict[str, Any] = {
        "scope": "READ_ONLY_CURRENT_PROJECT",
        "project_id": project.name,
        "project_title": _display(manifest.get("title", project.name)),
        "project_status": _display(manifest.get("status", "UNKNOWN"), 40),
        "roadmap": roadmap,
        # The ordinary chat context already contains accepted_notes; do not
        # scan and decode the proposal register a second time on each message.
        "accepted_decisions": (
            decision_references(runtime, project) if check_evidence else
            {"status": "IN_PROJECT_CONTEXT", "source": "notes_acceptees", "items": []}
        ),
        "provenance": "persisted_project_state_not_previous_chat_messages",
    }
    if check_evidence:
        result["source_integrity"] = _sources(project)
        result["milestone_evidence"] = _evidence(project, roadmap["status"])
        if repo_root is not None:
            result["mission"] = _mission(runtime, project, repo_root, manifest)
            result["objectives"] = recorded_objectives(repo_root, project, manifest)
            result["clarifications_pending"] = pending_clarifications(repo_root, project, manifest)
            result["audit_references"] = _audits(repo_root, project)
    else:
        result["milestone_evidence"] = {"status": "NOT_CHECKED_IN_CHAT"}
    return result


def render(report: dict[str, Any]) -> str:
    """Human-readable summary for an explicit command, never a model instruction."""
    roadmap = report["roadmap"]
    lines = [
        f"**Reprise de projet : {report['project_title']}** (`{report['project_id']}`)",
        f"État du projet : {report['project_status']}",
        "Sources du projet : " + report.get("source_integrity", "NON_CONTRÔLÉES"),
    ]
    mission = report.get("mission")
    if mission is not None:
        lines += ["", "**Mission courante**"]
        if mission["status"] == "AVAILABLE":
            lines.append(f"Révision {mission['project_revision']} · {mission['task_count']} tâche(s)")
            for task in mission["tasks"]:
                activity = _TASK_STATES[task["activity"]]
                lines.append(
                    f"- `{task['task_id']}` — {task['title']} · {task['role']} · {activity}"
                )
            if mission["truncated"]:
                lines.append("- Affichage partiel des tâches. Le dossier contient le plan complet.")
            if publication := mission["pending_publication"]:
                lines.append(
                    f"Publication à terminer pour `{publication['task_id']}` "
                    f"(tentative {publication['attempt']})."
                )
        lines += [_MISSION_NEXT[mission["next_action"]], ""]
    if roadmap["status"] == "AVAILABLE":
        counts = roadmap["counts"]
        lines += [
            "Feuille de route (états déclarés, non certifiés) : "
            f"{counts['IMPLEMENTED']} réalisés déclarés / {roadmap['total']} ; "
            f"{counts['IN_PROGRESS']} en cours ; {counts['BLOCKED']} bloqués.",
        ]
        for label, key in (("Jalons actifs", "active"), ("Jalons possibles ensuite", "ready")):
            rows = roadmap[key]
            lines.append(label + " :")
            lines.extend(
                f"- `{item['id']}` — {item['title']} ({item['state']}, NOT_VERIFIED)"
                for item in rows
            )
            if not rows:
                lines.append("- Aucun jalon dans cette catégorie.")
            if roadmap["truncated"][key]:
                lines.append("- Liste partielle : consulter la feuille de route complète.")
    else:
        lines.append("Feuille de route : " + roadmap["status"] + " (aucun état présumé).")
    objectives = report.get("objectives", {})
    if objectives.get("items"):
        lines += ["", "**Objectifs enregistrés dans le cadrage**"]
        lines.extend(f"- {row['objective']}" for row in objectives["items"])
        lines.append(f"Cadrage du {objectives['recorded_at'][:10]}.")
    elif objectives.get("status") == "UNVERIFIED":
        lines.append("Les objectifs du cadrage restent à vérifier.")
    clarifications = report.get("clarifications_pending", {})
    if clarifications.get("items"):
        lines += ["", "**Points à confirmer**"]
        for item in clarifications["items"]:
            blocking = " (bloquant)" if item["blocking"] else ""
            lines.append(f"- `{item['id']}` · {item['question']}{blocking}")
        if clarifications["count"] > len(clarifications["items"]):
            lines.append("D'autres points figurent dans le registre des clarifications.")
    elif clarifications.get("status") == "UNVERIFIED":
        lines.append("Le registre des clarifications reste à vérifier.")
    decisions = report["accepted_decisions"]
    if decisions["status"] == "AVAILABLE" and decisions["items"]:
        lines.append("Références de décisions acceptées (titres uniquement) :")
        lines.extend(
            f"- Proposition acceptée #{item['number']} · {item['accepted_at'][:10]} · {item['title']}"
            for item in decisions["items"]
        )
    elif decisions["status"] != "AVAILABLE":
        lines.append("Décisions acceptées : registre non vérifiable.")
    if decisions.get("unverified"):
        lines.append(f"{decisions['unverified']} référence(s) de décision restent à vérifier.")
    evidence = report.get("milestone_evidence", {})
    if evidence.get("status") == "CHECKED":
        lines.append(
            f"Reçus de jalons : {evidence['total']} ; "
            f"{evidence['to_requalify']} à requalifier."
        )
    elif evidence.get("status") == "UNVERIFIED":
        lines.append("Reçus de jalons : contrôle indisponible, aucune preuve validée.")
    for ref in evidence.get("references", []):
        lines.append(
            f"- Jalon `{ref['milestone_id']}` · {ref['captured_at'][:10]} · "
            f"`{ref['commit'][:12]}` · {ref['verification']}"
        )
    for audit in report.get("audit_references", []):
        label = "Validation" if audit["kind"] == "validation" else "Relecture"
        if audit["status"] == "CURRENT":
            lines.append(f"{label} du {audit['recorded_at'][:10]} · {audit['verdict']}.")
        elif audit["status"] == "STALE":
            lines.append(f"{label} du {audit['recorded_at'][:10]} à renouveler.")
        else:
            lines.append(f"{label} à vérifier.")
    lines.append(
        "Cette vue ne reprend pas l'historique d'un autre fil. Aucun agent, test, "
        "déploiement, validation ni jalon n'a été lancé ou modifié. "
        "Les états IMPLEMENTED restent déclaratifs ; consulter les preuves et le "
        "SHA source avant toute conclusion."
    )
    return "\n".join(lines)
