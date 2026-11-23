"""Read-only continuity briefing for long projects and new chat threads.

No model summaries, chat histories, external services or automatic task execution.
Only persisted operator/project metadata is read. This is never a proof of competence.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from clawfedora import chat_proposals, milestone_evidence, project_roadmap
from clawfedora.project_common import assert_no_symlinks, read_json, sha256_file
from clawfedora.project_intake import validate_input_integrity

MAX_ACTIVE = 4
MAX_READY = 4
MAX_DECISIONS = 5


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


def _decisions(runtime: Path, project: Path) -> dict[str, Any]:
    try:
        notes = chat_proposals.accepted_notes(runtime, project, limit=MAX_DECISIONS)
        return {
            "status": "AVAILABLE",
            "source": "accepted_chat_proposals",
            "items": [
                {"number": int(item["number"]), "title": _display(item["title"])}
                for item in notes if type(item.get("number")) is int
                and isinstance(item.get("title"), str)
            ],
        }
    except (OSError, ValueError, KeyError, TypeError):
        return {"status": "UNVERIFIED", "source": "accepted_chat_proposals", "items": []}


def _evidence(project: Path, roadmap_status: str) -> dict[str, Any]:
    if roadmap_status != "AVAILABLE":
        return {"status": "NOT_VERIFIED"}
    try:
        report = milestone_evidence.report(project)
        return {
            "status": "CHECKED",
            "total": report["total"],
            "to_requalify": sum(row["to_requalify"] for row in report["milestones"]),
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


def overview(
    runtime: Path, project: Path, *, check_evidence: bool = False,
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
        "accepted_decisions": _decisions(runtime, project),
        "provenance": "persisted_project_state_not_previous_chat_messages",
    }
    if check_evidence:
        result["source_integrity"] = _sources(project)
        result["milestone_evidence"] = _evidence(project, roadmap["status"])
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
    decisions = report["accepted_decisions"]
    if decisions["status"] == "AVAILABLE" and decisions["items"]:
        lines.append("Références de décisions acceptées (titres uniquement) :")
        lines.extend(
            f"- Proposition acceptée #{item['number']} : {item['title']}"
            for item in decisions["items"]
        )
    elif decisions["status"] != "AVAILABLE":
        lines.append("Décisions acceptées : registre non vérifiable.")
    evidence = report.get("milestone_evidence", {})
    if evidence.get("status") == "CHECKED":
        lines.append(
            f"Reçus de jalons : {evidence['total']} ; "
            f"{evidence['to_requalify']} à requalifier."
        )
    elif evidence.get("status") == "UNVERIFIED":
        lines.append("Reçus de jalons : contrôle indisponible, aucune preuve validée.")
    lines.append(
        "Cette vue ne reprend pas l'historique d'un autre fil. Aucun agent, test, "
        "déploiement, validation ni jalon n'a été lancé ou modifié. "
        "Les états IMPLEMENTED restent déclaratifs ; consulter les preuves et le "
        "SHA source avant toute conclusion."
    )
    return "\n".join(lines)
