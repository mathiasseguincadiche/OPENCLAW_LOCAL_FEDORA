"""SSE is an incremental transport, not a success-shaped buffered response."""

from __future__ import annotations

import http.client
import json
from collections.abc import Iterator
from typing import Any

import pytest

from clawfedora.stream_transport import (
    StreamingRefused,
    content_deltas,
    gateway_local_deltas,
)

SESSION = "123e4567-e89b-12d3-a456-426614174000"
TOKEN = "t" * 64


def _chunk(text: str = "", finish: str | None = None) -> bytes:
    return (
        "data: " + json.dumps({
            "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": finish}]
        }) + "\n\n"
    ).encode()


def _lines(*frames: bytes) -> Iterator[bytes]:
    for item in frames:
        yield from item.splitlines(keepends=True)


def test_sse_emits_first_delta_before_source_is_exhausted() -> None:
    produced: list[str] = []

    def source() -> Iterator[bytes]:
        produced.append("first")
        yield from _lines(_chunk("Bonjour "))
        produced.append("second")
        yield from _lines(_chunk("Fedora"))
        produced.append("finish")
        yield from _lines(_chunk("", "stop"), b"data: [DONE]\n\n")

    delta = content_deltas(source())
    assert next(delta) == "Bonjour "
    assert produced == ["first"]
    assert next(delta) == "Fedora"
    assert list(delta) == []
    assert produced == ["first", "second", "finish"]


@pytest.mark.parametrize(
    "frames",
    [
        [_chunk("partiel")],
        [_chunk("partiel"), b"data: [DONE]\n\n"],
        [_chunk("a"), _chunk("", "length"), b"data: [DONE]\n\n"],
        [b"data: {bad json}\n\n"],
        [b"data: {\"error\":{\"message\":\"upstream problem\"}}\n\n"],
        [b"data: {\"choices\":[{\"index\":0,\"delta\":{"
         b"\"tool_calls\":[{}]},\"finish_reason\":null}]}\n\n"],
        [b"garbage\n"],
        [_chunk("x" * 64), _chunk("", "stop"), b"data: [DONE]\n\n"],
    ],
)
def test_malformed_incomplete_and_oversized_streams_refuse(frames: list[bytes]) -> None:
    with pytest.raises(StreamingRefused):
        list(content_deltas(_lines(*frames), max_output_bytes=32))


def test_status_error_cannot_be_reported_as_completed() -> None:
    with pytest.raises(StreamingRefused, match="incomplète"):
        list(content_deltas(_lines(_chunk("truncated"), _chunk("", "content_filter"))))


def test_gateway_adapter_only_contacts_loopback_and_sends_fixed_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connections: list[Any] = []

    class FakeResponse:
        status = 200

        def getheader(self, name: str, default: str = "") -> str:
            assert name == "Content-Type"
            return "text/event-stream; charset=utf-8"

        def readline(self, size: int) -> bytes:
            assert size == 131073
            return next(self.frames, b"")

        def __init__(self) -> None:
            self.frames = _lines(
                _chunk("Premier "), _chunk("token"),
                _chunk("", "stop"), b"data: [DONE]\n\n"
            )

    class FakeConnection:
        def __init__(self, host: str, port: int, timeout: int) -> None:
            assert (host, port, timeout) == ("127.0.0.1", 18789, 30)
            self.closed = False
            connections.append(self)

        def request(
            self, method: str, path: str, *, body: bytes, headers: dict[str, str]
        ) -> None:
            assert method == "POST" and path == "/v1/chat/completions"
            assert headers["Authorization"] == "Bearer " + TOKEN
            data = json.loads(body)
            assert data == {
                "model": "openclaw/chef-operations", "stream": True,
                "user": "clawfedora-" + SESSION,
                "messages": [{"role": "user", "content": "Contexte test"}],
            }

        def getresponse(self) -> FakeResponse:
            return FakeResponse()

        def close(self) -> None:
            self.closed = True

    monkeypatch.setattr(http.client, "HTTPConnection", FakeConnection)
    assert list(gateway_local_deltas(
        "chef-operations", "Contexte test", SESSION, operator_token=TOKEN
    )) == ["Premier ", "token"]
    assert connections[0].closed


def test_gateway_adapter_stops_and_closes_on_consumer_cancel(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    connections: list[Any] = []

    class FakeResponse:
        status = 200

        def getheader(self, _key: str, _default: str = "") -> str:
            return "text/event-stream"

        def readline(self, _size: int) -> bytes:
            return _chunk("continue")

    class FakeConnection:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            self.closed = False
            connections.append(self)

        def request(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        def getresponse(self) -> FakeResponse:
            return FakeResponse()

        def close(self) -> None:
            self.closed = True

    monkeypatch.setattr(http.client, "HTTPConnection", FakeConnection)
    stream = gateway_local_deltas(
        "chef-operations", "bonjour", SESSION, operator_token=TOKEN
    )
    assert next(stream) == "continue"
    stream.close()
    assert connections[0].closed


@pytest.mark.parametrize(
    ("role", "session", "token"),
    [
        ("untrusted-agent", SESSION, TOKEN),
        ("chef-operations", "../escape", TOKEN),
        ("chef-operations", SESSION, "too-short"),
    ],
)
def test_refuses_invalid_target_before_opening_a_connection(
    monkeypatch: pytest.MonkeyPatch, role: str, session: str, token: str
) -> None:
    monkeypatch.setattr(
        http.client, "HTTPConnection",
        lambda *_a, **_kw: pytest.fail("no connection allowed"),
    )
    with pytest.raises(StreamingRefused):
        list(gateway_local_deltas(role, "bonjour", session, operator_token=token))


def test_sse_waits_for_the_blank_line_before_exposing_a_delta() -> None:
    steps: list[str] = []

    def fragmented_event() -> Iterator[bytes]:
        steps.append("data")
        yield _chunk("partiel").splitlines(keepends=True)[0]
        steps.append("commit")
        yield b"\n"
        yield from _lines(_chunk("", "stop"), b"data: [DONE]\n\n")

    source = content_deltas(fragmented_event())
    assert next(source) == "partiel"
    assert steps == ["data", "commit"]
    assert list(source) == []


def test_sse_can_read_a_standard_usage_only_final_frame() -> None:
    usage = b'data: {"choices":[],"usage":{"prompt_tokens":4,"completion_tokens":2}}\n\n'
    frames = _lines(_chunk("OK"), _chunk("", "stop"), usage, b"data: [DONE]\n\n")
    assert list(content_deltas(frames)) == ["OK"]


@pytest.mark.parametrize(
    "frames",
    [
        # A valid JSON document with no final SSE blank line is still incomplete.
        [b'data: {"choices":[{"index":0,"delta":{"content":"fake"},"finish_reason":null}]}\n'],
        [_chunk("fake").removesuffix(b"\n\n")],
        [_chunk("fake").replace(b"\n\n", b"\n"), _chunk("", "stop"), b"data: [DONE]\n\n"],
        # Two 'data' fields must never be interpreted as two separate SSE events.
        [b"data: {}\ndata: {}\n\n"],
        [b"data: {}\x00\n\n"],
        [b"data: {}\r\n", b"unknown: x\n\n"],
        [b'data: {"choices":[{"index":0,"delta":{"role":"system",'
         b'"content":"hi"},"finish_reason":null}]}\n\n'],
        [b'data: {"choices":[{"index":0,"delta":{"role":"tool",'
         b'"content":"hi"},"finish_reason":null}]}\n\n'],
        [b'data: {"choices":[]}\n\n'],
        [_chunk("", "stop"), _chunk("after"), b"data: [DONE]\n\n"],
        [_chunk("content", "stop"), b"data: [DONE]\n\n"],
        [_chunk("", "stop"), _chunk("", "stop"), b"data: [DONE]\n\n"],
        [_chunk("", "stop"), b'data: {"choices":[]}\n\n', b"data: [DONE]\n\n"],
    ],
)
def test_sse_framing_never_promotes_bad_data_to_a_finished_answer(
    frames: list[bytes],
) -> None:
    with pytest.raises(StreamingRefused):
        list(content_deltas(_lines(*frames)))


def test_heartbeats_and_metadata_cannot_become_visible_content() -> None:
    frames = _lines(
        b": keepalive\n",
        b"event: message\nid: raw-secret-not-for-display\n",
        _chunk("Visible"),
        _chunk("", "stop"),
        b"data: [DONE]\n\n",
    )
    assert list(content_deltas(frames)) == ["Visible"]
