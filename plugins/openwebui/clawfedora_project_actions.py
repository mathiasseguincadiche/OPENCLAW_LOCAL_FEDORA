"""Open WebUI Action: controlled project shortcuts for a single-admin Fedora atelier.

The tool never interprets or executes model output or approves a project
transition by itself. Form input and the selected marker are sent only to
the existing authenticated OpenClaw bridge on loopback, never to a cloud host.
The bridge issues a distinct one-time code for creating the project.
"""

from __future__ import annotations

import asyncio
import http.client
import json
import os
import re
from typing import Any

# Only fixed commands are exposed. The bridge performs all project-state checks.
# Every state-changing button requires an affirmative browser confirmation first.
PROJECT_ACTIONS = {
    "analyze": ("!analyser", "Lancer l'analyse du projet sélectionné ?"),
    "plan": ("!planifier", "Préparer un plan pour le projet sélectionné ?"),
    "start": ("!lancer", "Démarrer les tâches du projet approuvé ?"),
    "pause": ("!pause", "Mettre en pause le projet sélectionné ?"),
    "resume": ("!reprendre", "Reprendre les tâches de ce projet ?"),
    "audit": ("!auditer", "Demander l'audit du travail terminé ?"),
    "review": ("!relire", "Demander une seconde relecture ?"),
    "deliver": ("!livrer", "Préparer la livraison ? Une confirmation distincte restera requise."),
}

READ_ONLY_ACTIONS = {
    "projects": "!projets",
    "status": "!etat",
    "help": "!aide",
    "models": "!modele",
    "budget": "!budget",
}


def _project_marker(history: object) -> str | None:
    if not isinstance(history, list):
        raise ValueError("historique invalide")
    # The server revalidates this marker against its project registry.
    for item in reversed(history):
        if not isinstance(item, dict) or item.get("role") != "assistant":
            continue
        content = item.get("content")
        if not isinstance(content, str):
            continue
        marker = content.split("\n", 1)[0][:160]
        if marker.startswith("📁 Projet : "):
            return marker
        if marker.startswith("📁 Aucun projet"):
            return None
    return None


def local_bridge(
    command: str, history: object, *, key: str, port: int = 18891,
    mutation: bool = False, creation_brief: str | None = None,
    clarification: tuple[int, str] | None = None,
    revision: tuple[str, str] | None = None,
) -> str:
    create = creation_brief is not None
    if sum((create, clarification is not None, revision is not None)) > 1:
        raise ValueError("paramètres incompatibles")
    if revision is not None:
        if not mutation or command != "!modifier":
            raise ValueError("révision non autorisée")
        task_id, reason = revision
        if not isinstance(task_id, str) or not isinstance(reason, str):
            raise ValueError("identifiant ou motif de révision invalide")
        task_id = task_id.strip().lower()
        cleaned = " ".join(reason.split())
        if (
            re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}[a-z0-9]", task_id) is None
            or not cleaned or len(cleaned) > 2000 or "\x00" in reason
        ):
            raise ValueError("identifiant ou motif de révision invalide")
        command = f"!modifier {task_id} {cleaned}"
    if clarification is not None:
        if not mutation or command != "!repondre":
            raise ValueError("réponse de précision non autorisée")
        number, answer = clarification
        if (
            type(number) is not int or not 1 <= number <= 30
            or not isinstance(answer, str) or not answer.strip()
            or len(answer) > 1500 or "\x00" in answer
        ):
            raise ValueError("numéro ou réponse de précision invalide")
        cleaned = " ".join(answer.split())
        if len(cleaned) > 1500:
            raise ValueError("réponse trop longue")
        command = f"!repondre {number} {cleaned}"
    if create:
        if not mutation or not command.startswith("!creer ") or len(command) > 200:
            raise ValueError("création non autorisée")
        title = command.removeprefix("!creer ")
        if (
            not title.strip() or len(title) > 193
            or any(char in title for char in ("\n", "\r", "\x00"))
            or not isinstance(creation_brief, str)
            or not creation_brief.strip()
            or len(creation_brief.encode("utf-8")) > 12_000
            or "\x00" in creation_brief
        ):
            raise ValueError("titre ou demande de projet invalide")
    elif mutation and clarification is None and revision is None:
        if command not in {item[0] for item in PROJECT_ACTIONS.values()}:
            raise ValueError("action mutante non autorisée")
    elif not mutation and command not in READ_ONLY_ACTIONS.values():
        raise ValueError("action non autorisée")
    if not isinstance(key, str) or len(key) < 32:
        raise ValueError("jeton du pont local absent")
    marker = _project_marker(history)
    if mutation and not create and marker is None:
        raise ValueError("sélectionner d'abord le projet dans le chat avec !projet <id>")
    # A fixed command and project marker only. Never forward prompt, files or
    # history from the browser to initiate a project mutation.
    recent = ([{"role": "assistant", "content": marker}] if marker else [])
    if creation_brief is not None:
        recent.append({"role": "user", "content": creation_brief})
    recent.append({"role": "user", "content": command})
    payload = {
        "model": "openclaw/chef-operations",
        "stream": False,
        "messages": recent,
    }
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=8)
    try:
        connection.request(
            "POST", "/v1/chat/completions",
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
        )
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError("pont OpenClaw indisponible ou commande refusée")
        raw = response.read(64_001)
        if len(raw) > 64_000:
            raise ValueError("réponse trop volumineuse")
        parsed = json.loads(raw)
        message = parsed["choices"][0]["message"]["content"]
        if not isinstance(message, str):
            raise ValueError("réponse de commande invalide")
        return message[:2_500]
    finally:
        connection.close()


def read_only_bridge(
    command: str, history: object, *, key: str, port: int = 18891
) -> str:
    return local_bridge(command, history, key=key, port=port)


class Action:
    actions = [
        {"id": "projects", "name": "Voir les projets"},
        {"id": "status", "name": "État du projet"},
        {"id": "help", "name": "Commandes disponibles"},
        {"id": "models", "name": "Quel modèle choisir ?"},
        {"id": "budget", "name": "Budget DeepSeek"},
        {"id": "create", "name": "Créer un projet"},
        {"id": "answer", "name": "Répondre à une précision"},
        {"id": "revise", "name": "Demander une révision"},
        {"id": "analyze", "name": "Analyser le projet"},
        {"id": "plan", "name": "Préparer le plan"},
        {"id": "start", "name": "Lancer les tâches"},
        {"id": "pause", "name": "Mettre en pause"},
        {"id": "resume", "name": "Reprendre"},
        {"id": "audit", "name": "Auditer"},
        {"id": "review", "name": "Relire"},
        {"id": "deliver", "name": "Préparer la livraison"},
    ]

    async def action(
        self,
        body: dict[str, Any],
        __id__: str | None = None,
        __user__: dict[str, Any] | None = None,
        __event_emitter__: Any = None,
        __event_call__: Any = None,
        **_: Any,
    ) -> None:
        if (__user__ or {}).get("role") != "admin":
            raise ValueError("action interdite")
        secret = os.environ.get("OPENAI_API_KEY", "")
        history = body.get("messages")
        if __id__ in READ_ONLY_ACTIONS:
            output = await asyncio.to_thread(
                read_only_bridge, READ_ONLY_ACTIONS[__id__], history, key=secret
            )
        elif __id__ == "create":
            if __event_call__ is None:
                raise ValueError("formulaire navigateur indisponible")
            title = await __event_call__({
                "type": "input", "data": {
                    "title": "Nouveau projet", "message": "Titre du projet (193 caractères max)",
                    "placeholder": "Exemple : Infrastructure Terraform",
                },
            })
            if type(title) is not str or not title.strip():
                return
            brief = await __event_call__({
                "type": "input", "data": {
                    "title": "Objectif du projet",
                    "message": "Décris le besoin, les livrables et les contraintes.",
                    "placeholder": "Objectif, contexte et résultat attendu…",
                },
            })
            if type(brief) is not str or not brief.strip():
                return
            title, brief = title.strip(), brief.strip()
            if (
                len(title) > 193 or any(c in title for c in ("\n", "\r", "\x00"))
                or len(brief.encode("utf-8")) > 12_000 or "\x00" in brief
            ):
                raise ValueError("titre ou demande de projet trop long ou invalide")
            confirmed = await __event_call__({
                "type": "confirmation", "data": {
                    "title": "Préparer un nouveau projet",
                    "message": (
                        f"Préparer « {title} » à partir de {len(brief.encode('utf-8'))} "
                        "octets ? Une confirmation distincte sera demandée "
                        "pour créer réellement le projet."
                    ),
                },
            })
            if confirmed is not True:
                return
            output = await asyncio.to_thread(
                local_bridge, "!creer " + title, history,
                key=secret, mutation=True, creation_brief=brief,
            )
        elif __id__ == "answer":
            if __event_call__ is None:
                raise ValueError("formulaire navigateur indisponible")
            if _project_marker(history) is None:
                raise ValueError("sélectionner d'abord un projet")
            number_raw = await __event_call__({
                "type": "input", "data": {
                    "title": "Question de cadrage",
                    "message": "Numéro affiché par !questions (entre 1 et 30)",
                    "placeholder": "1",
                },
            })
            if type(number_raw) is not str or not number_raw.strip():
                return
            number_raw = number_raw.strip()
            if not number_raw.isdecimal() or not 1 <= int(number_raw) <= 30:
                raise ValueError("numéro de question invalide")
            number = int(number_raw)
            answer_raw = await __event_call__({
                "type": "input", "data": {
                    "title": f"Réponse à la question {number}",
                    "message": "Votre réponse de cadrage (maximum 1 500 caractères)",
                    "placeholder": "Votre réponse…",
                },
            })
            if type(answer_raw) is not str or not answer_raw.strip():
                return
            if len(answer_raw) > 1500 or "\x00" in answer_raw:
                raise ValueError("réponse de cadrage invalide")
            confirmed = await __event_call__({
                "type": "confirmation", "data": {
                    "title": "Enregistrer la réponse",
                    "message": (
                        f"Enregistrer votre réponse à la question {number} "
                        "du projet sélectionné ?"
                    ),
                },
            })
            if confirmed is not True:
                return
            output = await asyncio.to_thread(
                local_bridge, "!repondre", history, key=secret,
                mutation=True, clarification=(number, answer_raw),
            )
        elif __id__ == "revise":
            if __event_call__ is None:
                raise ValueError("formulaire navigateur indisponible")
            if _project_marker(history) is None:
                raise ValueError("sélectionner d'abord un projet")
            task_raw = await __event_call__({
                "type": "input", "data": {
                    "title": "Réviser une tâche",
                    "message": "Identifiant de la tâche figurant dans !etat",
                    "placeholder": "tache-001",
                },
            })
            if type(task_raw) is not str or not task_raw.strip():
                return
            task_id = task_raw.strip().lower()
            if re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}[a-z0-9]", task_id) is None:
                raise ValueError("identifiant de tâche invalide")
            reason_raw = await __event_call__({
                "type": "input", "data": {
                    "title": f"Motif de révision : {task_id}",
                    "message": "Pourquoi reprendre cette tâche ? (maximum 2 000 caractères)",
                    "placeholder": "Décrire précisément le changement attendu…",
                },
            })
            if type(reason_raw) is not str or not reason_raw.strip():
                return
            if len(" ".join(reason_raw.split())) > 2000 or "\x00" in reason_raw:
                raise ValueError("motif de révision invalide")
            confirmed = await __event_call__({
                "type": "confirmation", "data": {
                    "title": "Préparer la révision",
                    "message": (
                        f"Préparer la révision de {task_id} ? Le pont calculera les "
                        "tâches affectées et exigera ensuite une phrase d'approbation "
                        "indépendante avant toute modification."
                    ),
                },
            })
            if confirmed is not True:
                return
            output = await asyncio.to_thread(
                local_bridge, "!modifier", history, key=secret,
                mutation=True, revision=(task_id, reason_raw),
            )
        elif __id__ in PROJECT_ACTIONS:
            # Only a positive response from the actual browser counts, not an
            # LLM claim, a missing callback or a dict containing an error.
            if __event_call__ is None:
                raise ValueError("confirmation navigateur indisponible")
            command, warning = PROJECT_ACTIONS[__id__]
            if _project_marker(history) is None:
                raise ValueError("projet non sélectionné")
            confirmed = await __event_call__(
                {"type": "confirmation", "data": {
                    "title": "Action de projet", "message": warning,
                }}
            )
            if confirmed is not True:
                return
            output = await asyncio.to_thread(
                local_bridge, command, history, key=secret, mutation=True
            )
        else:
            raise ValueError("action interdite")
        if __event_emitter__ is not None:
            await __event_emitter__(
                {"type": "notification", "data": {"type": "info", "content": output}}
            )
