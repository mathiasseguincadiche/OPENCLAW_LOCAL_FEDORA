"""Opt-in incremental replies in the private native Atelier chat.

This is intentionally limited to a project-free local Mentor conversation.
The existing OpenClaw bridge performs model/permissions preflight and owns the
operator-level Gateway credential. A partial stream is NEVER a completed turn.
"""
from __future__ import annotations

import json
import secrets
import threading
import time
import uuid
from collections.abc import Generator, Iterator
from contextlib import closing
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

from clawfedora import atelier_chat, chat_projects, native_stream
from clawfedora.chat_context import select_history
from clawfedora.stream_transport import MAX_SSE_EVENT_BYTES, content_deltas
from clawfedora.webui_bridge import make_server as make_policy_bridge

MAX_OUTPUT_BYTES = 64_000


def enabled(runtime: Path) -> bool:
    """A 0600 operator-created canary is mandatory. Never enable from browser input."""
    return native_stream.opted_in(runtime)


def allowed(runtime: Path, identifier: str, message: str) -> dict[str, Any]:
    """Precheck before HTTP streaming headers; no project, role or model escalation."""
    document = atelier_chat.read(runtime, identifier)
    if not enabled(runtime):
        raise ValueError("Streaming non activé sur cet atelier")
    if document["agent"] != "chef-operations" or document["project"] is not None:
        raise ValueError("Streaming réservé au Mentor local sans projet")
    if (
        not isinstance(message, str) or not message.strip()
        or len(message.encode("utf-8")) > atelier_chat.MAX_USER_BYTES
        or message.strip().startswith(("!", "/"))
        or chat_projects.parse_command(message) is not None
    ):
        raise ValueError("Streaming réservé aux questions texte simples")
    if document.get("pending") is not None:
        raise ValueError("Tour précédent incertain : ne pas relancer automatiquement")
    if len(document["messages"]) + 2 > atelier_chat.MAX_MESSAGES:
        raise ValueError("Historique trop long : ouvrir une autre conversation")
    return document


def _bridge_deltas(
    repo_root: Path, runtime: Path, document: dict[str, Any], message: str,
) -> Iterator[str]:
    """Consume validated OpenAI-compatible SSE through a private loopback bridge."""
    history, stats = select_history(document["messages"], message)
    document["context_window"] = stats
    payload = {
        "model": "openclaw/chef-operations",
        "stream": True,
        "messages": [*history, {"role": "user", "content": message}],
    }
    bearer = secrets.token_hex(32)
    with make_policy_bridge(repo_root, runtime, bearer, 0) as bridge:
        worker = threading.Thread(target=bridge.serve_forever, daemon=True)
        worker.start()
        try:
            client = HTTPConnection("127.0.0.1", bridge.server_port, timeout=650)
            try:
                client.request(
                    "POST", "/v1/chat/completions", body=json.dumps(payload),
                    headers={
                        "Authorization": "Bearer " + bearer,
                        "Content-Type": "application/json", "Accept": "text/event-stream",
                    },
                )
                response = client.getresponse()
                if response.status != 200:
                    raise ValueError("Pont OpenClaw : génération SSE refusée")
                if response.getheader("Content-Type", "").split(";", 1)[0] != (
                    "text/event-stream"
                ):
                    raise ValueError("Réponse du pont non SSE")
                def lines() -> Iterator[bytes]:
                    while raw := response.readline(MAX_SSE_EVENT_BYTES + 1):
                        yield raw
                yield from content_deltas(lines(), max_output_bytes=MAX_OUTPUT_BYTES)
            finally:
                client.close()
        finally:
            bridge.shutdown()
            worker.join(timeout=5)


def stream(
    repo_root: Path, runtime: Path, identifier: str, message: str,
) -> Generator[dict[str, Any], None, None]:
    """Persist an uncertain intent before inference; commit only after SSE [DONE].

    If the browser disconnects, the bridge fails, or any limit is exceeded,
    the pending marker stays in place to require an explicit human check.
    """
    document = allowed(runtime, identifier, message)
    document["pending"] = {"message": message, "started": int(time.time())}
    atelier_chat._save(runtime, document)
    pieces: list[str] = []
    size = 0
    with closing(_bridge_deltas(repo_root, runtime, document, message)) as source:
        for piece in source:
            if not isinstance(piece, str):
                raise ValueError("Fragment de génération non textuel")
            size += len(piece.encode("utf-8"))
            if size > MAX_OUTPUT_BYTES:
                raise ValueError("Génération supérieure au plafond local")
            pieces.append(piece)
            if piece:
                yield {"type": "delta", "text": piece}

    answer = "".join(pieces)
    if not answer.strip():
        raise ValueError("Réponse locale vide ou incomplète")
    document["messages"].extend([
        {"role": "user", "content": message},
        {"role": "assistant", "content": answer},
    ])
    if document["title"] == "Nouvelle discussion":
        document["title"] = message.strip().replace("\n", " ")[:72]
    document["updated"] = int(time.time())
    document["pending"] = None
    atelier_chat._save(runtime, document)
    yield {"type": "complete", "id": identifier}
