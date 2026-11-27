"""Conseils déterministes pour le routage des sept agents Ollama, sans cloud."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Advice:
    agent: str
    model: str
    reason: str
    limitation: str


SUGGESTIONS: dict[str, Advice] = {
    "simple": Advice(
        "Mentor infrastructure/OPS", "Qwen 3.5 9B",
        "Une explication Linux ou la lecture d'un YAML est un travail de compréhension.",
        "Ne pas confondre une commande proposée et sa réussite sur Fedora.",
    ),
    "confidentiel": Advice(
        "Spécialiste selon la mission", "Qwen, Ornith ou Gemma, local uniquement",
        "Les fichiers et journaux de projet ne doivent pas être envoyés vers une API de modèle.",
        "Les outils Web sont indépendants : désactiver la recherche Web si nécessaire.",
    ),
    "architecture": Advice(
        "Architecte solutions", "Gemma 4 12B",
        "Cadrer les flux, le réseau, les risques et les compromis avant le code.",
        "Si Terraform ou Kubernetes doit être corrigé, ouvrir une tâche DevOps Ornith.",
    ),
    "iac": Advice(
        "Ingénieur DevOps", "Ornith 1.5 9B",
        "Terraform, Ansible, CI/CD, Bash et Docker exigent des corrections et diagnostics de code.",
        "Un fichier correct n'est pas un déploiement ; plan, tests et "
        "observations réelles sont requis.",
    ),
    "ci": Advice(
        "Ingénieur DevOps", "Ornith 1.5 9B",
        "Analyser le workflow, interpréter les logs puis corriger les causes vérifiées.",
        "Seule la CI associée au bon SHA confirme le résultat ; ne pas exposer les secrets.",
    ),
    "documents": Advice(
        "Rédacteur pédagogique", "Gemma 4 12B",
        "Construire des cours, procédures et runbooks cohérents avec les contributions validées.",
        "Vérifier liens, version des commandes, preuves et rendu réel.",
    ),
    "audit": Advice(
        "Auditeur qualité", "Gemma 4 12B",
        "Confronter critères, diff, rapports de tests et références, sans "
        "modifier le travail audité.",
        "Le modèle ne peut pas certifier une infrastructure sans résultats d'exécution.",
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
    "securite": "audit",
    "long": "documents",
}
CATEGORIES = ("simple", "confidentiel", "architecture", "iac", "ci", "documents", "audit")


def advise(category: str = "") -> str:
    """Conseil de rôle déterministe, sans accès aux conversations ni appel de modèle."""
    key = category.strip().casefold()
    if not key:
        lines = [
            "**Quel agent et quel modèle local ?**",
            "",
            "| Besoin | Agent | Modèle |",
            "|---|---|---|",
            "| Linux quotidien / mentorat | Mentor | Qwen 3.5 9B |",
            "| Données privées | Spécialiste autorisé | Local uniquement |",
            "| Architecture | Architecte | Gemma 4 12B |",
            "| Terraform / Ansible / CI/CD | Ingénieur DevOps | Ornith 1.5 9B |",
            "| Documentation | Rédacteur pédagogique | Gemma 4 12B |",
            "| Audit et preuves | Auditeur qualité | Gemma 4 12B |",
            "",
            "Détails : `!modele simple`, `!modele architecture`, `!modele iac`, "
            "`!modele ci`, `!modele documents`, `!modele audit`.",
        ]
        advice = "\n".join(lines)
    else:
        canonical = ALIASES.get(key, key)
        if canonical not in SUGGESTIONS:
            return (
                "Catégorie non reconnue. Utilise `!modele` sans argument. "
                "**Aucun contenu n'a été envoyé à une IA.**"
            )
        item = SUGGESTIONS[canonical]
        advice = (
            f"**Cas : {canonical}**\n\n"
            f"**Agent : {item.agent} · Modèle : {item.model}.**\n\n"
            f"**Pourquoi :** {item.reason}\n\n"
            f"**Précaution :** {item.limitation}"
        )
    return (
        advice
        + "\n\n**Important :** conseil statique sans analyse des documents ni inférence. "
        "Les sept rôles utilisent exclusivement Ollama sur ce poste. "
        "Aucune route OpenRouter et aucune escalade implicite vers un modèle cloud. "
        "Le worker gère les affectations approuvées, les permissions et les preuves."
    )
