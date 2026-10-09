"""Prove, with the real pinned OpenClaw, how a cloud run reaches the local gateway.

The cloud is reached through one loopback endpoint that must see everything: the system
prompt, the history, the tool results and every billed call of an agent turn. This check runs
one real agent turn with ``--model`` set to the cloud model against a fake gateway and fails
unless that endpoint receives the local token (never an upstream key), the tool results of
the loop, and a streamed usage report, while the local Ollama provider is never contacted.
No network, no key and no model are used.
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

from clawfedora.agents import deploy_workspaces
from clawfedora.cloud_state import ensure_gateway_token, write_activation
from clawfedora.core_config import (
    CLOUD_PROVIDER_ID,
    CLOUD_TOKEN_ENV,
    core_contract,
    openclaw_environment,
    root_contract,
)
from clawfedora.openclaw_config import build_openclaw_patch, cloud_model_ref
from clawfedora.project_worker import openclaw_runner
from clawfedora.version_lock import extract_openclaw_version

repo = Path(__file__).resolve().parents[2]
TOKEN = ""  # set from the runtime state once it exists
UPSTREAM_KEY = "sk-or-this-key-must-never-reach-openclaw"
captured: list[dict[str, Any]] = []
cloud = core_contract(repo, "cloud_policy.yaml")
MODEL_ID = str(cloud["model"]["upstream_id"])
GATEWAY_PORT = 19187  # OpenClaw Gateway of this check, away from the production port


class FakeGateway(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        pass

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        messages = body["messages"]
        captured.append(
            {
                "path": self.path,
                "authorization": self.headers.get("Authorization"),
                "model": body.get("model"),
                "stream": body.get("stream"),
                "include_usage": (body.get("stream_options") or {}).get("include_usage"),
                "tools": {item["function"]["name"] for item in body.get("tools", [])},
                "roles": [message["role"] for message in messages],
            }
        )
        has_result = any(message["role"] == "tool" for message in messages)
        if not has_result and "clawfedora_tool_status" in captured[-1]["tools"]:
            delta: dict[str, Any] = {
                "role": "assistant",
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "clawfedora_tool_status", "arguments": "{}"},
                    }
                ],
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


def _check_runner(runtime: Path) -> None:
    """The product runner, with the real CLI: refused until activated, then cloud only."""
    os.environ["HOME"] = str(runtime / "home")
    os.environ.pop("OPENCLAW_CONFIG_PATH", None)
    runner = openclaw_runner(runtime, repo, plain_text=True)
    try:
        runner("chef-operations", "Bonjour", "refused", route="cloud")
    except ValueError:
        pass
    else:
        _fail("la route cloud doit être refusée tant que le cloud n'est pas activé")
    before = len(captured)
    if before and any("refused" in str(call) for call in captured):
        _fail("une route cloud refusée ne doit rien envoyer")
    write_activation(
        runtime, {"privacy_filter": "2026-10-09T00:00:00Z", "budget_guard": "2026-10-09T00:00:00Z"}
    )
    session = str(uuid.uuid4())
    gateway = _start_gateway(runtime)
    try:
        answer = runner(
            "chef-operations", "Quels outils sont disponibles ?", session, route="cloud"
        )
    finally:
        gateway.terminate()
        try:
            gateway.wait(timeout=20)
        except subprocess.TimeoutExpired:
            gateway.kill()
    calls = captured[before:]
    if answer != {"text": "Réponse factice.", "route": "cloud"}:
        _fail(f"réponse inattendue du runner: {answer}")
    if len(calls) < 2 or any(call["authorization"] != f"Bearer {TOKEN}" for call in calls):
        _fail("le runner doit passer par la passerelle avec le jeton local, en deux appels")
    record = json.loads((runtime / f"state/model-runs/{session}.json").read_text())
    if (record["provider"], record["model"], record["route"]) != (
        CLOUD_PROVIDER_ID, MODEL_ID, "cloud"
    ):
        _fail(f"identité du modèle non enregistrée: {record}")
    if CLOUD_TOKEN_ENV in json.dumps(record) or TOKEN in json.dumps(record):
        _fail("l'identité enregistrée ne doit contenir aucun secret")
    print(f"  runner: route cloud refusée puis acceptée, {len(calls)} appels, identité enregistrée")


def main() -> None:
    global TOKEN
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

    # The runner only accepts the exact gateway of the policy: listen on its real port.
    try:
        server = ThreadingHTTPServer(
            (str(cloud["gateway"]["host"]), int(cloud["gateway"]["port"])), FakeGateway
        )
    except OSError as exc:
        raise SystemExit(f"CLOUD_ROUTE=FAIL port de la passerelle indisponible: {exc}") from exc
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with tempfile.TemporaryDirectory(prefix="clawfedora-cloud-route-") as temporary:
            runtime = Path(temporary)
            state = runtime / "state/openclaw"
            state.mkdir(parents=True)
            deploy_workspaces(repo, runtime)
            TOKEN = ensure_gateway_token(runtime)
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
            if TOKEN in serialized or UPSTREAM_KEY in serialized:
                _fail("un secret figure dans la configuration générée")
            path = state / "openclaw.json"
            path.write_text(serialized)
            env = dict(
                os.environ,
                HOME=str(runtime / "home"),
                OPENCLAW_STATE_DIR=str(state),
                OPENCLAW_CONFIG_PATH=str(path),
                OPENCLAW_LOCAL_FEDORA_ROOT=str(runtime),
                OLLAMA_API_KEY="ollama-local",
                OPENROUTER_API_KEY=UPSTREAM_KEY,
                **{str(cloud["gateway"]["token_env"]): TOKEN},
            )
            (runtime / "home").mkdir()
            for role in ("chef-operations", "ingenieur-devops"):
                before = len(captured)
                result = subprocess.run(
                    [cli, "agent", "--local", "--agent", role, "--session-id", str(uuid.uuid4()),
                     "--message", "Quels outils sont disponibles ?",
                     "--model", cloud_model_ref(cloud), "--json", "--timeout", "120"],
                    env=env, capture_output=True, text=True, timeout=300, check=False,
                )
                if result.returncode != 0:
                    _fail(f"{role}: tour cloud en échec: {result.stderr[-1500:]}")
                report = json.loads(result.stdout[result.stdout.index("{") :])
                meta = report["meta"]["agentMeta"]
                if meta.get("provider") != CLOUD_PROVIDER_ID or meta.get("model") != MODEL_ID:
                    _fail(f"{role}: le tour n'a pas utilisé le modèle cloud: {meta}")
                calls = captured[before:]
                if len(calls) < 2:
                    _fail(f"{role}: la boucle d'outil devait produire au moins deux appels")
                for call in calls:
                    if call["authorization"] != f"Bearer {TOKEN}":
                        _fail(f"{role}: la passerelle doit recevoir le jeton local seulement")
                    if UPSTREAM_KEY in str(call):
                        _fail(f"{role}: la clé du fournisseur a atteint la passerelle via OpenClaw")
                    if call["model"] != MODEL_ID or call["stream"] is not True:
                        _fail(f"{role}: requête inattendue: {call}")
                    if call["include_usage"] is not True:
                        _fail(f"{role}: l'usage n'est pas demandé en streaming")
                    if not call["path"].endswith("/chat/completions"):
                        _fail(f"{role}: chemin inattendu: {call['path']}")
                if "tool" in calls[0]["roles"]:
                    _fail(f"{role}: le premier appel ne doit pas contenir de résultat d'outil")
                if "tool" not in calls[1]["roles"]:
                    _fail(f"{role}: le résultat d'outil doit transiter par la passerelle")
                print(
                    f"  {role}: {len(calls)} appels facturables vus par la passerelle, "
                    f"{len(calls[0]['tools'])} outils, résultat d'outil transmis"
                )
            _check_runner(runtime)
    finally:
        server.shutdown()
    print(f"CLOUD_ROUTE=PASS provider={CLOUD_PROVIDER_ID} model={MODEL_ID} version={pin}")


if __name__ == "__main__":
    main()
