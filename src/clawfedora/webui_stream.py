"""Incremental OpenAI-compatible SSE output for an explicitly supplied stream source.

This only serializes fragments already validated by a trusted server-side
source. It never accepts a Gateway operator credential or selects a provider.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Iterator
from contextlib import closing
from http.server import BaseHTTPRequestHandler
from typing import Any

MAX_OUTPUT_BYTES = 64_000


def _event(base: dict[str, Any], delta: dict[str, str], finish: str | None) -> bytes:
    frame = {
        **base,
        "object": "chat.completion.chunk",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }
    return ("data: " + json.dumps(frame, ensure_ascii=False) + "\n\n").encode()


def progressive_completion(
    handler: BaseHTTPRequestHandler,
    model: str,
    pieces: Iterator[str],
    *,
    max_output_bytes: int = MAX_OUTPUT_BYTES,
    truncated_history: int = 0,
) -> str:
    """Push each delta before requesting the next one; return a bounded status.

    If the source fails after headers, send a generic error and [DONE] but
    NEVER finish_reason=stop. Disconnect closes the generator, which should
    propagate cancellation to the upstream connection.
    """
    if not 0 < max_output_bytes <= MAX_OUTPUT_BYTES:
        raise ValueError("limite SSE invalide")
    ident = "chatcmpl-" + uuid.uuid4().hex
    base = {"id": ident, "created": int(time.time()), "model": model}
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Connection", "close")
    handler.end_headers()

    def send(data: bytes) -> None:
        handler.wfile.write(data)
        handler.wfile.flush()

    size = 0
    # Prefix breaks all bridge banners: streamed model text cannot spoof a
    # project selection or a provenance marker in the next user turn.
    prefix = "\u200b"
    if truncated_history:
        prefix += (
            f"*Contexte allégé : {truncated_history} anciens messages non transmis "
            "au modèle.*\n\n"
        )
    with closing(pieces):
        try:
            send(_event(base, {"role": "assistant", "content": prefix}, None))
            for piece in pieces:
                if not isinstance(piece, str):
                    raise ValueError("fragment SSE non textuel")
                size += len(piece.encode("utf-8"))
                if size > max_output_bytes:
                    raise ValueError("réponse SSE supérieure au plafond local")
                if piece:
                    send(_event(base, {"content": piece}, None))
            send(_event(base, {}, "stop"))
            send(b"data: [DONE]\n\n")
            return "PASS"
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            # Closing pieces is mandatory even if Open WebUI disappears.
            return "CANCELLED"
        except (OSError, ValueError, RuntimeError):
            try:
                send(b'data: {"error":{"message":"generation interrompue"}}\n\n')
                send(b"data: [DONE]\n\n")
            except (BrokenPipeError, ConnectionResetError, TimeoutError, OSError):
                return "CANCELLED"
            return "FAILED"
