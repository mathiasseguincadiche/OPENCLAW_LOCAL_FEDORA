"""Prove, with the real pinned OpenClaw, that the cloud route is closed by the real gateway.

A real OpenClaw Gateway runs the product runner against the REAL local cloud gateway, in front of
a fake provider. The check fails unless: the provider key lives only in the gateway; the provider
receives the settings of the policy; every billed call of a turn is counted; a secret in the user
message never leaves; and a secret that appears only in a TOOL RESULT (a file read by the agent)
never leaves either. No network, no real key and no model are used.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from clawfedora import project_worker
from clawfedora.agents import deploy_workspaces
from clawfedora.cloud_gateway import make_server
from clawfedora.cloud_privacy import Finding, PrivacyFilter
from clawfedora.cloud_state import ensure_gateway_token, write_activation
from clawfedora.core_config import (
    CLOUD_PROVIDER_ID,
    core_contract,
    openclaw_environment,
    root_contract,
)
from clawfedora.openclaw_config import build_openclaw_patch
from clawfedora.project_worker import openclaw_runner
from clawfedora.version_lock import extract_openclaw_version

repo = Path(__file__).resolve().parents[2]
cloud = core_contract(repo, "cloud_policy.yaml")
MODEL_ID = str(cloud["model"]["upstream_id"])
UPSTREAM_KEY = "sk-or-v1-" + "k" * 40  # the provider key: only the gateway may know it
LEAK = "ghp_" + "Zq7" * 12  # a fake token, never present in any file of this repository
# Secrets OpenClaw cannot recognise (it masks token-shaped values in tool results itself):
SUBSCRIPTION = "7f3c9a42-1d5e-4b8a-9c60-2e8f4a1b6d73"
PERSONAL_TERM = "Acme-Interne-42"
GATEWAY_PORT = 19187  # OpenClaw Gateway of this check, away from the production port
upstream_requests: list[dict[str, Any]] = []
settled: list[tuple[Any, str]] = []


class CountingBudget:
    """Allows everything and records every reservation: stands in for the real budget guard."""

    def reserve(self, *, input_tokens: int, max_output_tokens: int) -> Any:
        class Held:
            def settle(self, usage: Any, status: str) -> None:
                settled.append((usage, status))

        return Held()


class SpyFilter(PrivacyFilter):
    """The real filter, remembering where it found something (never the value)."""

    found: list[list[Finding]] = []

    def scan_request(self, body: dict[str, Any]) -> list[Finding]:
        findings = super().scan_request(body)
        if findings:
            self.found.append(findings)
        return findings


class FakeProvider(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        pass

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        upstream_requests.append({"authorization": self.headers.get("Authorization"), "body": body})
        messages = body["messages"]
        has_result = any(message["role"] == "tool" for message in messages)
        wants_file = "LIRE-LE-FICHIER" in json.dumps(messages)
        tools = {item["function"]["name"]: item["function"] for item in body.get("tools", [])}
        call: dict[str, Any] | None = None
        if not has_result and wants_file and "read" in tools:
            properties = tools["read"].get("parameters", {}).get("properties", {})
            name = next(
                (key for key in ("path", "file_path", "filePath", "file") if key in properties),
                next(iter(properties)),
            )
            call = {"name": "read", "arguments": json.dumps({name: "leak.txt"})}
        elif not has_result and "clawfedora_tool_status" in tools:
            call = {"name": "clawfedora_tool_status", "arguments": "{}"}
        if call:
            delta: dict[str, Any] = {
                "role": "assistant",
                "tool_calls": [{"index": 0, "id": "call_1", "type": "function", "function": call}],
            }
            finish = "tool_calls"
        else:
            delta = {"role": "assistant", "content": "Réponse factice."}
            finish = "stop"
        usage = {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18, "cost": 0.0001}
        chunks = [
            {"id": "c", "object": "chat.completion.chunk", "model": MODEL_ID,
             "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
            {"id": "c", "object": "chat.completion.chunk", "model": MODEL_ID,
             "choices": [{"index": 0, "delta": {}, "finish_reason": finish}]},
            {"id": "c", "object": "chat.completion.chunk", "model": MODEL_ID,
             "choices": [], "usage": usage},
        ]
        raw = ("".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks)
               + "data: [DONE]\n\n").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def _fail(message: str) -> None:
    raise SystemExit("CLOUD_ROUTE=FAIL " + message)


def _start_gateway(runtime: Path) -> subprocess.Popen[bytes]:
    """A real OpenClaw Gateway: the product runner always goes through it."""
    environment = openclaw_environment(runtime)
    environment["HOME"] = str(runtime / "home")
    log = (runtime / "gateway.log").open("wb")
    process = subprocess.Popen(
        ["openclaw", "gateway", "--port", str(GATEWAY_PORT)],
        env=environment,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if process.poll() is not None:
            tail = (runtime / "gateway.log").read_text()[-800:]
            _fail("la Gateway OpenClaw s'est arrêtée: " + tail)
        with socket.socket() as probe:
            probe.settimeout(1)
            if probe.connect_ex(("127.0.0.1", GATEWAY_PORT)) == 0:
                time.sleep(2)
                return process
        time.sleep(1)
    process.terminate()
    _fail("la Gateway OpenClaw n'a pas démarré à temps")
    raise AssertionError  # unreachable


def _events(runtime: Path) -> list[dict[str, Any]]:
    path = runtime / "state/cloud/events.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


last_error: list[str] = []


def _remember_cli_errors() -> None:
    """The runner reports only an exit code: keep the CLI's own message for diagnostics."""
    real = subprocess.run

    def run(*args: Any, **kwargs: Any) -> Any:
        completed = real(*args, **kwargs)
        if completed.returncode != 0 and args and "agent" in args[0]:
            last_error.append((completed.stderr or "")[-600:] + (completed.stdout or "")[-300:])
        return completed

    project_worker.subprocess.run = run  # type: ignore[assignment]


def _check_runner(runtime: Path) -> None:
    _remember_cli_errors()
    os.environ["HOME"] = str(runtime / "home")
    os.environ.pop("OPENCLAW_CONFIG_PATH", None)
    runner = openclaw_runner(runtime, repo, plain_text=True)
    try:
        runner("chef-operations", "Bonjour", "refused", route="cloud")
    except ValueError:
        pass
    else:
        _fail("la route cloud doit être refusée tant que le cloud n'est pas activé")
    if upstream_requests:
        _fail("une route cloud refusée ne doit rien envoyer")
    write_activation(
        runtime, {"privacy_filter": "2026-10-09T00:00:00Z", "budget_guard": "2026-10-09T00:00:00Z"}
    )

    gateway = _start_gateway(runtime)
    try:
        # 1. Normal turn: one tool call, so two billed calls, all counted.
        session = str(uuid.uuid4())
        answer = runner("chef-operations", "Quels outils sont disponibles ?", session,
                        route="cloud")
        if answer != {"text": "Réponse factice.", "route": "cloud"}:
            _fail(f"réponse inattendue du runner: {answer}")
        if len(upstream_requests) != 2 or len(settled) != 2:
            _fail(f"deux appels facturables attendus, vus {len(upstream_requests)}/{len(settled)}")
        for seen in upstream_requests:
            sent = seen["body"]
            if seen["authorization"] != "Bearer " + UPSTREAM_KEY:
                _fail("le fournisseur doit recevoir la clé de la passerelle, jamais le jeton local")
            if sent["model"] != MODEL_ID or sent["provider"] != {
                "data_collection": "deny", "require_parameters": True
            } or sent["reasoning"] != {"effort": "low"} or sent["usage"] != {"include": True}:
                _fail(f"réglages de la politique absents de la requête: {sorted(sent)}")
            if sent["max_tokens"] > int(cloud["model"]["max_output_tokens"]):
                _fail("la sortie doit être bornée par la politique")
        if any(status != "ok" for _, status in settled):
            _fail(f"chaque appel doit être compté avec son usage: {settled}")
        record = json.loads((runtime / f"state/model-runs/{session}.json").read_text())
        if (record["provider"], record["model"], record["route"]) != (
            CLOUD_PROVIDER_ID, MODEL_ID, "cloud"
        ):
            _fail(f"identité du modèle non enregistrée: {record}")

        # 2. A secret in the user message never leaves.
        before = len(upstream_requests)
        try:
            runner("chef-operations", "ma clé est " + LEAK, str(uuid.uuid4()), route="cloud")
        except (ValueError, RuntimeError):
            pass
        else:
            _fail("un secret dans le message doit faire échouer le tour cloud")
        if len(upstream_requests) != before:
            _fail("un secret dans le message a atteint le fournisseur")

        # 3. A secret that exists only in a TOOL RESULT never leaves either.
        (runtime / "workspaces/chef-operations/leak.txt").write_text(
            f'subscription_id = "{SUBSCRIPTION}"\n# client: {PERSONAL_TERM}\n'
        )
        before = len(upstream_requests)
        failure = ""
        try:
            outcome = runner("chef-operations", "LIRE-LE-FICHIER", str(uuid.uuid4()), route="cloud")
        except (ValueError, RuntimeError) as exc:
            failure = str(exc)
        else:
            _fail(
                "un secret dans un résultat d'outil doit faire échouer le tour cloud: "
                f"réponse={str(outcome)[:300]}; appels={len(upstream_requests) - before}; "
                f"blocages={SpyFilter.found}; cli={last_error[-1:]}"
            )
        calls = upstream_requests[before:]
        if len(calls) != 1:
            _fail(
                "le premier appel part, le second (avec le résultat d'outil) est bloqué: "
                f"{len(calls)} appels; erreur={failure}; blocages={SpyFilter.found}; "
                f"cli={last_error[-1:]}"
            )
        sent = json.dumps(upstream_requests)
        if any(secret in sent for secret in (LEAK, SUBSCRIPTION, PERSONAL_TERM)):
            _fail("un secret a atteint le fournisseur")
    finally:
        gateway.terminate()
        try:
            gateway.wait(timeout=20)
        except subprocess.TimeoutExpired:
            gateway.kill()

    blocked = [event for event in _events(runtime) if event["decision"] == "blocked"]
    if len(blocked) != 2 or "token" not in blocked[0]["categories"] or set(
        blocked[1]["categories"]
    ) != {"subscription_id", "denylist"}:
        _fail(f"deux blocages journalisés attendus (message puis résultat d'outil): {blocked}")
    log = (runtime / "state/cloud/events.jsonl").read_text()
    if any(secret in log for secret in (LEAK, SUBSCRIPTION, PERSONAL_TERM, UPSTREAM_KEY)):
        _fail("le journal de décisions ne doit contenir ni secret ni clé")
    for path in runtime.rglob("*"):
        if path.is_file() and path.name != "gateway.log" and ".sqlite" not in path.name:
            with open(path, "rb") as handle:
                if UPSTREAM_KEY.encode() in handle.read():
                    _fail(f"la clé du fournisseur figure hors de la passerelle: {path.name}")
    print(
        f"  runner: {len(settled)} appels comptés, secret du message et secret d'un résultat "
        "d'outil bloqués avant tout envoi"
    )


def main() -> None:
    cli = shutil.which("openclaw")
    if not cli:
        raise SystemExit("OpenClaw CLI absent: install the exact pin and Parallel plugin first")
    version = subprocess.run([cli, "--version"], capture_output=True, text=True, check=True).stdout
    pin = str(root_contract(repo, "runtime_versions.yaml")["openclaw"]["version"])
    if extract_openclaw_version(version) != pin:
        raise SystemExit("OpenClaw version differs from the repository pin")
    plugin = Path(os.environ["OPENCLAW_SCHEMA_PARALLEL_PATH"]).resolve()
    if not (plugin / "openclaw.plugin.json").is_file():
        raise SystemExit("Pinned Parallel plugin absent")

    provider = ThreadingHTTPServer(("127.0.0.1", 0), FakeProvider)
    threading.Thread(target=provider.serve_forever, daemon=True).start()
    gate = None
    try:
        with tempfile.TemporaryDirectory(prefix="clawfedora-cloud-route-") as temporary:
            runtime = Path(temporary)
            state = runtime / "state/openclaw"
            state.mkdir(parents=True)
            deploy_workspaces(repo, runtime)
            ensure_gateway_token(runtime)
            toolkit = runtime / "runtime/extensions/clawfedora-toolkit"
            shutil.copytree(repo / "plugins/clawfedora-toolkit", toolkit)
            toolkit.chmod(0o750)
            for asset in toolkit.iterdir():
                asset.chmod(0o640)
            config = build_openclaw_patch(repo, runtime, cloud_enabled=True)
            # Ollama points at a closed port: a cloud run must never touch it.
            config["models"]["providers"]["ollama"]["baseUrl"] = "http://127.0.0.1:9"
            config["gateway"] = {**config["gateway"], "port": GATEWAY_PORT}
            config["plugins"] = {
                **config["plugins"],
                "load": {"paths": [str(plugin), str(toolkit)]},
                "entries": {**config["plugins"]["entries"], "parallel": {"enabled": True}},
            }
            serialized = json.dumps(config)
            if UPSTREAM_KEY in serialized or LEAK in serialized:
                _fail("un secret figure dans la configuration générée")
            (state / "openclaw.json").write_text(serialized)

            # The personal denylist the user keeps next to the gateway state.
            (runtime / "state/cloud/denylist.txt").write_text(PERSONAL_TERM + "\n")
            # The REAL gateway, on the port of the policy, in front of the fake provider.
            try:
                gate = make_server(
                    repo, runtime, budget=CountingBudget(), activation_check=lambda: None,
                    upstream_base_url=f"http://127.0.0.1:{provider.server_port}/v1",
                    key_reader=lambda: UPSTREAM_KEY,
                    privacy=SpyFilter(runtime / "state/cloud/denylist.txt"),
                )
            except OSError as exc:
                _fail(f"port de la passerelle indisponible: {exc}")
            threading.Thread(target=gate.serve_forever, daemon=True).start()
            (runtime / "home").mkdir()
            _check_runner(runtime)
    finally:
        if gate is not None:
            gate.shutdown()
        provider.shutdown()
    print(f"CLOUD_ROUTE=PASS provider={CLOUD_PROVIDER_ID} model={MODEL_ID} version={pin}")


if __name__ == "__main__":
    main()
