"""Local cloud gateway: the only door from this machine to the cloud model.

OpenClaw talks to this loopback server as if it were an OpenAI-compatible endpoint. The gateway
alone holds the provider key. For every request it, in this order: authenticates the local token,
checks the cloud is activated, bounds and normalises the request (a fixed allow-list of fields),
scans the WHOLE body with the privacy filter, reserves its worst-case cost with the budget guard,
injects the provider settings of the policy, forwards, relays the answer and settles the real
usage. Every refusal happens before anything leaves the machine. Nothing is stored but a
content-free decision log.

An agent turn is several calls (each tool result goes back to the model); only a component on
this path sees all of them, which is why filtering and counting live here.
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from contextlib import suppress
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Protocol

from clawfedora.cloud_privacy import PrivacyFilter, describe
from clawfedora.cloud_state import CLOUD_STATE, ensure_gateway_token, require_cloud_ready
from clawfedora.core_config import core_contract, daily_limits
from clawfedora.local_http import LocalServer

ALLOWED_FIELDS = frozenset({
    "model", "messages", "tools", "tool_choice", "stream", "stream_options", "max_tokens",
    "max_completion_tokens", "temperature", "top_p", "stop", "seed", "parallel_tool_calls",
})
EVENTS_FILE = "events.jsonl"
KEY_FILE_MIN = 20


class BudgetRefused(Exception):
    """The budget guard refuses the call: nothing is sent."""


class Reservation(Protocol):
    def settle(self, usage: dict[str, Any] | None, status: str) -> None:
        """Close a reservation. status: ``ok`` (usage known), ``failed`` (nothing generated,
        release it) or ``interrupted`` (billing unknown: keep the worst-case estimate)."""


class BudgetGuard(Protocol):
    def reserve(self, *, input_tokens: int, max_output_tokens: int) -> Reservation: ...


class FailClosedBudget:
    """Used until a real budget guard is wired: no cloud call can be made."""

    def reserve(self, *, input_tokens: int, max_output_tokens: int) -> Reservation:
        raise BudgetRefused("contrôle du budget non opérationnel: aucun appel cloud possible")


class Refused(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def read_upstream_key(runtime: Path, relative: str) -> str:
    """The provider key, read from a private file at each request, never cached or logged."""
    path = runtime / "state" / relative
    try:
        if path.is_symlink() or path.stat().st_mode & 0o077:
            raise Refused(503, "upstream_key_unsafe", "clé du fournisseur: droits 0600 requis")
        key = path.read_text(encoding="utf-8").strip()
    except OSError:
        raise Refused(
            503, "upstream_key_missing", "clé du fournisseur absente: la gateway ne peut pas appeler"
        ) from None
    if len(key) < KEY_FILE_MIN:
        raise Refused(503, "upstream_key_invalid", "clé du fournisseur invalide")
    return key


class GatewayServer(LocalServer):
    runtime: Path
    token: str
    policy: dict[str, Any]
    budget: BudgetGuard
    privacy: PrivacyFilter
    activation_check: Callable[[], None]
    key_reader: Callable[[], str]
    upstream_base_url: str
    output_cap: int


def _estimate_input_tokens(body: dict[str, Any]) -> int:
    raw = json.dumps([body.get("messages"), body.get("tools")], ensure_ascii=False)
    # Deliberately pessimistic (one token per three bytes): the reservation must not be low.
    return max(1, len(raw.encode()) // 3)


def normalize_request(body: Any, policy: dict[str, Any], output_cap: int) -> dict[str, Any]:
    """Allow-list and bound the client request. Raises ``Refused`` before anything else."""
    if not isinstance(body, dict):
        raise Refused(400, "invalid_request", "objet JSON requis")
    for key in body:
        if key not in ALLOWED_FIELDS:
            raise Refused(400, "unsupported_parameter", f"paramètre non autorisé: {key}")
    upstream_id = str(policy["model"]["upstream_id"])
    if body.get("model") != upstream_id:
        raise Refused(400, "model_not_allowed", "seul le modèle cloud de la politique est autorisé")
    limits = policy["limits"]
    messages = body.get("messages")
    if not isinstance(messages, list) or not 1 <= len(messages) <= int(limits["max_messages"]):
        raise Refused(400, "invalid_request", "messages: liste bornée requise")
    tools = body.get("tools")
    if tools is not None and (
        not isinstance(tools, list)
        or len(tools) > int(limits["max_tools"])
        or any(not isinstance(tool, dict) or tool.get("type") != "function" for tool in tools)
    ):
        raise Refused(400, "invalid_request", "tools: fonctions bornées requises")
    if type(body.get("stream", False)) is not bool:
        raise Refused(400, "invalid_request", "stream doit être booléen")
    options = body.get("stream_options")
    if options is not None and (
        not isinstance(options, dict) or set(options) - {"include_usage"}
    ):
        raise Refused(400, "unsupported_parameter", "stream_options: include_usage seulement")
    requested = [body.get("max_tokens"), body.get("max_completion_tokens")]
    for value in requested:
        if value is not None and (type(value) is not int or value < 1):
            raise Refused(400, "invalid_request", "limite de sortie invalide")
    asked = [value for value in requested if value is not None]
    cap = min([output_cap, *asked])
    normalized = {key: value for key, value in body.items() if key != "max_completion_tokens"}
    normalized["max_tokens"] = cap
    return normalized


def upstream_payload(normalized: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    """What the provider receives: client fields plus the settings only the policy may set."""
    params = policy["upstream_params"]
    payload = dict(normalized)
    payload["provider"] = dict(params["provider"])
    payload["reasoning"] = dict(params["reasoning"])
    payload["usage"] = {"include": True}
    if payload.get("stream"):
        payload["stream_options"] = {"include_usage": True}
    return payload


class GatewayHandler(BaseHTTPRequestHandler):
    server: GatewayServer

    def log_message(self, format: str, *args: Any) -> None:
        pass

    # -- plumbing -----------------------------------------------------------------
    def _json(self, status: int, value: dict[str, Any]) -> None:
        raw = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(raw)

    def _error(self, status: int, code: str, message: str) -> None:
        self._json(status, {"error": {"message": message, "type": code, "code": code}})

    def _event(self, request_id: str, decision: str, **fields: Any) -> None:
        """Append a decision record. It never contains message content or a secret."""
        directory = self.server.runtime / CLOUD_STATE
        directory.mkdir(parents=True, exist_ok=True)
        record = {
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "id": request_id,
            "decision": decision,
            **fields,
        }
        fd = os.open(directory / EVENTS_FILE, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _authorized(self) -> bool:
        host = self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"
        token = hmac.compare_digest(
            self.headers.get("Authorization", ""), "Bearer " + self.server.token
        )
        return host and token

    # -- request ------------------------------------------------------------------
    def do_GET(self) -> None:
        self._error(404, "not_found", "endpoint absent")

    def do_POST(self) -> None:
        request_id = uuid.uuid4().hex[:12]
        prefix = str(self.server.policy["gateway"]["path_prefix"])
        if self.path != prefix + "/chat/completions":
            self._error(404, "not_found", "endpoint absent")
            return
        if not self._authorized():
            self._error(401, "unauthorized", "authentification locale requise")
            return
        reservation: Reservation | None = None
        try:
            self.server.activation_check()
            body = self._read_body()
            normalized = normalize_request(body, self.server.policy, self.server.output_cap)
            findings = self.server.privacy.scan_request(normalized)
            if findings:
                summary = describe(findings)
                self._event(
                    request_id, "blocked", categories=sorted({f.category for f in findings})
                )
                raise Refused(
                    451, "privacy_blocked",
                    "envoi au cloud bloqué par le filtre de confidentialité: " + summary,
                )
            input_tokens = _estimate_input_tokens(normalized)
            try:
                reservation = self.server.budget.reserve(
                    input_tokens=input_tokens, max_output_tokens=int(normalized["max_tokens"])
                )
            except BudgetRefused as exc:
                self._event(request_id, "budget_refused")
                raise Refused(402, "budget_refused", str(exc)) from None
            key = self.server.key_reader()
        except Refused as exc:
            if reservation is not None:
                reservation.settle(None, "failed")
            self._error(exc.status, exc.code, exc.message)
            return
        except ValueError as exc:
            self._error(503, "cloud_not_activated", str(exc))
            return
        self._forward(request_id, normalized, key, reservation, input_tokens)

    def _read_body(self) -> Any:
        limit = int(self.server.policy["limits"]["max_request_bytes"])
        if self.headers.get("Transfer-Encoding"):
            raise Refused(411, "length_required", "Content-Length requis")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0:
            raise Refused(400, "invalid_request", "corps JSON requis")
        if length > limit:
            raise Refused(413, "request_too_large", "requête trop volumineuse")
        if self.headers.get_content_type() != "application/json":
            raise Refused(415, "unsupported_media_type", "application/json requis")
        try:
            return json.loads(self.rfile.read(length))
        except ValueError:
            raise Refused(400, "invalid_request", "JSON invalide") from None

    # -- upstream -----------------------------------------------------------------
    def _forward(
        self,
        request_id: str,
        normalized: dict[str, Any],
        key: str,
        reservation: Reservation,
        input_tokens: int,
    ) -> None:
        policy = self.server.policy
        payload = upstream_payload(normalized, policy)
        request = urllib.request.Request(
            self.server.upstream_base_url + "/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode(),
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
            method="POST",
        )
        timeout = float(policy["upstream"]["timeout_seconds"])
        streaming = bool(normalized.get("stream"))
        self._event(request_id, "forwarded", input_estimate=input_tokens, stream=streaming)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                if streaming:
                    self._relay_stream(request_id, response, reservation)
                else:
                    self._relay_json(request_id, response, reservation)
        except urllib.error.HTTPError as exc:
            reservation.settle(None, "failed")
            self._event(request_id, "upstream_error", status=exc.code)
            self._upstream_error(exc)
        except (urllib.error.URLError, TimeoutError, OSError):
            # The request may have been processed: keep the worst-case estimate.
            reservation.settle(None, "interrupted")
            self._event(request_id, "upstream_unreachable")
            with suppress(OSError):
                self._error(504, "upstream_unreachable", "le fournisseur ne répond pas")

    def _upstream_error(self, exc: urllib.error.HTTPError) -> None:
        if exc.code == 402:
            self._error(402, "upstream_payment_required",
                        "crédits du fournisseur épuisés ou plafond de la clé atteint")
        elif exc.code in (401, 403):
            self._error(502, "upstream_auth", "le fournisseur a refusé la clé de la passerelle")
        elif exc.code == 429:
            self._error(429, "upstream_rate_limited", "limite de débit du fournisseur atteinte")
        else:
            self._error(502, "upstream_error", f"le fournisseur a répondu {exc.code}")

    def _relay_json(self, request_id: str, response: Any, reservation: Reservation) -> None:
        raw = response.read()
        usage: dict[str, Any] | None = None
        with suppress(ValueError):
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and isinstance(parsed.get("usage"), dict):
                usage = parsed["usage"]
        reservation.settle(usage, "ok" if usage else "interrupted")
        self._event(request_id, "completed", usage=_safe_usage(usage))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        with suppress(OSError):
            self.wfile.write(raw)

    def _relay_stream(self, request_id: str, response: Any, reservation: Reservation) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        usage: dict[str, Any] | None = None
        finished = False
        client_alive = True
        try:
            for line in response:
                if line.startswith(b"data:"):
                    data = line[5:].strip()
                    if data == b"[DONE]":
                        finished = True
                    else:
                        with suppress(ValueError):
                            chunk = json.loads(data)
                            if isinstance(chunk, dict) and isinstance(chunk.get("usage"), dict):
                                usage = chunk["usage"]
                if client_alive:
                    try:
                        self.wfile.write(line)
                        self.wfile.flush()
                    except (OSError, ValueError):
                        # The client left, but the provider is still generating and billing:
                        # keep reading to learn the real usage.
                        client_alive = False
        except (OSError, ValueError):
            finished = False
        reservation.settle(usage, "ok" if usage else "interrupted")
        self._event(
            request_id, "completed" if finished else "interrupted", usage=_safe_usage(usage)
        )


def _safe_usage(usage: dict[str, Any] | None) -> dict[str, Any]:
    if not usage:
        return {}
    return {
        key: value
        for key, value in usage.items()
        if isinstance(value, int | float) and not isinstance(value, bool)
    }


def make_server(
    repo_root: Path,
    runtime: Path,
    *,
    budget: BudgetGuard,
    activation_check: Callable[[], None],
    port: int | None = None,
    upstream_base_url: str | None = None,
    key_reader: Callable[[], str] | None = None,
    privacy: PrivacyFilter | None = None,
) -> GatewayServer:
    policy = core_contract(repo_root, "cloud_policy.yaml")
    gateway = policy["gateway"]
    server = GatewayServer(
        (str(gateway["host"]), int(gateway["port"] if port is None else port)), GatewayHandler
    )
    server.runtime = runtime
    server.token = ensure_gateway_token(runtime)
    server.policy = policy
    server.budget = budget
    server.activation_check = activation_check
    server.privacy = privacy or PrivacyFilter(runtime / CLOUD_STATE / "denylist.txt")
    server.output_cap = int(daily_limits(repo_root)["max_output_tokens"])
    if upstream_base_url is not None:
        # Only a loopback test double may replace the provider: never an arbitrary address.
        if not upstream_base_url.startswith("http://127.0.0.1:"):
            raise ValueError("fournisseur de test: boucle locale seulement")
        server.upstream_base_url = upstream_base_url.rstrip("/")
    else:
        server.upstream_base_url = str(policy["upstream"]["base_url"]).rstrip("/")
    server.key_reader = key_reader or (
        lambda: read_upstream_key(runtime, str(gateway["upstream_key_file"]))
    )
    return server


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    args = parser.parse_args()
    # Until the budget guard exists the gateway refuses every call: it can never spend.
    server = make_server(
        args.root,
        args.runtime_root,
        budget=FailClosedBudget(),
        activation_check=lambda: require_cloud_ready(args.runtime_root, args.root),
    )
    with server, suppress(KeyboardInterrupt):
        server.serve_forever()


if __name__ == "__main__":
    main()


__all__ = [
    "BudgetGuard", "BudgetRefused", "FailClosedBudget", "GatewayServer", "Refused",
    "Reservation", "make_server", "normalize_request", "read_upstream_key", "upstream_payload",
]
