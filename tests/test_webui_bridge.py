from __future__ import annotations

import json
import threading
from contextlib import closing
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

import pytest

from clawfedora.project_worker import worker_lock
from clawfedora.webui_bridge import MODEL_IDS, chat_prompt, make_server
from clawfedora.webui_setup import environment, render, seal

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "a" * 64


def request(server: Any, path: str, data: Any = None, token: str = TOKEN) -> tuple[int, str]:
    conn = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    conn.request(
        "GET" if data is None else "POST",
        path,
        body=None if data is None else json.dumps(data),
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    )
    response = conn.getresponse()
    result = response.status, response.read().decode()
    conn.close()
    return result


def test_bridge_preserves_admission_and_never_exposes_gateway_auth(tmp_path: Path) -> None:
    called: list[str] = []

    def runner(role: str, prompt: str, _session: str) -> dict[str, Any]:
        called.append(role)
        assert "aucun changement d’état" in prompt
        with pytest.raises(ValueError, match="déjà actif"), worker_lock(tmp_path):
            pass
        return {"text": "Vérifier le service et ses journaux."}

    with make_server(ROOT, tmp_path, TOKEN, 0, runner=runner) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        payload = {
            "model": MODEL_IDS[0],
            "messages": [{"role": "user", "content": "Comment diagnostiquer ?"}],
        }
        assert request(server, "/v1/models", token="wrong")[0] == 401
        assert len(json.loads(request(server, "/v1/models")[1])["data"]) == 7
        assert not called
        assert request(server, "/unknown")[0] == 404
        assert request(server, "/unknown", payload)[0] == 404
        status, raw = request(server, "/v1/chat/completions", payload)
        assert status == 200 and json.loads(raw)["choices"][0]["message"]["content"]
        assert request(server, "/v1/chat/completions", payload, token="wrong")[0] == 401
        with worker_lock(tmp_path):
            assert request(server, "/v1/chat/completions", payload)[0] == 409
            assert request(server, "/v1/models")[0] == 200
        (tmp_path / "state/gaming-mode").touch()
        assert request(server, "/v1/chat/completions", payload)[0] == 409
        (tmp_path / "state/gaming-mode").unlink()
        status, raw = request(server, "/v1/chat/completions", {**payload, "stream": True})
        assert status == 200 and "data: [DONE]" in raw
        assert "chat.completion.chunk" in raw and "stop" in raw
        assert request(server, "/v1/chat/completions", {**payload, "model": "gpt-cloud"})[0] == 400
        server.shutdown()
        thread.join(timeout=5)
    assert called == ["chef-operations"] * 2


@pytest.mark.parametrize(
    "patch",
    [
        {"model": "ollama/other"},
        {"max_tokens": 4097},
        {"stream": "true"},
        {"messages": []},
        {"messages": [{"role": "tool", "content": "x"}]},
        {"messages": [{"role": "user", "content": [{"type": "image_url"}]}]},
        {"messages": [{"role": "user", "content": "x" * 32001}]},
    ],
)
def test_bridge_rejects_bypass_and_oversized_context(patch: dict[str, Any]) -> None:
    payload = {"model": MODEL_IDS[0], "messages": [{"role": "user", "content": "x"}], **patch}
    with pytest.raises(ValueError):
        chat_prompt(payload)


def test_bridge_defaults_match_the_daily_limits_contract() -> None:
    from clawfedora import webui_bridge
    from clawfedora.core_config import daily_limits

    budget = daily_limits(ROOT)
    assert webui_bridge.DEFAULT_MAX_TOKENS == budget["max_output_tokens"] == 4096
    assert budget["max_history_bytes"] == webui_bridge.DEFAULT_HISTORY_BYTES
    assert budget["context_tokens"] == 32768
    role, _prompt = chat_prompt(
        {"model": MODEL_IDS[0], "max_tokens": 4096, "messages": [{"role": "user", "content": "x"}]}
    )
    assert role == "chef-operations"


def test_read_endpoint_remains_responsive_while_chat_is_running(tmp_path: Path) -> None:
    entered, release = threading.Event(), threading.Event()

    def runner(*_args: Any) -> dict[str, Any]:
        entered.set()
        assert release.wait(timeout=4)
        return {"text": "Terminé"}

    with make_server(ROOT, tmp_path, TOKEN, 0, runner=runner) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        payload = {"model": MODEL_IDS[0], "messages": [{"role": "user", "content": "x"}]}
        chat = threading.Thread(target=request, args=(server, "/v1/chat/completions", payload))
        chat.start()
        assert entered.wait(timeout=2)
        assert request(server, "/v1/models")[0] == 200
        assert request(server, "/v1/chat/completions", payload)[0] == 409
        release.set()
        chat.join(timeout=3)
        server.shutdown()
        thread.join(timeout=3)


def test_setup_pins_limits_preserves_secrets_and_closes_registration(tmp_path: Path) -> None:
    import sqlite3

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / ".openclaw-fedora-runtime").touch()
    units = tmp_path / "units"
    value = render(ROOT, runtime, units)
    state = runtime / "state/webui"
    first = (state / "bridge.token").read_text()
    render(ROOT, runtime, units)
    assert first == (state / "bridge.token").read_text()
    assert (state / "webui.env").stat().st_mode & 0o077 == 0
    service = (units / "clawfedora-webui.service").read_text()
    assert "sha256:" in service and "--memory 3g --cpus 2" in service
    assert "--network host" in service and ":Z" in service and "--privileged" not in service
    assert "ENABLE_OLLAMA_API=false" in (state / "webui.env").read_text()
    assert value["sealed"] is False
    with closing(sqlite3.connect(state / "data/webui.db")) as db, db:
        db.execute('CREATE TABLE "user" (id TEXT, role TEXT)')
        db.execute(
            'CREATE TABLE "function" ('
            'id TEXT PRIMARY KEY, user_id TEXT, name TEXT, type TEXT, content TEXT, '
            'meta TEXT, valves TEXT, is_active INTEGER, is_global INTEGER, '
            'updated_at INTEGER, created_at INTEGER)'
        )
        db.execute('INSERT INTO "user" VALUES ("admin-id", "pending")')
    with (
        pytest.raises(ValueError, match="un seul compte"),
        sqlite3.connect(state / "data/webui.db") as db,
    ):
        seal(ROOT, runtime)
    with closing(sqlite3.connect(state / "data/webui.db")) as db, db:
        db.execute('UPDATE "user" SET role="admin"')
    seal(ROOT, runtime)
    assert render(ROOT, runtime, units)["sealed"] is True
    assert "ENABLE_SIGNUP=false" in (state / "webui.env").read_text()
    settings = environment(ROOT, TOKEN, "b" * 64, "c" * 64, sealed=True)
    assert settings["HOST"] == "127.0.0.1"
    assert settings["USER_PERMISSIONS_CHAT_FILE_UPLOAD"] == "true"
    assert settings["USER_PERMISSIONS_CHAT_STT"] == "true"
    assert settings["USER_PERMISSIONS_CHAT_TTS"] == "true"
    assert settings["USER_PERMISSIONS_CHAT_CALL"] == "false"
    assert settings["AUDIO_STT_OPENAI_API_BASE_URL"] == "http://127.0.0.1:18893/v1"
    assert settings["AUDIO_TTS_OPENAI_API_BASE_URL"] == "http://127.0.0.1:18893/v1"
    assert "clawfedora-speech.service" in (units / "clawfedora-webui.service").read_text()
    with closing(sqlite3.connect(state / "data/webui.db")) as db:
        row = db.execute(
            'SELECT type, is_active, is_global FROM "function" WHERE id="clawfedora_files"'
        ).fetchone()
    assert row == ("filter", 1, 1)
    assert all(
        settings[key] == "false"
        for key in (
            "ENABLE_CODE_EXECUTION",
            "ENABLE_AUTOMATIONS",
            "ENABLE_SUBAGENTS",
            "ENABLE_PERSISTENT_CONFIG",
        )
    )


def test_client_tool_catalog_and_overrides_are_never_forwarded() -> None:
    role, prompt = chat_prompt(
        {
            "model": MODEL_IDS[0],
            "messages": [{"role": "user", "content": "Bonjour"}],
            "tools": [{"name": "exec", "description": "UNTRUSTED_TOOL"}],
            "base_url": "https://cloud.invalid",
            "user": "OPERATOR_SESSION",
            "extra_body": {"model": "REMOTE_MODEL"},
        }
    )
    assert role == "chef-operations"
    assert all(
        value not in prompt
        for value in ("UNTRUSTED_TOOL", "cloud.invalid", "OPERATOR_SESSION", "REMOTE_MODEL")
    )


def test_maintenance_refuses_active_inference_and_reuses_inherited_lock(tmp_path: Path) -> None:
    import os
    import subprocess

    (tmp_path / ".openclaw-fedora-runtime").touch()
    script = ROOT / "scripts/linux/lib/runtime.sh"
    env = {**os.environ, "OPENCLAW_LOCAL_FEDORA_ROOT": str(tmp_path)}
    with worker_lock(tmp_path):
        result = subprocess.run(
            ["bash", "-c", 'source "$1"; claw_lock_worker', "maintenance", str(script)],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 2 and "discussion active" in result.stderr
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; claw_lock_worker; bash -c \'source "$1"; claw_lock_worker\' child "$1"',
            "maintenance",
            str(script),
        ],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_chat_uses_approved_notes_and_displays_history_omission(tmp_path: Path) -> None:
    from clawfedora.mentor import save_profile

    save_profile(tmp_path, {"human_approved": True, "background": "Administrateur Linux"})
    captured = []

    def runner(_role: str, prompt: str, _session: str) -> dict[str, Any]:
        captured.append(prompt)
        return {"text": "Vérifions une observation."}

    with make_server(ROOT, tmp_path, TOKEN, 0, runner=runner) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        messages = [
            {"role": "user", "content": "old" + "x" * 31990},
            {"role": "user", "content": "Question actuelle"},
        ]
        status, raw = request(
            server, "/v1/chat/completions", {"model": MODEL_IDS[0], "messages": messages}
        )
        assert status == 200
        assert "Contexte allégé" in json.loads(raw)["choices"][0]["message"]["content"]
        assert "Administrateur Linux" in captured[0]
        models = json.loads(request(server, "/v1/models")[1])["data"]
        assert models[0]["name"] == "Mentor infrastructure/OPS"
        server.shutdown()
        thread.join(timeout=5)
