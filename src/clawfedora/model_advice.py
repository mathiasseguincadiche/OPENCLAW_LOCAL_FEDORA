"""Deterministic hybrid-model guidance, not an automatic router or data classifier.

Never reads a conversation, source file, secret, cloud token, or network service.
An agent's requested tool scope and project authorizations are unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Advice:
    route: str
    reason: str
    limitation: str


SUGGESTIONS: dict[str, Advice] = {
    "simple": Advice(
        "Qwen local",
        "Expliquer Linux, lire un petit YAML ou préparer une procédure courte ne nécessite "
        "généralement pas une requête API payante.",
        "Si les résultats sont insuffisants, reformule ou demande une analyse plus structurée.",
    ),
    "confidentiel": Advice(
        "Qwen local uniquement",
        "Configuration privée, noms internes, journaux sensibles et contenus professionnels "
        "ne doivent pas partir vers un modèle distant simplement pour gagner en qualité.",
        "Le filtre de secrets n'identifie pas toutes les informations confidentielles.",
    ),
    "architecture": Advice(
        "DeepSeek cloud à envisager",
        "Un ADR complexe ou des compromis d'infrastructure multi-contrainte peuvent bénéficier "
        "d'un contexte et d'un raisonnement cloud plus importants.",
        "N'utiliser cette route que pour des sources autorisées, avec consentement explicite et "
        "budget disponible ; les gains ne sont pas encore mesurés.",
    ),
    "iac": Advice(
        "DeepSeek cloud à envisager",
        "La cohérence de plusieurs modules Terraform et playbooks Ansible peut demander "
        "davantage de raisonnement que la relecture d'un seul fichier.",
        "Aucun modèle ne remplace terraform validate, ansible-lint, un plan vérifié ou les "
        "preuves de déploiement ; ne pas exporter des variables sensibles.",
    ),
    "ci": Advice(
        "Qwen local pour un incident simple ; DeepSeek pour un incident complexe et assaini",
        "Un journal CI difficile et plusieurs dépendances peuvent justifier une analyse "
        "approfondie par DeepSeek.",
        "Les secrets et jetons doivent être exclus et le statut réel doit venir du bon run "
        "et du bon commit, pas d'une affirmation du modèle.",
    ),
    "documents": Advice(
        "Qwen pour un document court et privé ; DeepSeek pour une synthèse publique longue",
        "Un gros dossier d'architecture ou un runbook multi-section peut bénéficier "
        "du contexte cloud.",
        "Une sortie longue n'est pas nécessairement exacte : vérifier références, fichiers "
        "et rendus ; un dossier confidentiel reste local.",
    ),
}

ALIASES = {
    "prive": "confidentiel",
    "private": "confidentiel",
    "secret": "confidentiel",
    "linux": "simple",
    "debutant": "simple",
    "terraform": "iac",
    "ansible": "iac",
    "pipeline": "ci",
    "audit": "ci",
    "long": "documents",
}

CATEGORIES = ("simple", "confidentiel", "architecture", "iac", "ci", "documents")


def advise(category: str = "") -> str:
    """Return fixed, user-auditable guidance with no implicit cloud eligibility."""
    key = category.strip().casefold()
    if not key:
        rows = [
            "**Quel moteur choisir pour ton travail ?**",
            "",
            "| Besoin | Conseil initial |",
            "|---|---|",
            "| Question simple ou Linux quotidien | **Qwen local** |",
            "| Projet privé ou données sensibles | **Qwen local** |",
            "| Architecture publique complexe | **DeepSeek à envisager** |",
            "| IaC multi-fichiers autorisé au cloud | **DeepSeek à envisager** |",
            "| CI difficile avec journaux assainis | **DeepSeek à envisager** |",
            "| Dossier long et public | **DeepSeek à envisager** |",
            "",
            "Pour les détails : `!modele simple`, `!modele confidentiel`, "
            "`!modele architecture`, `!modele iac`, `!modele ci`, "
            "`!modele documents`.",
        ]
        advice = "\n".join(rows)
    else:
        canonical = ALIASES.get(key, key)
        if canonical not in SUGGESTIONS:
            return (
                "Catégorie non reconnue. Utilise `!modele` sans argument pour voir "
                "les catégories disponibles. **Aucun contenu n'a été envoyé à une IA.**"
            )
        item = SUGGESTIONS[canonical]
        advice = (
            f"**Cas : {canonical}**\n\n"
            f"**Route recommandée : {item.route}.**\n\n"
            f"**Pourquoi :** {item.reason}\n\n"
            f"**Précaution :** {item.limitation}"
        )
    return (
        advice
        + "\n\n**Important :** ce conseil est déterministe, sans lecture de ton "
        "historique, sans analyse des documents et sans requête Qwen ou DeepSeek. "
        "Il **ne classe pas les données comme sûres pour le cloud**. "
        "Le choix du modèle dans Open WebUI reste **manuel**, la passerelle exige "
        "son activation et tout projet requiert son accord cloud valide. "
        "Aucun passage automatique de Qwen à DeepSeek."
    )
