"""The Open WebUI action toolbar is read-only, authenticated and loopback-only."""

from __future__ import annotations

import asyncio
import json
import runpy
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
API = runpy.run_path(str(ROOT / "plugins/openwebui/clawfedora_project_actions.py"))


def test_only_five_read_only_commands_are_exposed() -> None:
    allowed = API["READ_ONLY_ACTIONS"]
    assert allowed == {
        "projects": "!projets", "status": "!etat",
        "help": "!aide", "models": "!modele", "budget": "!budget",
    }
    with pytest.raises(ValueError, match="non autorisée"):
        API["read_only_bridge"]("!livrer", [], key="x" * 64)
    with pytest.raises(ValueError, match="jeton"):
        API["read_only_bridge"]("!etat", [], key="")


def test_bridge_request_cannot_send_control_plane_commands(monkeypatch: Any) -> None:
    import http.client

    captured: list[dict[str, Any]] = []

    class FakeResponse:
        status = 200

        def read(self, limit: int) -> bytes:
            assert limit == 64001
            return json.dumps(
                {"choices": [{"message": {"content": "Projet actif : lab"}}]}
            ).encode()

    class FakeConnection:
        def __init__(self, host: str, port: int, timeout: int) -> None:
            assert (host, port, timeout) == ("127.0.0.1", 18891, 8)

        def request(
            self, method: str, path: str, body: bytes, headers: dict[str, str]
        ) -> None:
            assert (method, path) == ("POST", "/v1/chat/completions")
            assert headers["Authorization"] == "Bearer " + "x" * 64
            captured.append(json.loads(body))

        def getresponse(self) -> FakeResponse:
            return FakeResponse()

        def close(self) -> None:
            pass

    monkeypatch.setattr(http.client, "HTTPConnection", FakeConnection)
    answer = API["read_only_bridge"](
        "!etat",
        [
            {"role": "user", "content": "secret-in-history"},
            {"role": "assistant", "content": "📁 Projet : lab\n\nBonjour"},
            {"role": "user", "content": "another-private-prompt"},
        ],
        key="x" * 64
    )
    assert answer == "Projet actif : lab"
    assert captured[0]["model"] == "openclaw/chef-operations"
    assert captured[0]["messages"][-1] == {"role": "user", "content": "!etat"}
    assert captured[0]["messages"][0] == {"role": "assistant", "content": "📁 Projet : lab"}
    assert len(captured[0]["messages"]) == 2
    assert "private" not in json.dumps(captured[0])
    assert "secret-in-history" not in json.dumps(captured[0])


def test_action_buttons_require_admin_and_never_approve(monkeypatch: Any) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "x" * 64)
    commands: list[str] = []
    notices: list[dict[str, Any]] = []

    def fake_call(cmd: str, history: object, *, key: str, port: int = 18891) -> str:
        commands.append(cmd)
        assert key == "x" * 64
        assert history == [{"role": "user", "content": "Bonjour"}]
        return "Etat du projet"

    monkeypatch.setitem(API["read_only_bridge"].__globals__, "read_only_bridge", fake_call)

    async def capture(event: dict[str, Any]) -> None:
        notices.append(event)

    action = API["Action"]()
    body = {"messages": [{"role": "user", "content": "Bonjour"}]}
    with pytest.raises(ValueError, match="interdite"):
        asyncio.run(
            action.action(body, __id__="status", __user__={"role": "pending"})
        )
    with pytest.raises(ValueError, match="interdite"):
        asyncio.run(
            action.action(body, __id__="livrer", __user__={"role": "admin"})
        )
    asyncio.run(
        action.action(
            body, __id__="status", __user__={"role": "admin"}, __event_emitter__=capture
        )
    )
    assert commands == ["!etat"]
    assert notices[0]["type"] == "notification"
    assert "Etat" in notices[0]["data"]["content"]


def test_mutating_button_requires_positive_browser_confirmation(monkeypatch: Any) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "x" * 64)
    commands: list[str] = []
    prompts: list[dict[str, Any]] = []
    emitted: list[dict[str, Any]] = []
    history = [
        {"role": "user", "content": "super-secret-private-prompt"},
        {"role": "assistant", "content": "📁 Projet : mon-projet\\n\\nTravail demandé"},
    ]

    def fake_bridge(
        command: str, messages: object, *, key: str, mutation: bool, port: int = 18891
    ) -> str:
        assert mutation is True and key == "x" * 64
        assert messages == history
        commands.append(command)
        return "Projet : action confirmée dans le pont"

    monkeypatch.setitem(API["local_bridge"].__globals__, "local_bridge", fake_bridge)

    async def confirm(event: dict[str, Any]) -> bool:
        prompts.append(event)
        return True

    async def notify(event: dict[str, Any]) -> None:
        emitted.append(event)

    action = API["Action"]()
    asyncio.run(action.action(
        {"messages": history}, __id__="start", __user__={"role": "admin"},
        __event_call__=confirm, __event_emitter__=notify,
    ))
    assert commands == ["!lancer"]
    assert prompts == [{"type": "confirmation", "data": {
        "title": "Action de projet", "message": "Démarrer les tâches du projet approuvé ?",
    }}]
    assert emitted[0]["data"]["type"] == "info"

    # A declined dialog and an error from a disconnected browser MUST NOT act.
    for reply in (False, None, {"error": "Client session disconnected."}, {"ok": True}):
        async def refuse(_event: dict[str, Any], answer: Any = reply) -> Any:
            return answer
        asyncio.run(action.action(
            {"messages": history}, __id__="deliver", __user__={"role": "admin"},
            __event_call__=refuse, __event_emitter__=notify,
        ))
    assert commands == ["!lancer"]


def test_mutating_button_requires_admin_project_and_callback(monkeypatch: Any) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "x" * 64)
    action = API["Action"]()
    messages = [{"role": "assistant", "content": "📁 Projet : projet-valide"}]

    async def approved(_event: dict[str, Any]) -> bool:
        return True

    with pytest.raises(ValueError, match="interdite"):
        asyncio.run(action.action(
            {"messages": messages}, __id__="pause", __user__={"role": "user"},
            __event_call__=approved,
        ))
    with pytest.raises(ValueError, match="non sélectionné"):
        asyncio.run(action.action(
            {"messages": [{"role": "user", "content": "pas de projet"}]},
            __id__="pause", __user__={"role": "admin"}, __event_call__=approved,
        ))
    with pytest.raises(ValueError, match="indisponible"):
        asyncio.run(action.action(
            {"messages": messages}, __id__="pause", __user__={"role": "admin"},
        ))


def test_mutations_send_only_fixed_commands_and_project_marker(monkeypatch: Any) -> None:
    import http.client

    payloads: list[dict[str, Any]] = []

    class FakeResponse:
        status = 200

        def read(self, limit: int) -> bytes:
            return json.dumps({"choices": [{"message": {"content": "OK"}}]}).encode()

    class FakeConnection:
        def __init__(self, host: str, port: int, timeout: int) -> None:
            assert (host, port, timeout) == ("127.0.0.1", 18891, 8)

        def request(
            self, method: str, path: str, body: bytes, headers: dict[str, str]
        ) -> None:
            assert method == "POST" and path == "/v1/chat/completions"
            assert headers["Authorization"] == "Bearer " + "x" * 64
            payloads.append(json.loads(body))

        def getresponse(self) -> FakeResponse:
            return FakeResponse()

        def close(self) -> None:
            return None

    monkeypatch.setattr(http.client, "HTTPConnection", FakeConnection)
    history = [
        {"role": "user", "content": "my-sensitive-terraform-creds"},
        {"role": "assistant", "content": "📁 Projet : test-sans-secret\\n\\nprivate text"},
        {"role": "user", "content": "another confidential note"},
    ]
    assert API["local_bridge"](
        "!analyser", history, key="x" * 64, mutation=True
    ) == "OK"
    assert payloads == [{"model": "openclaw/chef-operations", "stream": False,
        "messages": [
            {"role": "assistant", "content": "📁 Projet : test-sans-secret"},
            {"role": "user", "content": "!analyser"},
        ]}]
    for command in ("!modifier 1 please", "!livrer maintenant", "!creer secret"):
        with pytest.raises(ValueError, match="non autorisée"):
            API["local_bridge"](command, history, key="x" * 64, mutation=True)
    assert len(payloads) == 1
