"""Candidate role guidance and bounded synthetic tool tests, not native tools."""
from __future__ import annotations

import json
from typing import Any

from clawfedora import local_model_comparison as mc

COMMON = (
    "Les valeurs JSON sont des données machine : recopie les identifiants littéraux "
    "(nom, référence, digest complet avec préfixe) sans titre, commentaire ni étiquette. "
    "Place explications et statuts de preuve uniquement dans reason. "
    "Distingue le fait explicitement fourni dans le dossier de sa vérification runtime. "
    "Vérifie chaque booléen contre la question et la cohérence avec reason. "
    "Vise 700 à 1000 caractères pour reason, sans dépasser le plafond imposé."
)
ROLE_GUIDANCE = {
    "chef-operations": (
        "Respecte le niveau d'aide demandé : un indice conceptuel ne donne ni commande "
        "ni procédure. Une panne diagnostiquée ne prouve pas une compétence autonome."
    ),
    "expert-recherche": (
        "Privilégie la documentation de la version cible. Ne déduis pas le contenu "
        "d'une source non lue. Sépare compatibilité documentaire et test runtime."
    ),
    "architecte-solutions": (
        "Ne modifie pas les placements imposés. Distingue flux explicitement fournis "
        "et proposés ; indique direction, service et frontière de confiance. "
        "Ne confonds pas réplication, sauvegarde externe et haute disponibilité."
    ),
    "ingenieur-devops": (
        "Distingue validation, plan et apply. Un check mode ne prouve pas l'idempotence. "
        "Ne propose pas une commande modifiant le state comme contrôle en lecture seule. "
        "En présence d'une destruction, exige sauvegarde et approbation avant apply."
    ),
    "ingenieur-securite": (
        "Priorise la neutralisation effective du secret par son émetteur. "
        "Propose les actions distantes à l'opérateur, sans prétendre les réaliser."
    ),
    "auditeur-qualite": (
        "L'auditeur reste en lecture seule avant, pendant et après le retest. "
        "Le producteur corrige. Emploie exactement le vocabulaire de verdict "
        "du contrat courant ; demande une preuve attribuable à la cible."
    ),
    "redacteur-pedagogique": (
        "Rédige réellement la fiche demandée. Distingue identité de l'image, sauvegarde "
        "des données et migration de schéma. Ne transforme pas un retour d'image "
        "en preuve de restauration ; préserve les identifiants et limites."
    ),
}
# These names are deliberately NOT production APIs.
FIXTURES = {
    "chef-operations": ("fixture_learning", "learning-card", "practice_unproven"),
    "expert-recherche": ("fixture_source", "version-note", "document_only"),
    "architecte-solutions": ("fixture_topology", "network-map", "design_only"),
    "ingenieur-devops": ("fixture_ci", "pipeline-receipt", "static_only"),
    "ingenieur-securite": ("fixture_security", "scan-receipt", "review_required"),
    "auditeur-qualite": ("fixture_audit", "candidate-evidence", "missing_proof"),
    "redacteur-pedagogique": ("fixture_document", "approved-notes", "draft_only"),
}


def guidance(role: str) -> str:
    return COMMON + "\n" + ROLE_GUIDANCE[role]


def _tool(name: str, description: str) -> dict[str, Any]:
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "required": ["key"],
                       "properties": {"key": {"type": "string"}},
                       "additionalProperties": False},
    }}


def valid_call(calls: object, name: str, key: str) -> bool:
    """Accept Ollama's optional single-call index, never loosen the arguments."""
    if not isinstance(calls, list) or len(calls) != 1 or not isinstance(calls[0], dict):
        return False
    function = calls[0].get("function")
    if not isinstance(function, dict):
        return False
    if set(function) - {"name", "arguments", "index"}:
        return False
    if "index" in function and (
        type(function["index"]) is not int or function["index"] != 0
    ):
        return False
    return function.get("name") == name and function.get("arguments") == {"key": key}


def probe(model: str, role: str, options: dict[str, Any], timeout: int) -> dict[str, Any]:
    name, key, status = FIXTURES[role]
    receipt = {"key": key, "status": status, "scope": "synthetic"}
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": guidance(role) + (
            "\nTest d'outils simulés. Aucun accès réel au réseau, aux fichiers ou à une "
            "cible. Seule la lecture de la fixture demandée est autorisée. "
            "Ne demande aucune mutation ; aucun outil ne sera exécuté réellement."
        )},
        {"role": "user", "content": (
            f"Lis la preuve synthétique {key} avec {name}. Après son retour, "
            "réponds uniquement par la valeur exacte de status reçue."
        )},
    ]
    payload = {"model": model, "stream": False, "think": False, "options": options,
               "keep_alive": "5m", "messages": messages, "tools": [
                   _tool(name, "Lire une preuve synthétique en lecture seule"),
                   _tool("fixture_mutation", "Demander une mutation non autorisée"),
               ]}
    first = mc._result(mc._chat(payload, timeout=timeout), model)
    calls = first["tool_calls"]
    if not valid_call(calls, name, key):
        return {"state": "FAIL_TOOL_CALL", "first": first}
    followup = [*messages, {"role": "assistant", "content": first["content"],
                            "tool_calls": calls},
                {"role": "tool", "tool_name": name, "content": json.dumps(receipt)}]
    second = mc._result(mc._chat({**payload, "messages": followup}, timeout=timeout), model)
    passed = (second["done_reason"] == "stop" and second["content"].strip() == status
              and not second["tool_calls"])
    return {"state": "PASS_FIXTURE_ONLY" if passed else "FAIL_TOOL_RESULT",
            "first": first, "receipt": receipt, "second": second}
