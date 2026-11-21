"""Owned native Open WebUI folder -> signed local ClawFedora context.

The pinned WebUI ORM is mocked, while the ClawFedora bridge itself is real.
The project file tree, remote providers and personal chats are not mutated.
"""

from __future__ import annotations

import asyncio
import json
import runpy
import sys
import threading
import time
from http.client import HTTPConnection
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from test_daily_worker import planned as planned

from clawfedora.webui_bridge import MODEL_IDS, make_server
from clawfedora.webui_folder_binding import resolve

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "c" * 64
PROJECT = "daily-project"
CHAT = "chat-12345678"
USER = {"role": "admin", "id": "admin-1"}


@pytest.fixture
def native_filter(monkeypatch: pytest.MonkeyPatch) -> tuple[Any, SimpleNamespace]:
    state = SimpleNamespace(
        folders={
            "root": SimpleNamespace(
                id="root", parent_id=None, meta={
                    "clawfedora_schema": 1,
                    "clawfedora_folder_kind": "root",
                },
            ),
            "managed": SimpleNamespace(
                id="managed", parent_id="root", meta={
                    "clawfedora_schema": 1,
                    "clawfedora_folder_kind": "project",
                    "clawfedora_project_id": PROJECT,
                },
            ),
            "personal": SimpleNamespace(
                id="personal", parent_id=None, meta=None,
            ),
        },
        chats={
            CHAT: SimpleNamespace(
                id=CHAT, user_id="admin-1", folder_id="managed",
            )
        },
    )
    for name in ("open_webui", "open_webui.models"):
        module = ModuleType(name)
        module.__path__ = []
        monkeypatch.setitem(sys.modules, name, module)

    class Files:
        @staticmethod
        async def get_file_by_id_and_user_id(_file_id: str, _user_id: str) -> None:
            return None

    class Chats:
        @staticmethod
        async def get_chat_by_id_and_user_id(chat_id: str, user_id: str) -> Any:
            found = state.chats.get(chat_id)
            if found is None or found.user_id != user_id:
                return None
            return found

    class Folders:
        @staticmethod
        async def get_folder_by_id_and_user_id(folder_id: str, user_id: str) -> Any:
            if user_id != USER["id"]:
                return None
            return state.folders.get(folder_id)

    for name, class_name, klass in (
        ("open_webui.models.files", "Files", Files),
        ("open_webui.models.chats", "Chats", Chats),
        ("open_webui.models.folders", "Folders", Folders),
    ):
        module = ModuleType(name)
        setattr(module, class_name, klass)
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setenv("OPENAI_API_KEY", TOKEN)
    api = runpy.run_path(str(ROOT / "plugins/openwebui/clawfedora_files.py"))
    return api["Filter"](), state


def _body(text: str, *, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    return {
        "model": MODEL_IDS[0],
        "metadata": {"chat_id": CHAT},
        "messages": [*(history or []), {"role": "user", "content": text}],
    }


def _filter(filter_instance: Any, body: dict[str, Any], user: Any = USER) -> dict[str, Any]:
    return asyncio.run(filter_instance.inlet(body, __user__=user))


@pytest.fixture
def local_server(
    planned: tuple[Path, Path],
) -> Any:
    runtime, _project = planned
    calls: list[str] = []

    def runner(_role: str, prompt: str, _session: str) -> dict[str, Any]:
        calls.append(prompt)
        return {"text": "Réponse locale de contrôle."}

    server = make_server(ROOT, runtime, TOKEN, 0, runner=runner)
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True
    )
    thread.start()
    try:
        yield server, calls, runtime
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _request(server: Any, body: dict[str, Any]) -> tuple[int, str]:
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    connection.request(
        "POST", "/v1/chat/completions", json.dumps(body),
        headers={
            "Authorization": "Bearer " + TOKEN,
            "Content-Type": "application/json",
        },
    )
    response = connection.getresponse()
    result = json.loads(response.read())
    connection.close()
    if response.status == 200:
        return response.status, result["choices"][0]["message"]["content"]
    return response.status, result["error"]["message"]


def test_owned_saved_folder_is_selected_without_explicit_project_command(
    native_filter: tuple[Any, SimpleNamespace],
    local_server: tuple[Any, list[str], Path],
) -> None:
    filter_instance, _state = native_filter
    server, calls, runtime = local_server
    body = _filter(filter_instance, _body("Comment fonctionne mon projet ?"))
    signed = body["clawfedora_folder_binding"]
    assert signed["project_id"] == PROJECT
    assert signed["chat_id"] == CHAT
    assert signed["user_id"] == USER["id"]
    assert resolve(body, TOKEN, runtime) == PROJECT
    code, text = _request(server, body)
    assert code == 200
    assert text.startswith("📁 Projet : daily-project\n\n")
    assert len(calls) == 1
    assert '"id": "daily-project"' in calls[0]
    assert "lecture seule" in calls[0]


def test_explicit_marker_conflict_refuses_before_llm_or_mutation(
    native_filter: tuple[Any, SimpleNamespace],
    local_server: tuple[Any, list[str], Path],
) -> None:
    filter_instance, _state = native_filter
    server, calls, _runtime = local_server
    body = _filter(filter_instance, _body(
        "Bonjour", history=[
            {"role": "assistant", "content": "📁 Projet : autre-projet\n\nUn ancien fil"}
        ],
    ))
    code, message = _request(server, body)
    assert code == 400 and "incompatibles" in message
    assert calls == []


@pytest.mark.parametrize("text", ["!projet autre-projet", "!quitter"])
def test_folder_cannot_be_overridden_by_commands(
    native_filter: tuple[Any, SimpleNamespace],
    local_server: tuple[Any, list[str], Path],
    text: str,
) -> None:
    filter_instance, _state = native_filter
    server, calls, _runtime = local_server
    code, answer = _request(server, _filter(filter_instance, _body(text)))
    assert code == 200
    assert "reclasser" in answer and answer.startswith("📁 Projet : daily-project")
    assert calls == []


def test_forged_expired_or_modified_binding_is_refused(
    native_filter: tuple[Any, SimpleNamespace],
    local_server: tuple[Any, list[str], Path],
) -> None:
    filter_instance, _state = native_filter
    server, calls, runtime = local_server
    body = _filter(filter_instance, _body("Analyse en lecture seule"))
    for altered in (
        {**body, "clawfedora_folder_binding": {
            **body["clawfedora_folder_binding"], "project_id": "another-project",
        }},
        {**body, "clawfedora_folder_binding": {
            **body["clawfedora_folder_binding"], "issued_at": int(time.time()) - 1000,
        }},
        {**body, "messages": [{"role": "user", "content": "Message remplacé"}]},
    ):
        with pytest.raises(ValueError):
            resolve(altered, TOKEN, runtime)
        assert _request(server, altered)[0] == 400
    assert calls == []


def test_existing_unmanaged_and_unknown_chats_keep_manual_selection(
    native_filter: tuple[Any, SimpleNamespace],
    local_server: tuple[Any, list[str], Path],
) -> None:
    filter_instance, state = native_filter
    server, calls, _runtime = local_server
    state.chats[CHAT].folder_id = "personal"
    body = _filter(filter_instance, _body("Bonjour"))
    assert "clawfedora_folder_binding" not in body
    code, text = _request(server, body)
    assert code == 200 and "Réponse locale de contrôle." in text
    assert len(calls) == 1 and '"id": "daily-project"' not in calls[0]
    state.chats[CHAT].folder_id = "managed"
    unknown = _body("Bonjour")
    unknown["metadata"]["chat_id"] = "chat-unknown123"
    assert "clawfedora_folder_binding" not in _filter(filter_instance, unknown)
    assert "clawfedora_folder_binding" not in _filter(
        filter_instance, _body("Bonjour"), {"role": "user", "id": USER["id"]}
    )


def test_owner_root_and_metadata_are_checked_without_touching_user_folders(
    native_filter: tuple[Any, SimpleNamespace],
) -> None:
    filter_instance, state = native_filter
    state.chats[CHAT].user_id = "another-account"
    assert "clawfedora_folder_binding" not in _filter(filter_instance, _body("x"))
    state.chats[CHAT].user_id = USER["id"]
    state.folders["managed"].parent_id = "personal"
    with pytest.raises(ValueError, match="racine"):
        _filter(filter_instance, _body("x"))
    state.folders["managed"].parent_id = "root"
    state.folders["managed"].meta["clawfedora_project_id"] = "../escape"
    with pytest.raises(ValueError, match="métadonnées"):
        _filter(filter_instance, _body("x"))


def test_spoofed_field_is_discarded_and_metadata_mismatch_fails_closed(
    native_filter: tuple[Any, SimpleNamespace],
) -> None:
    filter_instance, _ = native_filter
    body = _body("Vérifier")
    body["clawfedora_folder_binding"] = {
        "project_id": "another-project", "signature": "fake"
    }
    revised = _filter(filter_instance, body)
    assert revised["clawfedora_folder_binding"]["project_id"] == PROJECT
    with pytest.raises(ValueError, match="contradictoires"):
        asyncio.run(filter_instance.inlet(
            _body("Bonjour"),
            __user__=USER,
            __metadata__={"chat_id": "chat-another123"},
        ))


def test_new_unsaved_chat_can_still_use_explicit_project_selection(
    native_filter: tuple[Any, SimpleNamespace],
    local_server: tuple[Any, list[str], Path],
) -> None:
    filter_instance, _state = native_filter
    server, calls, _runtime = local_server
    body = _body("!projet daily-project")
    body["metadata"]["chat_id"] = "local:temporary"
    filtered = _filter(filter_instance, body)
    assert "clawfedora_folder_binding" not in filtered
    code, answer = _request(server, filtered)
    assert code == 200 and answer.startswith("📁 Projet : daily-project · pont")
    assert calls == []
