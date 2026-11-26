"""Bounded local editorial review, before normal collection and final project audit."""
from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

from clawfedora.document_review import inspect_document

MARKER = "[revue éditoriale]"
MAX_REVISIONS = 2
MAX_BYTES = 12_000
CRITERIA = {
    "accuracy": "Exactitude des faits, commandes, versions, sources et limites.",
    "writing": "Précision, transitions, rythme, absence de remplissage et de répétitions.",
    "structure": "Besoin, hiérarchie, progression, navigation et adaptation au support.",
    "pedagogy": "Mécanisme, exemple distinct, action, contrôle et autonomie si pertinent.",
    "preservation": "Respect du brief, contenu requis, décisions, installation et exercices.",
    "security": "Absence de divulgation privée, secrets et procédures dangereuses.",
    "evidence": "Aucune preuve inventée ni qualification non démontrée.",
}


def requested(task: dict[str, Any]) -> bool:
    return any(c.startswith(MARKER) for c in task.get("acceptance_criteria", []))


def validate_task(task: dict[str, Any]) -> None:
    if not requested(task):
        return
    outputs = task["expected_outputs"]
    if (
        task["role"] != "redacteur-pedagogique"
        or task.get("learning_mode", "direct") != "direct"
        or len(outputs) != 1 or Path(outputs[0]).suffix != ".md"
        or Path(outputs[0]).parts[0] not in {"work", "deliverables"}
        or any(c.startswith("[preuve") for c in task["acceptance_criteria"])
    ):
        raise ValueError(
            "revue éditoriale : rédacteur direct, une source Markdown, critères de contenu",
        )


def audit_schema() -> dict[str, Any]:
    check = {
        "type": "object", "required": ["state", "quote", "reason", "action"],
        "additionalProperties": False,
        "properties": {
            "state": {"type": "string", "enum": ["PASS", "REVISE"]},
            "quote": {"type": "string", "minLength": 1, "maxLength": 250},
            "reason": {"type": "string", "minLength": 1, "maxLength": 350},
            "action": {"type": "string", "minLength": 1, "maxLength": 350},
        },
    }
    return {
        "type": "object", "required": ["checks"], "additionalProperties": False,
        "properties": {
            "checks": {
                "type": "object", "required": list(CRITERIA), "additionalProperties": False,
                "properties": {key: check for key in CRITERIA},
            },
        },
    }


def _sha(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _structure(content: str) -> list[str]:
    if not isinstance(content, str) or not 0 < len(content.encode("utf-8")) <= MAX_BYTES:
        raise ValueError("revue éditoriale : section Markdown limitée à 12000 octets")
    if "\x00" in content or content.startswith("@"):
        raise ValueError("revue éditoriale : contenu Markdown résolu requis")
    report = inspect_document(content, "readme")
    structural = report["structure"]
    problems = []
    if not structural["main_heading_signal"]:
        problems.append("Prévoir exactement un titre principal.")
    if structural["unclosed_code_fence_at"] is not None:
        problems.append("Fermer le bloc de code non terminé.")
    if structural["skipped_heading_levels_at"]:
        problems.append("Corriger les sauts de niveaux de titres.")
    return problems


Audit = Callable[[str, list[str]], tuple[str, dict[str, Any]]]
Revise = Callable[[str, list[dict[str, str]], list[str]], str]


def run(initial: str, audit: Audit, revise: Revise) -> tuple[str, dict[str, Any]]:
    from clawfedora.structured_response import validate_response

    content = initial
    seen: set[str] = set()
    rounds: list[dict[str, Any]] = []
    for index in range(MAX_REVISIONS + 1):
        structural = _structure(content)
        digest = _sha(content)
        if digest in seen:
            return content, {"state": "NO_PROGRESS", "rounds": rounds,
                             "candidate_sha256": digest}
        seen.add(digest)
        session, answer = audit(content, structural)
        validate_response(answer, audit_schema())
        checks = answer["checks"]
        failures: list[dict[str, str]] = []
        for key, item in checks.items():
            if item["quote"] not in content:
                raise ValueError("revue éditoriale : extrait absent de la version auditée")
            if item["state"] == "REVISE":
                failures.append({"criterion": key, **item})
        rounds.append({
            "round": index + 1, "reviewer_session": session, "candidate_sha256": digest,
            "checks": {key: item["state"] for key, item in checks.items()},
            "structure_issues": structural,
        })
        if not failures and not structural:
            return content, {"state": "MODEL_REVIEW_PASSED", "rounds": rounds,
                             "candidate_sha256": digest}
        if index == MAX_REVISIONS:
            break
        content = revise(content, failures, structural)
    return content, {"state": "REVISION_LIMIT", "rounds": rounds,
                     "candidate_sha256": _sha(content)}
