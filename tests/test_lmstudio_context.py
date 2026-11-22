from __future__ import annotations

import json
import shutil
import subprocess
import threading
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

import pytest

from clawfedora.lmstudio_context import resolve
from clawfedora.webui_bridge import MODEL_IDS, make_server

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "a" * 64


def _project(runtime: Path, name: str = "opsdesk") -> None:
    directory = runtime / "projects" / name
    directory.mkdir(parents=True)
    (directory / "project.json").write_text(
        json.dumps({"id": name, "title": name, "status": "INTAKE_READY"}),
        encoding="utf-8",
    )


def _request(server: Any, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    conn = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    conn.request(
        "POST",
        "/v1/chat/completions",
        body=json.dumps(payload),
        headers={
            "Authorization": "Bearer " + TOKEN,
            "Content-Type": "application/json",
        },
    )
    response = conn.getresponse()
    status, body = response.status, json.loads(response.read())
    conn.close()
    return status, body


def test_explicit_per_chat_project_is_read_only_and_cannot_switch(tmp_path: Path) -> None:
    _project(tmp_path)
    request = {"clawfedora_lmstudio_project": "opsdesk"}
    assert resolve(
        request, tmp_path, previous=None, referenced=set(), native_webui=None,
    ) == "opsdesk"
    assert resolve(
        {}, tmp_path, previous="opsdesk", referenced={"opsdesk"}, native_webui=None,
    ) is None
    assert resolve(
        request, tmp_path, previous="opsdesk", referenced={"opsdesk"}, native_webui=None,
    ) == "opsdesk"
    with pytest.raises(ValueError, match="nouvelle conversation"):
        resolve(
            request, tmp_path, previous="ancien", referenced={"ancien"},
            native_webui=None,
        )
    with pytest.raises(ValueError, match="nouvelle conversation"):
        resolve(
            request, tmp_path, previous="opsdesk",
            referenced={"ancien", "opsdesk"}, native_webui=None,
        )
    with pytest.raises(ValueError, match="ne peuvent pas"):
        resolve(
            request, tmp_path, previous=None, referenced=set(),
            native_webui="opsdesk",
        )


@pytest.mark.parametrize(
    "invalid",
    ["../../etc", "OpsDesk", " opsdesk ", "", True, None, 1, "a" * 70],
)
def test_context_refuses_invalid_or_missing_project(
    tmp_path: Path, invalid: Any,
) -> None:
    _project(tmp_path)
    with pytest.raises(ValueError):
        resolve(
            {"clawfedora_lmstudio_project": invalid}, tmp_path,
            previous=None, referenced=set(), native_webui=None,
        )


def test_context_rejects_missing_and_symlinked_projects(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="projet absent"):
        resolve(
            {"clawfedora_lmstudio_project": "opsdesk"}, tmp_path,
            previous=None, referenced=set(), native_webui=None,
        )
    external = tmp_path / "elsewhere"
    external.mkdir()
    (tmp_path / "projects").mkdir()
    (tmp_path / "projects/opsdesk").symlink_to(external, target_is_directory=True)
    with pytest.raises(ValueError, match="projet absent"):
        resolve(
            {"clawfedora_lmstudio_project": "opsdesk"}, tmp_path,
            previous=None, referenced=set(), native_webui=None,
        )


def test_bridge_lmstudio_project_applies_to_direct_human_command(
    tmp_path: Path,
) -> None:
    _project(tmp_path)
    called: list[str] = []

    def runner(*_args: Any) -> dict[str, str]:
        called.append("model")
        return {"text": "unused"}

    with make_server(ROOT, tmp_path, TOKEN, 0, runner=runner) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        payload: dict[str, Any] = {
            "model": MODEL_IDS[0],
            "clawfedora_lmstudio_project": "opsdesk",
            "messages": [{"role": "user", "content": "!aide"}],
        }
        status, body = _request(server, payload)
        assert status == 200
        text = body["choices"][0]["message"]["content"]
        assert text.startswith("📁 Projet : opsdesk · pont")
        assert "Commandes du pont" in text
        status, body = _request(
            server, {**payload, "messages": [
                {"role": "assistant", "content": "📁 Projet : ancien · pont\n\nancien"},
                {"role": "user", "content": "!aide"},
            ]},
        )
        assert status == 400
        assert "nouvelle conversation" in body["error"]["message"]
        status, body = _request(
            server, {**payload, "messages": [
                {"role": "user", "content": "!projet ancien"},
            ]},
        )
        assert status == 200
        assert "nouvelle conversation" in body["choices"][0]["message"]["content"]
        status, _ = _request(
            server, {**payload, "clawfedora_lmstudio_project": "other-project"},
        )
        assert status == 400
        server.shutdown()
        thread.join(timeout=5)
    assert not called, "Human commands must not become agent model instructions"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js absent")
def test_lmstudio_contract_node_offline() -> None:
    plugin = ROOT / "plugins/lmstudio-clawfedora"
    result = subprocess.run(
        ["node", "--test", str(plugin / "tests/contract.test.mjs")],
        cwd=plugin, capture_output=True, text=True, timeout=20, check=False,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
