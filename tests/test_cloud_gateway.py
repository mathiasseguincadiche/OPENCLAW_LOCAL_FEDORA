"""The gateway: nothing leaves unless it is authenticated, filtered, counted and bounded."""

from __future__ import annotations

import http.client
import json
import random
import string
import threading
import time
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from clawfedora.cloud_gateway import (
    BudgetRefused,
    FailClosedBudget,
    GatewayServer,
    Refused,
    make_server,
    read_upstream_key,
)
from clawfedora.cloud_state import ensure_gateway_token, require_cloud_ready

ROOT = Path(__file__).resolve().parents[1]
MODEL = "z-ai/glm-5.3-flash"
UPSTREAM_KEY = "upstream-key-" + "".join(random.Random(7).choices(string.ascii_lowercase, k=24))
GITHUB_TOKEN = "ghp_" + "".join(random.Random(8).choices(string.ascii_letters + string.digits, k=36))
PATH = "/v1/chat/completions"


class FakeBudget:
    def __init__(self, refuse: bool = False) -> None:
        self.refuse = refuse
        self.reserved: list[tuple[int, int]] = []
        self.settled: list[tuple[dict[str, Any] | None, str]] = []

    def reserve(self, *, input_tokens: int, max_output_tokens: int) -> Any:
        if self.refuse:
            raise BudgetRefused("plafond mensuel atteint")
        self.reserved.append((input_tokens, max_output_tokens))
        budget = self

        class Held:
            def settle(self, usage: dict[str, Any] | None, status: str) -> None:
                budget.settled.append((usage, status))

        return Held()


class Upstream:
    """A fake provider on loopback; its behaviour is set per test."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.behaviour: Callable[[BaseHTTPRequestHandler, dict[str, Any]], None] = self.ok

    @staticmethod
    def usage() -> dict[str, Any]:
        return {"prompt_tokens": 20, "completion_tokens": 9, "total_tokens": 29, "cost": 0.00042}

    def ok(self, handler: BaseHTTPRequestHandler, body: dict[str, Any]) -> None:
        if body.get("stream"):
            chunks = [
                {"choices": [{"delta": {"content": "Bon"}}]},
                {"choices": [{"delta": {"content": "jour"}}]},
                {"choices": [], "usage": self.usage()},
            ]
            raw = "".join("data: " + json.dumps(c) + "\n\n" for c in chunks) + "data: [DONE]\n\n"
            handler.send_response(200)
            handler.send_header("Content-Type", "text/event-stream")
            handler.end_headers()
            handler.wfile.write(raw.encode())
        else:
            raw_json = json.dumps({"choices": [{"message": {"content": "Bonjour"}}],
                                   "usage": self.usage()}).encode()
            handler.send_response(200)
            handler.send_header("Content-Type", "application/json")
            handler.send_header("Content-Length", str(len(raw_json)))
            handler.end_headers()
            handler.wfile.write(raw_json)

    def status(self, code: int) -> Callable[[BaseHTTPRequestHandler, dict[str, Any]], None]:
        def respond(handler: BaseHTTPRequestHandler, body: dict[str, Any]) -> None:
            raw = json.dumps({"error": {"message": "détail du fournisseur"}}).encode()
            handler.send_response(code)
            handler.send_header("Content-Length", str(len(raw)))
            handler.end_headers()
            handler.wfile.write(raw)

        return respond


@pytest.fixture
def upstream() -> Iterator[tuple[Upstream, int]]:
    state = Upstream()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state.requests.append({"path": self.path, "auth": self.headers.get("Authorization"),
                                   "headers": dict(self.headers), "body": body})
            state.behaviour(self, body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True
    ).start()
    yield state, server.server_port
    server.shutdown()


@pytest.fixture
def gateway(
    tmp_path: Path, upstream: tuple[Upstream, int]
) -> Iterator[tuple[GatewayServer, FakeBudget]]:
    (tmp_path / "state").mkdir()
    budget = FakeBudget()
    server = make_server(
        ROOT, tmp_path, budget=budget, activation_check=lambda: None, port=0,
        upstream_base_url=f"http://127.0.0.1:{upstream[1]}/v1",
        key_reader=lambda: UPSTREAM_KEY,
    )
    threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True
    ).start()
    yield server, budget
    server.shutdown()
    server.server_close()


def post(
    server: GatewayServer,
    body: Any,
    *,
    token: str | None = None,
    path: str = PATH,
    headers: dict[str, str] | None = None,
    raw: bytes | None = None,
) -> tuple[int, bytes]:
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    data = raw if raw is not None else json.dumps(body).encode()
    sent = {"Content-Type": "application/json",
            "Authorization": "Bearer " + (token if token is not None else server.token)}
    sent.update(headers or {})
    connection.request("POST", path, body=data, headers=sent)
    response = connection.getresponse()
    return response.status, response.read()


def request(content: str = "Bonjour", **extra: Any) -> dict[str, Any]:
    return {"model": MODEL, "messages": [{"role": "user", "content": content}], **extra}


def events(server: GatewayServer) -> list[dict[str, Any]]:
    path = server.runtime / "state/cloud/events.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


# -- authentication -----------------------------------------------------------------
def test_requests_without_the_local_token_are_refused_before_anything_else(
    gateway: tuple[GatewayServer, FakeBudget], upstream: tuple[Upstream, int]
) -> None:
    server, budget = gateway
    assert post(server, request(), token="wrong")[0] == 401
    assert post(server, request(), headers={"Authorization": ""})[0] == 401
    status, _ = post(server, request(), headers={"Host": "evil.example:80"})
    assert status == 401
    assert post(server, request(), path="/v1/models")[0] == 404
    assert upstream[0].requests == [] and budget.reserved == []


def test_a_gateway_that_is_not_activated_refuses_everything(
    tmp_path: Path, upstream: tuple[Upstream, int]
) -> None:
    (tmp_path / "state").mkdir()
    server = make_server(
        ROOT, tmp_path, budget=FakeBudget(), port=0,
        activation_check=lambda: require_cloud_ready(tmp_path, ROOT),
        upstream_base_url=f"http://127.0.0.1:{upstream[1]}/v1", key_reader=lambda: UPSTREAM_KEY,
    )
    threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True
    ).start()
    try:
        status, body = post(server, request())
        assert status == 503 and b"cloud_not_activated" in body
        assert upstream[0].requests == []
    finally:
        server.shutdown()
        server.server_close()


# -- request shape ------------------------------------------------------------------
@pytest.mark.parametrize(
    "extra",
    [{"models": ["openai/gpt-6"]}, {"provider": {"order": ["x"]}}, {"route": "fallback"},
     {"plugins": [{"id": "web"}]}, {"transforms": ["middle-out"]}, {"reasoning": {"effort": "high"}}],
)
def test_fields_that_could_reroute_or_raise_the_cost_are_refused(
    gateway: tuple[GatewayServer, FakeBudget], upstream: tuple[Upstream, int], extra: dict[str, Any]
) -> None:
    server, budget = gateway
    status, body = post(server, request(**extra))
    assert status == 400 and b"unsupported_parameter" in body
    assert upstream[0].requests == [] and budget.reserved == []


def test_only_the_cloud_model_of_the_policy_is_accepted(
    gateway: tuple[GatewayServer, FakeBudget], upstream: tuple[Upstream, int]
) -> None:
    server, _ = gateway
    bad = request()
    bad["model"] = "openai/gpt-6"
    assert post(server, bad)[0] == 400 and upstream[0].requests == []


@pytest.mark.parametrize(
    "mutation",
    [lambda b: b.update(messages=[]), lambda b: b.update(messages="x"),
     lambda b: b.update(stream="yes"), lambda b: b.update(max_tokens=0),
     lambda b: b.update(tools=[{"type": "retrieval"}]),
     lambda b: b.update(tools=[{"type": "function"}] * 65),
     lambda b: b.update(stream_options={"include_usage": True, "x": 1})],
)
def test_malformed_requests_are_refused(
    gateway: tuple[GatewayServer, FakeBudget], upstream: tuple[Upstream, int], mutation: Any
) -> None:
    server, _ = gateway
    body = request()
    mutation(body)
    assert post(server, body)[0] == 400 and upstream[0].requests == []


def test_body_limits_and_media_type(gateway: tuple[GatewayServer, FakeBudget]) -> None:
    server, _ = gateway
    assert post(server, None, raw=b"{")[0] == 400
    assert post(server, None, raw=b"[]")[0] == 400
    # The size is judged on the declared length, before the body is read.
    assert post(server, None, raw=b"x" * 10, headers={"Content-Length": "2000000"})[0] == 413
    assert post(server, request(), headers={"Content-Type": "text/plain"})[0] == 415
    assert post(server, None, raw=b"")[0] == 400


# -- what the provider receives -----------------------------------------------------
def test_the_provider_receives_the_policy_settings_and_the_provider_key_only(
    gateway: tuple[GatewayServer, FakeBudget], upstream: tuple[Upstream, int]
) -> None:
    server, budget = gateway
    status, body = post(server, request(max_tokens=100000, max_completion_tokens=50000,
                                         temperature=0.2))
    assert status == 200 and json.loads(body)["choices"][0]["message"]["content"] == "Bonjour"
    (seen,) = upstream[0].requests
    sent = seen["body"]
    assert seen["path"] == "/v1/chat/completions"
    assert seen["auth"] == "Bearer " + UPSTREAM_KEY
    assert server.token not in json.dumps(seen)
    assert sent["model"] == MODEL and sent["temperature"] == 0.2
    assert sent["provider"] == {"data_collection": "deny", "require_parameters": True}
    assert sent["reasoning"] == {"effort": "low"} and sent["usage"] == {"include": True}
    assert sent["max_tokens"] == 4096 and "max_completion_tokens" not in sent
    # A smaller limit requested by the client is kept.
    post(server, request(max_tokens=100))
    assert upstream[0].requests[-1]["body"]["max_tokens"] == 100
    assert budget.reserved[0][1] == 4096 and budget.reserved[0][0] > 0


# -- privacy ------------------------------------------------------------------------
@pytest.mark.parametrize("role", ["user", "assistant", "system", "tool"])
def test_a_secret_anywhere_in_the_request_is_blocked_before_reservation_and_sending(
    gateway: tuple[GatewayServer, FakeBudget], upstream: tuple[Upstream, int], role: str
) -> None:
    server, budget = gateway
    body = request()
    body["messages"].append({"role": role, "content": "résultat: " + GITHUB_TOKEN})
    status, answer = post(server, body)
    assert status == 451 and b"privacy_blocked" in answer
    assert GITHUB_TOKEN.encode() not in answer and b"jeton" in answer
    assert upstream[0].requests == [] and budget.reserved == []
    log = (server.runtime / "state/cloud/events.jsonl").read_text()
    assert GITHUB_TOKEN not in log and "résultat" not in log and '"decision": "blocked"' in log


def test_a_secret_in_a_tool_result_of_a_later_call_is_still_caught(
    gateway: tuple[GatewayServer, FakeBudget], upstream: tuple[Upstream, int]
) -> None:
    server, _ = gateway
    clean = request()
    assert post(server, clean)[0] == 200
    looped = request()
    looped["messages"] += [
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "1", "type": "function", "function": {"name": "read", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "1", "content": "export TOKEN=" + GITHUB_TOKEN},
    ]
    assert post(server, looped)[0] == 451
    assert len(upstream[0].requests) == 1


# -- budget -------------------------------------------------------------------------
def test_a_refusing_or_missing_budget_stops_the_call(
    gateway: tuple[GatewayServer, FakeBudget], upstream: tuple[Upstream, int]
) -> None:
    server, budget = gateway
    budget.refuse = True
    status, body = post(server, request())
    assert status == 402 and b"budget_refused" in body and b"plafond mensuel" in body
    server.budget = FailClosedBudget()
    status, body = post(server, request())
    assert status == 402 and "non opérationnel".encode() in body
    assert upstream[0].requests == []


def test_a_failure_after_reservation_releases_it(
    tmp_path: Path, upstream: tuple[Upstream, int]
) -> None:
    (tmp_path / "state").mkdir()
    budget = FakeBudget()

    def no_key() -> str:
        raise Refused(503, "upstream_key_missing", "clé absente")

    server = make_server(ROOT, tmp_path, budget=budget, activation_check=lambda: None, port=0,
                         upstream_base_url=f"http://127.0.0.1:{upstream[1]}/v1", key_reader=no_key)
    threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True
    ).start()
    try:
        assert post(server, request())[0] == 503
        assert budget.settled == [(None, "failed")] and upstream[0].requests == []
    finally:
        server.shutdown()
        server.server_close()


# -- relay and counting -------------------------------------------------------------
def test_a_streamed_answer_is_relayed_and_its_usage_settled(
    gateway: tuple[GatewayServer, FakeBudget], upstream: tuple[Upstream, int]
) -> None:
    server, budget = gateway
    status, raw = post(server, request(stream=True, stream_options={"include_usage": True}))
    text = raw.decode()
    assert status == 200 and '"content": "Bon"' in text and text.endswith("data: [DONE]\n\n")
    assert upstream[0].requests[0]["body"]["stream_options"] == {"include_usage": True}
    assert budget.settled == [(Upstream.usage(), "ok")]
    assert [e["decision"] for e in events(server)] == ["forwarded", "completed"]
    assert events(server)[-1]["usage"]["cost"] == 0.00042


def test_a_client_that_leaves_mid_stream_is_still_counted(
    gateway: tuple[GatewayServer, FakeBudget], upstream: tuple[Upstream, int]
) -> None:
    server, budget = gateway

    def slow(handler: BaseHTTPRequestHandler, body: dict[str, Any]) -> None:
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.end_headers()
        handler.wfile.write(b'data: {"choices": [{"delta": {"content": "a"}}]}\n\n')
        handler.wfile.flush()
        time.sleep(0.4)
        for _ in range(200):
            handler.wfile.write(b'data: {"choices": [{"delta": {"content": "b"}}]}\n\n')
        final = json.dumps({"choices": [], "usage": Upstream.usage()}).encode()
        handler.wfile.write(b"data: " + final + b"\n\ndata: [DONE]\n\n")

    upstream[0].behaviour = slow
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    connection.request("POST", PATH, body=json.dumps(request(stream=True)),
                       headers={"Content-Type": "application/json",
                                "Authorization": "Bearer " + server.token})
    response = connection.getresponse()
    response.fp.readline()  # type: ignore[union-attr]
    connection.close()
    deadline = time.monotonic() + 10
    while not budget.settled and time.monotonic() < deadline:
        time.sleep(0.05)
    assert budget.settled == [(Upstream.usage(), "ok")]


@pytest.mark.parametrize(
    ("code", "status", "marker"),
    [(402, 402, b"upstream_payment_required"), (401, 502, b"upstream_auth"),
     (403, 502, b"upstream_auth"), (429, 429, b"upstream_rate_limited"),
     (500, 502, b"upstream_error"), (404, 502, b"upstream_error")],
)
def test_provider_errors_are_mapped_and_release_the_reservation(
    gateway: tuple[GatewayServer, FakeBudget], upstream: tuple[Upstream, int],
    code: int, status: int, marker: bytes,
) -> None:
    server, budget = gateway
    upstream[0].behaviour = upstream[0].status(code)
    got, body = post(server, request())
    assert got == status and marker in body
    assert UPSTREAM_KEY.encode() not in body and "détail du fournisseur".encode() not in body
    assert budget.settled == [(None, "failed")]


def test_an_unreachable_provider_keeps_the_worst_case_estimate(
    tmp_path: Path,
) -> None:
    (tmp_path / "state").mkdir()
    budget = FakeBudget()
    server = make_server(ROOT, tmp_path, budget=budget, activation_check=lambda: None, port=0,
                         upstream_base_url="http://127.0.0.1:9/v1", key_reader=lambda: UPSTREAM_KEY)
    threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True
    ).start()
    try:
        status, body = post(server, request())
        assert status == 504 and b"upstream_unreachable" in body
        assert budget.settled == [(None, "interrupted")]
    finally:
        server.shutdown()
        server.server_close()


# -- keys and construction ----------------------------------------------------------
def test_the_provider_key_file_must_be_private_and_is_never_a_symlink(tmp_path: Path) -> None:
    key = tmp_path / "state/cloud/upstream.key"
    key.parent.mkdir(parents=True)
    with pytest.raises(Refused, match="absente"):
        read_upstream_key(tmp_path, "cloud/upstream.key")
    key.write_text(UPSTREAM_KEY + "\n")
    key.chmod(0o644)
    with pytest.raises(Refused, match="0600"):
        read_upstream_key(tmp_path, "cloud/upstream.key")
    key.chmod(0o600)
    assert read_upstream_key(tmp_path, "cloud/upstream.key") == UPSTREAM_KEY
    key.write_text("court")
    with pytest.raises(Refused, match="invalide"):
        read_upstream_key(tmp_path, "cloud/upstream.key")
    link = tmp_path / "state/cloud/link.key"
    link.symlink_to(key)
    with pytest.raises(Refused, match="0600"):
        read_upstream_key(tmp_path, "cloud/link.key")


def test_the_provider_cannot_be_replaced_by_an_arbitrary_address(tmp_path: Path) -> None:
    (tmp_path / "state").mkdir()
    for url in ("https://evil.example/v1", "http://10.0.0.5:8080/v1", "http://localhost:9/v1"):
        with pytest.raises(ValueError, match="boucle locale"):
            make_server(ROOT, tmp_path, budget=FakeBudget(), activation_check=lambda: None,
                        port=0, upstream_base_url=url)


def test_default_wiring_targets_the_policy_and_uses_the_shared_token(tmp_path: Path) -> None:
    (tmp_path / "state").mkdir()
    server = make_server(ROOT, tmp_path, budget=FailClosedBudget(), activation_check=lambda: None,
                         port=0)
    try:
        assert server.upstream_base_url == "https://openrouter.ai/api/v1"
        assert server.token == ensure_gateway_token(tmp_path)
    finally:
        server.server_close()
