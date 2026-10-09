"""The cloud route of the runner: refused unless activated, never through Ollama."""

from __future__ import annotations

import json
import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest

from clawfedora import ollama_api, project_worker
from clawfedora.cloud_state import (
    cloud_status,
    ensure_gateway_token,
    revoke_activation,
    write_activation,
)
from clawfedora.core_config import CLOUD_TOKEN_ENV, openclaw_environment
from clawfedora.openclaw_config import build_openclaw_patch

ROOT = Path(__file__).resolve().parents[1]
BOTH = {"privacy_filter": "2026-10-09T10:00:00Z", "budget_guard": "2026-10-09T10:00:00Z"}


class FakeOpenClaw:
    """Answers the few `openclaw` commands the runner issues; records what it was asked."""

    def __init__(self, runtime: Path) -> None:
        patch = build_openclaw_patch(ROOT, runtime, cloud_enabled=True)
        self.agents = patch["agents"]
        self.providers = patch["models"]["providers"]
        self.envelope: dict[str, Any] = self.reply("Bonjour", "cloudgw", "z-ai/glm-5.3-flash")
        self.commands: list[list[str]] = []
        self.environments: list[dict[str, str]] = []

    @staticmethod
    def reply(text: str, provider: str, model: str) -> dict[str, Any]:
        return {
            "status": "ok",
            "result": {
                "meta": {
                    "finalAssistantVisibleText": text,
                    "agentMeta": {
                        "provider": provider,
                        "model": model,
                        "usage": {"input": 12, "output": 5, "cacheRead": 0},
                    },
                }
            },
        }

    def __call__(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        self.environments.append(kwargs.get("env") or {})
        if command[:2] == ["openclaw", "--version"]:
            return subprocess.CompletedProcess(command, 0, "OpenClaw 2026.9.8 (abc)", "")
        if command[:4] == ["openclaw", "config", "get", "agents"]:
            return subprocess.CompletedProcess(command, 0, json.dumps(self.agents), "")
        if command[:4] == ["openclaw", "config", "get", "models.providers"]:
            return subprocess.CompletedProcess(command, 0, json.dumps(self.providers), "")
        if command[:2] == ["openclaw", "agent"]:
            return subprocess.CompletedProcess(command, 0, json.dumps(self.envelope), "")
        raise AssertionError(f"commande inattendue: {command}")

    def agent_commands(self) -> list[list[str]]:
        return [command for command in self.commands if command[:2] == ["openclaw", "agent"]]


@pytest.fixture
def runtime(tmp_path: Path) -> Path:
    (tmp_path / "state").mkdir()
    (tmp_path / "state/openclaw").mkdir()
    (tmp_path / "state/openclaw/openclaw.json").write_text("{}")
    return tmp_path


@pytest.fixture
def fake(runtime: Path, monkeypatch: pytest.MonkeyPatch) -> FakeOpenClaw:
    fake = FakeOpenClaw(runtime)
    monkeypatch.setattr(project_worker.subprocess, "run", fake)

    def no_ollama(url: str) -> dict[str, Any]:
        pytest.fail(f"la route cloud ne doit pas contacter Ollama: {url}")

    monkeypatch.setattr(ollama_api, "request_json", no_ollama)
    return fake


def test_cloud_route_is_refused_until_every_control_is_verified(
    runtime: Path, fake: FakeOpenClaw
) -> None:
    runner = project_worker.openclaw_runner(runtime, ROOT, plain_text=True)
    with pytest.raises(ValueError, match="cloud non activé"):
        runner("chef-operations", "Bonjour", "s1", route="cloud")
    write_activation(runtime, {"privacy_filter": "2026-10-09T10:00:00Z"})
    with pytest.raises(ValueError, match="budget_guard"):
        runner("chef-operations", "Bonjour", "s1", route="cloud")
    write_activation(runtime, {"budget_guard": "2026-10-09T10:00:00Z"})
    with pytest.raises(ValueError, match="privacy_filter"):
        runner("chef-operations", "Bonjour", "s1", route="cloud")
    # Refused before any process starts.
    assert fake.commands == []


def test_unknown_route_is_refused(runtime: Path, fake: FakeOpenClaw) -> None:
    runner = project_worker.openclaw_runner(runtime, ROOT, plain_text=True)
    with pytest.raises(ValueError, match="route inconnue"):
        runner("chef-operations", "Bonjour", "s1", route="openrouter")


def test_the_redacted_environment_reference_of_the_real_cli_is_accepted(
    runtime: Path, fake: FakeOpenClaw
) -> None:
    write_activation(runtime, BOTH)
    fake.providers["cloudgw"]["apiKey"]["id"] = "__OPENCLAW_REDACTED__"
    runner = project_worker.openclaw_runner(runtime, ROOT, plain_text=True)
    assert runner("chef-operations", "Bonjour", "s0", route="cloud")["route"] == "cloud"


def test_cloud_route_selects_the_cloud_model_without_ollama(
    runtime: Path, fake: FakeOpenClaw
) -> None:
    write_activation(runtime, BOTH)
    runner = project_worker.openclaw_runner(runtime, ROOT, plain_text=True)
    result = runner("chef-operations", "Bonjour", "session-1", route="cloud")
    assert result == {"text": "Bonjour", "route": "cloud"}
    (command,) = fake.agent_commands()
    assert command[command.index("--model") + 1] == "cloudgw/z-ai/glm-5.3-flash"
    # Provider and allow-list were verified with the cloud route only.
    assert ["openclaw", "config", "get", "models.providers", "--json"] in fake.commands
    record = json.loads((runtime / "state/model-runs/session-1.json").read_text())
    assert record["route"] == "cloud" and record["provider"] == "cloudgw"
    assert record["model"] == "z-ai/glm-5.3-flash"
    assert record["usage"] == {"input": 12, "output": 5, "cacheRead": 0}
    # No message content is stored with the identity.
    assert "Bonjour" not in json.dumps(record)


def test_cloud_route_checks_the_model_that_really_answered(
    runtime: Path, fake: FakeOpenClaw
) -> None:
    write_activation(runtime, BOTH)
    runner = project_worker.openclaw_runner(runtime, ROOT, plain_text=True)
    fake.envelope = fake.reply("x", "ollama", "qwen3.5:9b-q4_K_M")
    with pytest.raises(RuntimeError, match="provider=cloudgw"):
        runner("chef-operations", "Bonjour", "s2", route="cloud")
    fake.envelope = fake.reply("x", "cloudgw", "some/other-model")
    with pytest.raises(RuntimeError, match="model=z-ai/glm-5.3-flash"):
        runner("chef-operations", "Bonjour", "s3", route="cloud")


@pytest.mark.parametrize(
    "tamper",
    [
        lambda f: f.providers["cloudgw"].update(baseUrl="https://openrouter.ai/api/v1"),
        lambda f: f.providers["cloudgw"].update(baseUrl="http://127.0.0.1:9999/v1"),
        lambda f: f.providers["cloudgw"].update(api="anthropic-messages"),
        lambda f: f.providers["cloudgw"]["models"][0].update(id="other/model"),
        lambda f: f.providers["cloudgw"].update(apiKey="sk-or-v1-literal-key"),
        lambda f: f.providers["cloudgw"].update(apiKey="__OPENCLAW_REDACTED__"),
        lambda f: f.providers["cloudgw"].update(
            apiKey={"source": "env", "provider": "default", "id": "OPENROUTER_API_KEY"}),
        lambda f: f.providers.pop("cloudgw"),
        lambda f: f.agents["defaults"]["modelPolicy"].update(allow=["ollama/qwen3.5:9b-q4_K_M"]),
    ],
)
def test_tampered_cloud_configuration_stops_the_run(
    runtime: Path, fake: FakeOpenClaw, tamper: Any
) -> None:
    write_activation(runtime, BOTH)
    tamper(fake)
    runner = project_worker.openclaw_runner(runtime, ROOT, plain_text=True)
    with pytest.raises(ValueError, match="route cloud refusée|jeton local"):
        runner("chef-operations", "Bonjour", "s4", route="cloud")
    assert fake.agent_commands() == []


def test_local_route_is_unchanged_and_never_selects_a_model(
    runtime: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeOpenClaw(runtime)
    fake.envelope = fake.reply("Salut", "ollama", "qwen3.5:9b-q4_K_M")
    monkeypatch.setattr(project_worker.subprocess, "run", fake)
    calls: list[str] = []

    def request(url: str) -> dict[str, Any]:
        calls.append(url)
        if url.endswith("/api/version"):
            return {"version": "0.35.1"}
        return {"models": [{"name": "qwen3.5:9b-q4_K_M", "digest": "sha256:" + "a" * 64,
                            "details": {"quantization_level": "Q4_K_M"}}]}

    monkeypatch.setattr(ollama_api, "request_json", request)
    monkeypatch.setattr(project_worker, "verify_model_lock", lambda *a, **k: None, raising=False)
    import clawfedora.model_identity as identity

    monkeypatch.setattr(identity, "verify_model_lock", lambda *a, **k: None)
    runner = project_worker.openclaw_runner(runtime, ROOT, plain_text=True)
    assert runner("chef-operations", "Bonjour", "local-1") == {"text": "Salut", "route": "local"}
    (command,) = fake.agent_commands()
    assert "--model" not in command
    assert calls[0] == "http://127.0.0.1:11434/api/version"
    assert json.loads((runtime / "state/model-runs/local-1.json").read_text())["route"] == "local"
    # A local turn never needs the cloud activation.
    assert cloud_status(runtime, ROOT) == (False, "cloud non activé")


TASK_PROMPT = 'task\n{"expected_outputs":["deliverables/task-one/file.md"]}'


def test_cloud_json_syntax_error_fails_without_a_second_cloud_call_when_ollama_is_down(
    runtime: Path, fake: FakeOpenClaw, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_activation(runtime, BOTH)

    def down(url: str) -> dict[str, Any]:
        raise ConnectionRefusedError(url)

    monkeypatch.setattr(ollama_api, "request_json", down)
    runner = project_worker.openclaw_runner(runtime, ROOT)
    fake.envelope = fake.reply("pas du json", "cloudgw", "z-ai/glm-5.3-flash")
    with pytest.raises(ValueError, match="réparation locale indisponible"):
        runner("ingenieur-devops", TASK_PROMPT, "s5", route="cloud")
    # The gateway was called once: a repair never triggers a second billed call.
    assert len(fake.agent_commands()) == 1


def test_cloud_json_syntax_error_is_repaired_by_the_local_model(
    runtime: Path, fake: FakeOpenClaw, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_activation(runtime, BOTH)
    repaired = {"files": {"deliverables/task-one/file.md": "ok"}, "summary": "ok"}

    def request(url: str) -> dict[str, Any]:
        if url.endswith("/api/version"):
            return {"version": "0.35.1"}
        return {"models": [{"name": "qwen3.5:9b-q4_K_M", "digest": "sha256:" + "a" * 64,
                            "details": {"quantization_level": "Q4_K_M"}}]}

    import clawfedora.model_identity as identity

    monkeypatch.setattr(ollama_api, "request_json", request)
    monkeypatch.setattr(identity, "verify_model_lock", lambda *a, **k: None)
    seen: dict[str, Any] = {}

    def repair(text: str, schema: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        seen.update(text=text, model=kwargs["model"])
        return repaired

    monkeypatch.setattr(project_worker, "repair_response", repair)
    runner = project_worker.openclaw_runner(runtime, ROOT)
    fake.envelope = fake.reply("pas du json", "cloudgw", "z-ai/glm-5.3-flash")
    assert runner("ingenieur-devops", TASK_PROMPT, "s6", route="cloud") == repaired
    assert seen == {"text": "pas du json", "model": "qwen3.5:9b-q4_K_M"}
    assert len(fake.agent_commands()) == 1
    record = json.loads((runtime / "state/response-repairs/s6.json").read_text())
    assert record["route"] == "cloud" and record["model"] == "qwen3.5:9b-q4_K_M"


def test_gateway_token_is_stable_private_and_always_in_the_environment(runtime: Path) -> None:
    token = ensure_gateway_token(runtime)
    assert len(token) >= 32 and ensure_gateway_token(runtime) == token
    path = runtime / "state/cloud/gateway.token"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE((runtime / "state/cloud").stat().st_mode) == 0o700
    env = openclaw_environment(runtime)
    assert env[CLOUD_TOKEN_ENV] == token
    # No upstream key is ever provided to OpenClaw by the environment builder.
    assert "OPENROUTER_API_KEY" not in env


def test_gateway_token_is_not_written_outside_a_managed_runtime(tmp_path: Path) -> None:
    value = ensure_gateway_token(tmp_path)
    assert len(value) >= 32
    assert not (tmp_path / "state").exists()
    assert openclaw_environment(tmp_path)[CLOUD_TOKEN_ENV]
    assert not (tmp_path / "state").exists()


def test_a_short_token_file_is_rejected_not_silently_replaced(runtime: Path) -> None:
    ensure_gateway_token(runtime)
    (runtime / "state/cloud/gateway.token").write_text("short\n")
    with pytest.raises(ValueError, match="jeton cloud invalide"):
        ensure_gateway_token(runtime)


def test_revoking_the_activation_switches_the_cloud_off(runtime: Path) -> None:
    write_activation(runtime, BOTH)
    assert cloud_status(runtime, ROOT) == (True, "cloud activé")
    revoke_activation(runtime)
    assert cloud_status(runtime, ROOT)[0] is False
    (runtime / "state/cloud/activation.json").write_text("not json")
    assert cloud_status(runtime, ROOT)[0] is False
