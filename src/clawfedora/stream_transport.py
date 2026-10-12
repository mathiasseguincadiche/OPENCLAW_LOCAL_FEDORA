"""Restricted SSE transport for the pinned OpenClaw Gateway, NOT enabled by default.

The browser NEVER connects to the operator-level Gateway or sees its token.
This module is staged until runtime identity, rollback and cancellation checks
are integrated into the existing OpenClaw preflight/worker path.
"""

from __future__ import annotations

import http.client
import json
import re
import time
from collections.abc import Iterable, Iterator
from typing import Any

from clawfedora.core_config import AGENT_IDS

GATEWAY_HOST = "127.0.0.1"
GATEWAY_PORT = 18789
MAX_SSE_EVENT_BYTES = 128 * 1024
MAX_TOTAL_BYTES = 64_000
MAX_INPUT_BYTES = 65_536
MAX_DURATION_SECONDS = 630
_SESSION = re.compile(r"^[a-f0-9-]{8,80}$")


class StreamingRefused(ValueError):
    """Bad or untrusted Gateway response. Never claim it was a completed answer."""


def content_deltas(
    lines: Iterable[bytes],
    *,
    max_output_bytes: int = MAX_TOTAL_BYTES,
) -> Iterator[str]:
    """Decode a bounded Gateway OpenAI-style SSE response one delta at a time.

    Errors and premature EOF fail *closed*; the caller must not emit finish=stop.
    This decoder cannot verify source model identity; the caller must enforce
    the existing agent roster/model lock *before* opening the Gateway stream.
    """
    if not 0 < max_output_bytes <= MAX_TOTAL_BYTES:
        raise StreamingRefused("taille de sortie non autorisée")
    total = 0
    saw_stop = False
    saw_done = False
    event_bytes = 0
    for raw in lines:
        if not isinstance(raw, bytes):
            raise StreamingRefused("événement SSE non binaire")
        event_bytes += len(raw)
        if event_bytes > MAX_SSE_EVENT_BYTES:
            raise StreamingRefused("événement SSE démesuré")
        line = raw.rstrip(b"\r\n")
        if not line:
            event_bytes = 0
            continue
        if line.startswith(b":"):
            continue
        if not line.startswith(b"data: "):
            # Spec permits event/id/retry metadata. It must never contain text to display.
            if line.startswith((b"event:", b"id:", b"retry:")):
                continue
            raise StreamingRefused("ligne de flux SSE inconnue")
        payload = line[6:]
        if payload == b"[DONE]":
            if not saw_stop:
                raise StreamingRefused("flux terminé sans résultat final du modèle")
            saw_done = True
            break
        try:
            frame: Any = json.loads(payload)
        except (ValueError, UnicodeError) as exc:
            raise StreamingRefused("événement SSE non décodable") from exc
        if not isinstance(frame, dict) or frame.get("error"):
            raise StreamingRefused("la génération distante a signalé une erreur")
        choices = frame.get("choices")
        if not isinstance(choices, list):
            raise StreamingRefused("événement sans choix de modèle")
        # An optional final usage record may have no choices.
        if not choices:
            continue
        if len(choices) != 1 or not isinstance(choices[0], dict):
            raise StreamingRefused("plusieurs choix de réponse non autorisés")
        item = choices[0]
        if item.get("index") != 0:
            raise StreamingRefused("index de choix incohérent")
        finish = item.get("finish_reason")
        if finish is not None:
            if finish != "stop":
                raise StreamingRefused("génération arrêtée ou incomplète")
            saw_stop = True
        delta = item.get("delta")
        if not isinstance(delta, dict):
            raise StreamingRefused("delta de réponse invalide")
        if set(delta) - {"content", "role"}:
            raise StreamingRefused("delta outil/raisonnement privé non autorisé")
        piece = delta.get("content")
        if piece is None:
            continue
        if saw_stop and piece:
            raise StreamingRefused("texte envoyé après la fin du modèle")
        if not isinstance(piece, str):
            raise StreamingRefused("delta de texte invalide")
        total += len(piece.encode("utf-8"))
        if total > max_output_bytes:
            raise StreamingRefused("sortie du flux trop volumineuse")
        if piece:
            yield piece
    if not saw_stop or not saw_done:
        raise StreamingRefused("flux interrompu avant confirmation de fin")


def gateway_local_deltas(
    role: str,
    prompt: str,
    session: str,
    *,
    operator_token: str,
    port: int = GATEWAY_PORT,
) -> Iterator[str]:
    """Server-side HTTPS-less *loopback-only* Gateway stream, with fixed target.

    Caller owns the worker lock, consent checks, telemetry and the disconnect
    lifecycle. A Gateway token has full operator privilege: NEVER call from
    browser code or a model tool. No custom hostname, URL or model override.
    """
    if role not in AGENT_IDS or not _SESSION.fullmatch(session):
        raise StreamingRefused("agent ou session non autorisé")
    if not isinstance(operator_token, str) or len(operator_token) < 32:
        raise StreamingRefused("jeton d'opérateur indisponible")
    if not isinstance(prompt, str) or len(prompt.encode("utf-8")) > MAX_INPUT_BYTES:
        raise StreamingRefused("message Gateway trop volumineux")
    if type(port) is not int or not 1024 <= port <= 65535:
        raise StreamingRefused("port Gateway invalide")
    body = json.dumps({
        "model": "openclaw/" + role,
        "stream": True,
        "user": "clawfedora-" + session,
        "messages": [{"role": "user", "content": prompt}],
    }, ensure_ascii=False).encode("utf-8")
    connection = http.client.HTTPConnection(GATEWAY_HOST, port, timeout=30)
    started = time.monotonic()
    try:
        connection.request(
            "POST", "/v1/chat/completions", body=body,
            headers={
                "Authorization": "Bearer " + operator_token,
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
        )
        response = connection.getresponse()
        if response.status != 200:
            raise StreamingRefused("le Gateway a refusé le streaming local")
        if response.getheader("Content-Type", "").split(";", 1)[0] != "text/event-stream":
            raise StreamingRefused("réponse Gateway non SSE")
        def bounded_lines() -> Iterator[bytes]:
            while True:
                if time.monotonic() - started > MAX_DURATION_SECONDS:
                    raise StreamingRefused("temps de génération dépassé")
                line = response.readline(MAX_SSE_EVENT_BYTES + 1)
                if not line:
                    break
                yield line
        yield from content_deltas(bounded_lines())
    except (OSError, http.client.HTTPException) as exc:
        raise StreamingRefused("connexion au Gateway local interrompue") from exc
    finally:
        # Closing the source connection aborts the Gateway stream if the caller
        # closes this generator after a browser disconnect.
        connection.close()
