"""Measure the real prompt of the pinned OpenClaw against the daily context limits.

Unit tests use simulated model answers, so they cannot see what OpenClaw really sends.
This check runs one real agent turn per role against a local fake Ollama endpoint and
fails when the instructions are truncated or the prompt does not fit the context.
No model, GPU or network is used.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from clawfedora.agents import bootstrap_chars, deploy_workspaces, effective_instructions
from clawfedora.core_config import AGENT_IDS, core_contract, daily_limits, root_contract
from clawfedora.openclaw_config import build_openclaw_patch
from clawfedora.version_lock import extract_openclaw_version
from clawfedora.webui_bridge import chat_prompt

repo = Path(__file__).resolve().parents[2]
MODEL = str(root_contract(repo, "model_catalog.yaml")["models"]["qwen-max"]["runtime_id"])
captured: list[dict[str, Any]] = []


class FakeOllama(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        pass

    def _json(self, value: dict[str, Any], kind: str = "application/json") -> None:
        raw = json.dumps(value).encode() + b"\n"
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if self.path == "/api/version":
            self._json({"version": "0.0.0-fake"})
        else:
            self._json({"models": [{"name": MODEL, "model": MODEL}]})

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        if self.path == "/api/chat":
            captured.append(json.loads(body))
            self._json(
                {
                    "model": MODEL,
                    "message": {"role": "assistant", "content": "Réponse factice."},
                    "done": True,
                    "done_reason": "stop",
                    "prompt_eval_count": 1,
                    "eval_count": 1,
                },
                "application/x-ndjson",
            )
        else:
            self._json({"capabilities": ["completion", "tools", "vision"]})


def _fail(message: str) -> None:
    raise SystemExit("PROMPT_SIZE=FAIL " + message)


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
    limits = daily_limits(repo)
    tool_policy = core_contract(repo, "tool_policy.yaml")["agents"]

    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllama)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with tempfile.TemporaryDirectory(prefix="clawfedora-prompt-limits-") as temporary:
            runtime = Path(temporary)
            state = runtime / "state/openclaw"
            state.mkdir(parents=True)
            deploy_workspaces(repo, runtime)
            toolkit = runtime / "runtime/extensions/clawfedora-toolkit"
            shutil.copytree(repo / "plugins/clawfedora-toolkit", toolkit)
            toolkit.chmod(0o750)
            for asset in toolkit.iterdir():
                asset.chmod(0o640)
            config = build_openclaw_patch(repo, runtime)
            config["models"]["providers"]["ollama"]["baseUrl"] = (
                f"http://127.0.0.1:{server.server_port}"
            )
            config["plugins"] = {
                **config["plugins"],
                "load": {"paths": [str(plugin), str(toolkit)]},
                "entries": {**config["plugins"]["entries"], "parallel": {"enabled": True}},
            }
            path = state / "openclaw.json"
            path.write_text(json.dumps(config))
            env = dict(
                os.environ,
                HOME=str(runtime / "home"),
                OPENCLAW_STATE_DIR=str(state),
                OPENCLAW_CONFIG_PATH=str(path),
                OPENCLAW_LOCAL_FEDORA_ROOT=str(runtime),
                OLLAMA_API_KEY="ollama-local",
            )
            (runtime / "home").mkdir()

            # Worst chat case: the bridge forwards its whole history limit to the mentor.
            sentence = "Le service nginx refuse de démarrer après ma modification du proxy. " * 4
            history: list[dict[str, str]] = []
            while len(json.dumps(history, ensure_ascii=False).encode()) < limits[
                "max_history_bytes"
            ] - 2 * len(sentence.encode()):
                role = "user" if len(history) % 2 == 0 else "assistant"
                history.append({"role": role, "content": sentence + str(len(history))})
            if history[-1]["role"] != "user":
                history.pop()
            _, longest = chat_prompt(
                {"model": "openclaw/chef-operations", "messages": history},
                max_tokens=limits["max_output_tokens"],
                max_history_bytes=limits["max_history_bytes"],
            )
            cases = [(agent, "Bonjour") for agent in AGENT_IDS]
            cases.append(("chef-operations", longest))

            for agent, message in cases:
                before = len(captured)
                message_file = runtime / "message.txt"
                message_file.write_text(message, encoding="utf-8")
                result = subprocess.run(
                    [
                        cli,
                        "agent",
                        "--local",
                        "--agent",
                        agent,
                        "--session-id",
                        str(uuid.uuid4()),
                        "--message-file",
                        str(message_file),
                        "--json",
                        "--timeout",
                        "120",
                    ],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=300,
                    check=False,
                )
                label = f"{agent} ({len(message.encode())} octets)"
                if result.returncode != 0 or len(captured) != before + 1:
                    _fail(f"{label}: tour agent en échec: {result.stderr[-1500:]}")
                if "truncating in injected context" in result.stderr:
                    _fail(f"{label}: consignes du workspace tronquées par OpenClaw")
                report = result.stdout
                pressure = json.loads(report[report.index("{") :])
                text = json.dumps(pressure)
                if '"route": "fits"' not in text or '"overflowTokens": 0' not in text:
                    _fail(f"{label}: le prompt dépasse le contexte disponible")
                request = captured[-1]
                options = request.get("options", {})
                if (
                    options.get("num_ctx") != limits["context_tokens"]
                    or options.get("num_predict") != limits["max_output_tokens"]
                ):
                    _fail(f"{label}: options Ollama divergentes: {options}")
                system = str(request["messages"][0]["content"])
                instructions = effective_instructions(repo, agent)
                if instructions not in system:
                    _fail(f"{label}: AGENTS.md assemblé absent ou altéré dans le prompt natif")
                for marker in ("Accompagnement commun", "Outils et livrables", "Contrat partagé"):
                    if marker not in system:
                        _fail(f"{label}: consigne non injectée: {marker}")
                tools = {item["function"]["name"] for item in request.get("tools", [])}
                forbidden = tools & set(config["tools"]["deny"])
                if forbidden:
                    _fail(f"{label}: outils interdits exposés: {sorted(forbidden)}")
                if not {"read", "web_search", "web_fetch"} <= tools:
                    _fail(f"{label}: outils directs attendus absents: {sorted(tools)}")
                unexpected = tools - set(tool_policy[agent]["also_allow"])
                if unexpected:
                    _fail(f"{label}: outils hors permissions du rôle: {sorted(unexpected)}")
                estimate = text.split('"estimatedPromptTokens": ')[1].split(",")[0]
                print(
                    f"  {label}: AGENTS {len(instructions)} caractères "
                    f"({bootstrap_chars(instructions)} unités UTF-16), "
                    f"prompt estimé {estimate} tokens, {len(tools)} outils directs"
                )
    finally:
        server.shutdown()
    print(
        f"PROMPT_SIZE=PASS context={limits['context_tokens']} "
        f"output={limits['max_output_tokens']} roles={len(AGENT_IDS)} version={pin}"
    )


if __name__ == "__main__":
    main()
