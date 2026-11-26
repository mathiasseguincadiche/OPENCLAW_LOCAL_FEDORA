"""Deterministic document-review preparation, not a semantic or visual verdict.

V26's four reader situations are questions to examine, not scores an LLM can
declare from Markdown syntax. Never assign a PASS without real reader evidence.
"""
from __future__ import annotations

import hashlib
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
# Profiles complement, rather than replace, the original three kinds.
KINDS.update({
    "wiki_home": {"purpose": ("objectif", "présentation", "projet"),
                  "navigation": ("explorer", "navigation", "commencer"),
                  "progress": ("parcours", "progression", "suivi"),
                  "references": ("références", "architecture", "état")},
    "architecture": {"context": ("contexte", "besoin"), "components": ("architecture", "composants"),
                     "decisions": ("décision", "compromis", "alternative"),
                     "validation": ("contrôle", "preuve", "validation", "limite")},
    "proof": {"scope": ("cible", "périmètre", "version"), "method": ("méthode", "contrôle"),
              "observed": ("observ", "résultat"), "limits": ("limite", "risque")},
    "journal": {"context": ("séance", "contexte", "cible"), "observed": ("observ", "résultat"),
                "next": ("suite", "prochaine", "blocage"), "help": ("aide", "assistance")},
    "portfolio": {"need": ("besoin", "projet"),
                  "contribution": ("rôle", "contribution", "réalisation"),
                  "evidence": ("preuve", "test"), "limits": ("limite", "état")},
    "release": {"changes": ("changement", "nouveauté"), "validation": ("test", "validation"),
                "rollback": ("rollback", "retour", "migration")},
    "issue": {"problem": ("problème", "symptôme", "contexte"), "reproduce": ("reprodu", "étape"),
              "expected": ("attendu", "critère"), "observed": ("observ", "preuve")},
    "pull_request": {"scope": ("périmètre", "changement", "objectif"), "tests": ("test", "contrôle"),
                     "limits": ("risque", "limite", "rollback")},
})
RUBRIC = (
    ("accuracy", 20, "Exactitude technique : sources, version et cible"),
    ("writing", 15, "Qualité rédactionnelle : précision, clarté, sobriété"),
    ("information", 15, "Architecture de l’information : hiérarchie et absence de doublons"),
    ("learning", 10, "Pédagogie : mécanisme, pratique, signes de réussite"),
    ("graphics", 10, "Qualité graphique : source, rendu et lisibilité"),
    ("navigation", 10, "Ergonomie : parcours de lecture, mobile et thèmes"),
    ("cross_support", 10, "Cohérence des supports : révisions et séparation public/privé"),
    ("evidence", 5, "Sources et preuves : date, portée, limites"),
    ("maintenance", 5, "Maintenabilité : propriétaire, révision, impact"),
)
BLOCKERS = (
    "technical_error", "fabricated_evidence", "private_disclosure",
    "required_content_removed", "unsafe_procedure", "missing_required_review",
)

READERS = (
    ("discovery", "Découvrir le projet et trouver le point d'entrée sans défilement"),
    ("learning", "Suivre une procédure avec prérequis et signes de réussite"),
    ("lookup", "Retrouver rapidement un port, une décision ou une restauration"),
    ("expert", "Contrôler un choix, une limite et la preuve correspondante"),
)


def inspect_document(content: str, kind: str, support: str = "markdown") -> dict[str, Any]:
    if support not in ("markdown", "github", "notion", "document"):
        raise ValueError("support documentaire inconnu")
    if not isinstance(kind, str) or kind not in KINDS:
        raise ValueError("type de document inconnu")
    if not isinstance(content, str) or not 0 < len(content.encode("utf-8")) <= 12_000:
        raise ValueError("document texte limité à 12000 octets")
    headings = []
    fence: tuple[str, int, int] | None = None
    for line_number, raw in enumerate(content.splitlines(), 1):
        marker = re.match(r"^ {0,3}(\x60{3,}|~{3,})(.*)$", raw)
        if fence is not None:
            if marker:
                run, suffix = marker.groups()
                if run[0] == fence[0] and len(run) >= fence[1] and not suffix.strip():
                    fence = None
            continue
        if marker:
            run, _suffix = marker.groups()
            fence = (run[0], len(run), line_number)
            continue
        match = re.match(r"^(#{1,6})[ \t]+(.+?)\s*#*\s*$", raw)
        if match:
            headings.append({"line": line_number, "level": len(match.group(1)),
                             "title": match.group(2)[:140]})
    levels = [int(item["level"]) for item in headings]
    skipped = [item["line"] for prev, item in zip(levels, headings[1:], strict=False)
               if int(item["level"]) > prev + 1]
    seen: set[str] = set()
    repeated: list[int] = []
    for item in headings:
        normalized = " ".join(str(item["title"]).casefold().split())
        if normalized in seen:
            repeated.append(int(item["line"]))
        seen.add(normalized)
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
        "support": support,
        "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "editorial_rubric": [{"id": key, "weight": weight, "criterion": label,
                              "verdict": "NOT_EVALUATED"} for key, weight, label in RUBRIC],
        "blocking_criteria": [{"id": key, "verdict": "NOT_EVALUATED"} for key in BLOCKERS],
        "editorial_score": None,
        "premium_review": [
            {"id": "opening", "question": "Le besoin et le lectorat sont-ils explicites ?"},
            {"id": "explanation", "question": "Mécanisme, exemple et limites sont-ils reliés ?"},
            {"id": "voice",
             "question": "Phrases naturelles, transitions et rythme sans remplissage ?"},
            {"id": "composition", "question": "Visuels utiles et hiérarchie propres au projet ?"},
            {"id": "native", "question": "Composants adaptés au support, vérifiés en contexte ?"},
            {"id": "preservation", "question": "Contenu, liens, exercices et preuves préservés ?"},
        ],
        "support_review": {
            "markdown": ["Hiérarchie, liens, code et sources"],
            "github": ["README et navigation réelle", "SVG et Draw.io, clair/sombre/mobile",
                       "Preuves publiques expurgées et liens versionnés"],
            "notion": ["Blocs, mentions, médias et bases à préserver",
                       "Rendu natif et empilement mobile", "Installation et suivi personnel intacts"],
            "document": ["Source éditable, pagination, figures et export natif"],
        }[support],
        "headings": headings[:80],
        "structure": {
            "main_heading_count": levels.count(1),
            "skipped_heading_levels_at": skipped,
            "main_heading_signal": levels.count(1) == 1,
            "repeated_heading_lines": repeated,
            "unclosed_code_fence_at": fence[2] if fence else None,
        },
        "indicators": indicators,
        "reader_situations": [
            {"id": key, "question": question, "verdict": "NOT_EVALUATED"}
            for key, question in READERS
        ],
        "manual_review": [
            "Exactitude du contenu à comparer aux sources et au commit",
            "Parcours réel des lecteurs, pas seulement présence de titres",
            "Titres répétés : vérifier leur utilité et la navigation, sans les interdire",
            "Commandes : cible, droits, installation, résultat attendu et retour arrière",
            "Visuel natif GitHub/Notion en clair, sombre et mobile",
            "Préservation des sections existantes et des exercices personnels",
        ],
        "limitations": [
            "Un titre trouvé ne prouve pas le contenu ni la pédagogie",
            "Une rubrique absente peut être volontaire pour un document court",
            "Aucune navigation, source externe ou action Fedora vérifiée",
        ],
    }
