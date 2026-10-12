"""Open WebUI Action: read-only project shortcuts for a single-admin Fedora atelier.

The tool never interprets or executes model output, never approves a project
transition and never sends user content to an external host. Requests go only to
the existing authenticated OpenClaw bridge on loopback.
"""

from __future__ import annotations

import asyncio
import http.client
import json
import os
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
    mutation: bool = False,
) -> str:
    if mutation:
        if command not in {item[0] for item in PROJECT_ACTIONS.values()}:
            raise ValueError("action mutante non autorisée")
    elif command not in READ_ONLY_ACTIONS.values():
        raise ValueError("action non autorisée")
    if not isinstance(key, str) or len(key) < 32:
        raise ValueError("jeton du pont local absent")
    marker = _project_marker(history)
    if mutation and marker is None:
        raise ValueError("sélectionner d'abord le projet dans le chat avec !projet <id>")
    # A fixed command and project marker only. Never forward prompt, files or
    # history from the browser to initiate a project mutation.
    recent = ([{"role": "assistant", "content": marker}] if marker else [])
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
