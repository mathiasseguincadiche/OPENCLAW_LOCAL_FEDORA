"""All shared Ollama requests must stay on the exact local service."""
from __future__ import annotations

from typing import Any

import pytest

from clawfedora import ollama_api


@pytest.mark.parametrize("url,payload", [
    ("https://example.invalid/api/generate", {"prompt": "private"}),
    ("http://127.0.0.1:11434@remote.invalid/api/version", None),
    ("http://127.0.0.1:11434/api/version?target=remote", None),
    ("http://127.0.0.1:11434/api/generate", None),
    ("http://127.0.0.1:11434/api/tags", {"prompt": "private"}),
])
def test_disallowed_destination_never_connects(
    monkeypatch: pytest.MonkeyPatch, url: str, payload: dict[str, Any] | None,
) -> None:
    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("network connection opened")

    monkeypatch.setattr(ollama_api, "HTTPConnection", forbidden)
    with pytest.raises(ValueError, match="non autorisée"):
        ollama_api.request_json(url, payload=payload)


@pytest.mark.parametrize("status,raw", [
    (200, b'{"done":true}'),
    (302, b'{"location":"https://example.invalid"}'),
    (200, b"01234567890123456789012345678901234567890"),
    (200, b"[]"),
])
def test_local_transport_is_bounded_and_does_not_follow_redirects(
    monkeypatch: pytest.MonkeyPatch, status: int, raw: bytes,
) -> None:
    calls: list[tuple[str, str]] = []
    closed: list[bool] = []
    monkeypatch.setattr(ollama_api, "MAX_RESPONSE_BYTES", 32)
    monkeypatch.setenv("HTTP_PROXY", "http://example.invalid:8888")

    class Response:
        def __init__(self) -> None:
            self.status = status

        def read(self, limit: int) -> bytes:
            assert limit == 33
            return raw[:limit]

    class Connection:
        def __init__(self, host: str, port: int, timeout: float) -> None:
            assert (host, port, timeout) == ("127.0.0.1", 11434, 10.0)

        def request(self, method: str, path: str, **_kwargs: Any) -> None:
            calls.append((method, path))

        def getresponse(self) -> Response:
            return Response()

        def close(self) -> None:
            closed.append(True)

    monkeypatch.setattr(ollama_api, "HTTPConnection", Connection)
    url = ollama_api.ENDPOINT + "/api/generate"
    if status == 200 and raw == b'{"done":true}':
        assert ollama_api.request_json(url, payload={"prompt": "test"}) == {"done": True}
    else:
        with pytest.raises(ValueError):
            ollama_api.request_json(url, payload={"prompt": "test"})
    assert calls == [("POST", "/api/generate")]
    assert closed == [True]
