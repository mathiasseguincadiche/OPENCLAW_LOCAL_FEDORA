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


def test_only_three_read_only_commands_are_exposed() -> None:
    allowed = API["READ_ONLY_ACTIONS"]
    assert allowed == {"projects": "!projets", "status": "!etat", "help": "!aide"}
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
