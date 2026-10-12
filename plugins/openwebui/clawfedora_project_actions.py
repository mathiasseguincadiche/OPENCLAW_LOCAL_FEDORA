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

READ_ONLY_ACTIONS = {
    "projects": "!projets",
    "status": "!etat",
    "help": "!aide",
    "models": "!modele",
}


def read_only_bridge(
    command: str, history: object, *, key: str, port: int = 18891
) -> str:
    if command not in READ_ONLY_ACTIONS.values():
        raise ValueError("action non autorisée")
    if not isinstance(key, str) or len(key) < 32:
        raise ValueError("jeton du pont local absent")
    if not isinstance(history, list):
        raise ValueError("historique invalide")
    # Project selection lives in the first paragraph of the last project-marked
    # assistant reply. Never forward ordinary chat contents, code, files or secrets
    # just to render a read-only toolbar notification.
    recent: list[dict[str, str]] = []
    for item in reversed(history):
        if not isinstance(item, dict) or item.get("role") != "assistant":
            continue
        content = item.get("content")
        if not isinstance(content, str):
            continue
        marker = content.split("\n", 1)[0][:160]
        if marker.startswith(("📁 Projet : ", "📁 Aucun projet")):
            recent.append({"role": "assistant", "content": marker})
            break
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


class Action:
    actions = [
        {"id": "projects", "name": "Voir les projets"},
        {"id": "status", "name": "État du projet"},
        {"id": "help", "name": "Commandes disponibles"},
        {"id": "models", "name": "Quel modèle choisir ?"},
    ]

    async def action(
        self,
        body: dict[str, Any],
        __id__: str | None = None,
        __user__: dict[str, Any] | None = None,
        __event_emitter__: Any = None,
        **_: Any,
    ) -> None:
        if __id__ not in READ_ONLY_ACTIONS or (__user__ or {}).get("role") != "admin":
            raise ValueError("action interdite")
        secret = os.environ.get("OPENAI_API_KEY", "")
        output = await asyncio.to_thread(
            read_only_bridge, READ_ONLY_ACTIONS[__id__], body.get("messages"), key=secret
        )
        if __event_emitter__ is not None:
            await __event_emitter__(
                {"type": "notification", "data": {"type": "info", "content": output}}
            )
