"""A real live SSE bridge, with staging enabled only via dependency injection."""

from __future__ import annotations

import json
import threading
from collections.abc import Generator
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

import pytest

from clawfedora.project_worker import worker_lock
from clawfedora.webui_bridge import MODEL_IDS, make_server

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "a" * 64


def _request(server: Any, messages: list[dict[str, str]]) -> HTTPConnection:
    conn = HTTPConnection("127.0.0.1", server.server_port, timeout=8)
    conn.request(
        "POST", "/v1/chat/completions",
        body=json.dumps({"model": MODEL_IDS[0], "stream": True, "messages": messages}),
        headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"},
    )
    return conn


def test_bridge_streams_first_token_before_source_finishes_and_keeps_worker_lock(
    tmp_path: Path,
) -> None:
    first_sent = threading.Event()
    continue_stream = threading.Event()
    finished = threading.Event()
    calls: list[str] = []

    def original_runner(*_args: Any) -> dict[str, Any]:
        pytest.fail("CLI must not be invoked when the tested streaming source is selected")

    def stream_runner(role: str, prompt: str, session: str) -> Generator[str, None, None]:
        calls.append(role)
        assert "Fedora" in prompt and len(session) == 36
        yield "Premier "
        first_sent.set()
        assert continue_stream.wait(timeout=5)
        yield "second"
        finished.set()

    with make_server(
        ROOT, tmp_path, TOKEN, 0, runner=original_runner, stream_runner=stream_runner
    ) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        conn = _request(server, [{"role": "user", "content": "Fedora"}])
        response = conn.getresponse()
        assert response.status == 200
        assert response.getheader("Content-Type") == "text/event-stream"
        # Role marker, then the first real delta must arrive while the
        # upstream generator is still paused before its second delta.
        role_event = response.readline()
        assert b"chat.completion.chunk" in role_event
        assert b"\xe2\x80\x8b" in role_event  # invisible defang prefix
        assert response.readline() == b"\n"
        first = response.readline()
        assert b"Premier " in first and b"second" not in first
        assert first_sent.wait(timeout=2)
        assert not finished.is_set()
        with pytest.raises(ValueError, match="déjà actif"), worker_lock(tmp_path):
            pass
        assert response.readline() == b"\n"
        continue_stream.set()
        rest = response.read().decode()
        assert "second" in rest and '"finish_reason": "stop"' in rest
        assert "data: [DONE]" in rest
        conn.close()
        server.shutdown()
        thread.join(timeout=5)
    assert calls == ["chef-operations"]


def test_streaming_failure_is_visible_and_not_falsely_completed(tmp_path: Path) -> None:
    def stream_runner(
        _role: str, _prompt: str, _session: str
    ) -> Generator[str, None, None]:
        yield "partial output"
        raise RuntimeError("raw provider secret must not leak to client")

    with make_server(ROOT, tmp_path, TOKEN, 0, stream_runner=stream_runner) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        conn = _request(server, [{"role": "user", "content": "bonjour"}])
        response = conn.getresponse()
        data = response.read().decode()
        assert response.status == 200
        assert "partial output" in data
        assert "generation interrompue" in data
        assert "raw provider secret" not in data
        assert '"finish_reason": "stop"' not in data
        assert "data: [DONE]" in data
        conn.close()
        server.shutdown()
        thread.join(timeout=5)


def test_streaming_falls_back_to_existing_cli_path_when_source_not_approved(
    tmp_path: Path,
) -> None:
    used: list[str] = []

    def runner(role: str, _prompt: str, _session: str) -> dict[str, Any]:
        used.append(role)
        return {"text": "Réponse classique en un bloc"}

    with make_server(ROOT, tmp_path, TOKEN, 0, runner=runner) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        conn = _request(server, [{"role": "user", "content": "salut"}])
        response = conn.getresponse()
        data = response.read().decode()
        assert response.status == 200
        assert "classique en un bloc" in data
        assert "data: [DONE]" in data
        conn.close()
        server.shutdown()
        thread.join(timeout=5)
    assert used == ["chef-operations"]


def test_source_never_runs_for_commands_or_project_history(tmp_path: Path) -> None:
    invoked: list[str] = []

    def stream_runner(
        _role: str, _prompt: str, _session: str
    ) -> Generator[str, None, None]:
        invoked.append("bad")
        yield "should never stream"

    with make_server(ROOT, tmp_path, TOKEN, 0, stream_runner=stream_runner) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        for messages in (
            [{"role": "user", "content": "!aide"}],
            [
                {"role": "assistant", "content": "📁 Projet : fake-project"},
                {"role": "user", "content": "!etat"},
            ],
        ):
            conn = _request(server, messages)
            response = conn.getresponse()
            assert response.status == 200
            assert b"data: [DONE]" in response.read()
            conn.close()
        server.shutdown()
        thread.join(timeout=5)
    assert not invoked


@pytest.mark.parametrize("truncate", [False, True])
def test_staged_gateway_stream_reaches_webui_without_exposing_operator_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, truncate: bool,
) -> None:
    from clawfedora import stream_transport

    operator_token = "gateway-only-operator-token-" + "z" * 40
    network: list[Any] = []

    def event(text: str, finish: str | None = None) -> bytes:
        return (
            "data: " + json.dumps({
                "choices": [{"index": 0, "delta": {"content": text},
                             "finish_reason": finish}]
            }) + "\n\n"
        ).encode()

    class GatewayResponse:
        status = 200

        def __init__(self) -> None:
            values = [event("Premier "), event("fragment")]
            if not truncate:
                values.extend([event("", "stop"), b"data: [DONE]\n\n"])
            self.lines = iter(b"".join(values).splitlines(keepends=True))

        def getheader(self, _name: str, _default: str = "") -> str:
            return "text/event-stream"

        def readline(self, _size: int) -> bytes:
            return next(self.lines, b"")

    class GatewayConnection:
        def __init__(self, host: str, port: int, timeout: int) -> None:
            assert (host, port, timeout) == ("127.0.0.1", 18789, 30)
            self.closed = False
            network.append(self)

        def request(
            self, method: str, endpoint: str, *, body: bytes, headers: dict[str, str]
        ) -> None:
            assert method == "POST" and endpoint == "/v1/chat/completions"
            assert headers["Authorization"] == "Bearer " + operator_token
            assert json.loads(body)["model"] == MODEL_IDS[0]

        def getresponse(self) -> GatewayResponse:
            return GatewayResponse()

        def close(self) -> None:
            self.closed = True

    monkeypatch.setattr(stream_transport.http.client, "HTTPConnection", GatewayConnection)

    def source(role: str, prompt: str, session: str) -> Generator[str, None, None]:
        yield from stream_transport.gateway_local_deltas(
            role, prompt, session, operator_token=operator_token
        )

    with make_server(ROOT, tmp_path, TOKEN, 0, stream_runner=source) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        conn = _request(server, [{"role": "user", "content": "bonjour"}])
        response = conn.getresponse()
        body = response.read().decode()
        assert response.status == 200
        assert "Premier " in body and "fragment" in body
        assert operator_token not in body
        if truncate:
            assert "generation interrompue" in body
            assert '"finish_reason": "stop"' not in body
        else:
            assert '"finish_reason": "stop"' in body
        assert "data: [DONE]" in body
        conn.close()
        server.shutdown()
        thread.join(timeout=5)
    assert network and network[0].closed
