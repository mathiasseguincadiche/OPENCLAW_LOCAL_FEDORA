"""Deterministic document-review preparation, not a semantic or visual verdict.

V26's four reader situations are questions to examine, not scores an LLM can
declare from Markdown syntax. Never assign a PASS without real reader evidence.
"""
from __future__ import annotations

import re
from typing import Any

KINDS: dict[str, dict[str, tuple[str, ...]]] = {
    "readme": {
        "first_steps": ("démarr", "demarr", "commencer", "installation", "quick start"),
        "architecture": ("architecture", "fonctionnement", "composant"),
        "evidence": ("preuve", "test", "vérif", "verif"),
        "limitations": ("limite", "risque", "statut", "état", "etat"),
    },
    "procedure": {
        "prerequisites": ("prérequ", "prerequ", "environnement", "préparer", "preparer"),
        "actions": ("procédure", "procedure", "étape", "etape", "intervention"),
        "verification": ("vérif", "verif", "résultat", "resultat", "contrôle", "controle"),
        "failure": ("dépann", "depann", "erreur", "incident", "échec", "echec"),
        "rollback": ("retour arrière", "rollback", "restaur", "reprise"),
    },
    "course": {
        "mechanism": ("mécanisme", "mecanisme", "comprendre", "concept", "fonctionne"),
        "example": ("exemple", "démonstration", "demonstration"),
        "practice": ("pratiq", "exercice", "essai"),
        "verification": ("vérif", "verif", "contrôle", "controle", "résultat", "resultat"),
        "diagnosis": ("dépann", "depann", "erreur", "diagnostic"),
        "transfer": ("transpos", "réutil", "reutil", "approfond", "variante"),
    },
}
READERS = (
    ("discovery", "Découvrir le projet et trouver le point d'entrée sans défilement"),
    ("learning", "Suivre une procédure avec prérequis et signes de réussite"),
    ("lookup", "Retrouver rapidement un port, une décision ou une restauration"),
    ("expert", "Contrôler un choix, une limite et la preuve correspondante"),
)


def inspect_document(content: str, kind: str) -> dict[str, Any]:
    if not isinstance(kind, str) or kind not in KINDS:
        raise ValueError("type de document inconnu")
    if not isinstance(content, str) or not 0 < len(content.encode("utf-8")) <= 12_000:
        raise ValueError("document texte limité à 12000 octets")
    headings = []
    inside_fence = False
    for line_number, raw in enumerate(content.splitlines(), 1):
        if re.match(r"^\s*\x60{3,}", raw):
            inside_fence = not inside_fence
            continue
        if inside_fence:
            continue
        match = re.match(r"^(#{1,6})[ \t]+(.+?)\s*#*\s*$", raw)
        if match:
            headings.append({"line": line_number, "level": len(match.group(1)),
                             "title": match.group(2)[:140]})
    levels = [int(item["level"]) for item in headings]
    skipped = [item["line"] for prev, item in zip(levels, headings[1:], strict=False)
               if int(item["level"]) > prev + 1]
    indicators: list[dict[str, Any]] = []
    for label, variants in KINDS[kind].items():
        found = [item["line"] for item in headings if any(
            token in str(item["title"]).casefold() for token in variants
        )]
        indicators.append({
            "id": label, "explicit_heading_lines": found,
            "state": "SIGNAL_FOUND" if found else "NOT_LOCATED_IN_HEADINGS",
        })
    return {
        "assessment": "STRUCTURAL_REVIEW_ONLY_NO_EDITORIAL_PASS",
        "document_kind": kind,
        "headings": headings[:80],
        "structure": {
            "main_heading_count": levels.count(1),
            "skipped_heading_levels_at": skipped,
            "main_heading_signal": levels.count(1) == 1,
        },
        "indicators": indicators,
        "reader_situations": [
            {"id": key, "question": question, "verdict": "NOT_EVALUATED"}
            for key, question in READERS
        ],
        "manual_review": [
            "Exactitude du contenu à comparer aux sources et au commit",
            "Parcours réel des lecteurs, pas seulement présence de titres",
            "Visuel natif GitHub/Notion en clair, sombre et mobile",
            "Préservation des sections existantes et des exercices personnels",
        ],
        "limitations": [
            "Un titre trouvé ne prouve pas le contenu ni la pédagogie",
            "Une rubrique absente peut être volontaire pour un document court",
            "Aucune navigation, source externe ou action Fedora vérifiée",
        ],
    }
