"""Recovery is an explicit archive operation, never a replay or a success verdict."""
from __future__ import annotations

import json
import threading
from collections.abc import Generator
from contextlib import closing
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

import pytest

from clawfedora import atelier_chat, atelier_chat_stream, dashboard
from clawfedora.chat_context import select_history
from clawfedora.project_worker import worker_lock

ROOT = Path(__file__).resolve().parents[1]


def _interrupted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    chat = atelier_chat.create(tmp_path, None, "chef-operations")

    def broken(*_args: Any) -> str:
        raise ValueError("interrupted")

    monkeypatch.setattr(atelier_chat, "_policy_answer", broken)
    with pytest.raises(ValueError, match="interrupted"):
        atelier_chat.send(ROOT, tmp_path, chat["id"], "!lancer")
    return atelier_chat.read(tmp_path, chat["id"])


def test_recovery_archives_without_replay_or_context_injection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat = _interrupted(tmp_path, monkeypatch)
    identifier = chat["id"]
    pending = chat["pending"]

    with pytest.raises(ValueError, match="confirmation"):
        atelier_chat.recover(tmp_path, identifier, pending, human_approved=False)
    assert atelier_chat.read(tmp_path, identifier) == chat
    with pytest.raises(ValueError, match="obsolète"):
        atelier_chat.recover(
            tmp_path, identifier, {**pending, "id": "a" * 32}, human_approved=True,
        )
    assert atelier_chat.read(tmp_path, identifier) == chat
    recovered = atelier_chat.recover(tmp_path, identifier, pending, human_approved=True)
    assert recovered["pending"] is None
    assert recovered["messages"] == []
    record = recovered["recoveries"][0]
    assert record["intent"] == pending
    assert record["outcome"] == "ABANDONED_UNCERTAIN"
    assert record["after_messages"] == 0
    assert atelier_chat.read(tmp_path, identifier) == recovered
    with pytest.raises(ValueError, match="obsolète"):
        atelier_chat.recover(tmp_path, identifier, pending, human_approved=True)

    def answer(_root: Path, _runtime: Path, doc: dict[str, Any], message: str) -> str:
        assert message == "Nouvelle question"
        history, _stats = select_history(doc["messages"], message)
        assert history == []
        return "Nouvelle réponse"

    monkeypatch.setattr(atelier_chat, "_policy_answer", answer)
    updated = atelier_chat.send(ROOT, tmp_path, identifier, "Nouvelle question")
    assert updated["messages"] == [
        {"role": "user", "content": "Nouvelle question"},
        {"role": "assistant", "content": "Nouvelle réponse"},
    ]
    assert updated["recoveries"] == recovered["recoveries"]


def test_recovery_refuses_active_worker_and_concurrent_stream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat = _interrupted(tmp_path, monkeypatch)
    identifier = chat["id"]
    pending = chat["pending"]
    with worker_lock(tmp_path), pytest.raises(ValueError, match="déjà actif"):
        atelier_chat.recover(tmp_path, identifier, pending, human_approved=True)
    assert atelier_chat.read(tmp_path, identifier) == chat
    atelier_chat.recover(tmp_path, identifier, pending, human_approved=True)
    monkeypatch.setattr(atelier_chat_stream, "enabled", lambda _: True)

    def source(*_args: Any) -> Generator[str, None, None]:
        yield "partiel"
        yield "suite"

    monkeypatch.setattr(atelier_chat_stream, "_bridge_deltas", source)
    with closing(atelier_chat_stream.stream(ROOT, tmp_path, identifier, "Question")) as events:
        assert next(events)["text"] == "partiel"
        current = atelier_chat.read(tmp_path, identifier)["pending"]
        assert current["id"] != pending["id"]
        with pytest.raises(ValueError, match="déjà en cours"):
            atelier_chat.recover(tmp_path, identifier, current, human_approved=True)
    assert atelier_chat.read(tmp_path, identifier)["pending"] == current
    with pytest.raises(ValueError, match="obsolète"):
        atelier_chat.recover(tmp_path, identifier, pending, human_approved=True)
    result = atelier_chat.recover(tmp_path, identifier, current, human_approved=True)
    assert result["messages"] == [] and len(result["recoveries"]) == 2


def test_legacy_intent_and_atomic_save_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat = atelier_chat.create(tmp_path, None, "chef-operations")
    chat["pending"] = {"message": "Ancien tour", "started": 10}
    chat["messages"] = [
        {"role": "user", "content": "Question passée"},
        {"role": "assistant", "content": "Réponse passée"},
    ]
    atelier_chat._save(tmp_path, chat)
    with monkeypatch.context() as patch:
        def disk_full(*_args: Any) -> None:
            raise OSError("disque plein")

        patch.setattr(atelier_chat.os, "replace", disk_full)
        with pytest.raises(OSError, match="disque plein"):
            atelier_chat.recover(tmp_path, chat["id"], chat["pending"], human_approved=True)
    assert atelier_chat.read(tmp_path, chat["id"]) == chat
    result = atelier_chat.recover(tmp_path, chat["id"], chat["pending"], human_approved=True)
    assert result["messages"] == chat["messages"]
    assert result["recoveries"][0]["after_messages"] == 2
    assert result["recoveries"][0]["intent"] == chat["pending"]
    assert result["pending"] is None


def test_recovery_http_requires_origin_and_exact_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat = _interrupted(tmp_path, monkeypatch)

    with dashboard.make_server(ROOT, tmp_path, 0) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            def post(payload: dict[str, Any], *, origin: bool = True) -> tuple[int, Any]:
                conn = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                headers = {"Content-Type": "application/json"}
                if origin:
                    headers["Origin"] = f"http://127.0.0.1:{server.server_port}"
                try:
                    conn.request("POST", "/api/chat/recover", json.dumps(payload), headers)
                    response = conn.getresponse()
                    return response.status, json.loads(response.read())
                finally:
                    conn.close()

            payload = {
                "id": chat["id"], "pending": chat["pending"], "human_approved": True,
            }
            assert post(payload, origin=False)[0] == 403
            assert post({**payload, "human_approved": "true"})[0] == 400
            assert post({**payload, "replay": True})[0] == 400
            assert atelier_chat.read(tmp_path, chat["id"]) == chat
            status, result = post(payload)
            assert status == 200 and result["pending"] is None
            assert result["recoveries"][0]["outcome"] == "ABANDONED_UNCERTAIN"
            assert post(payload)[0] == 400
        finally:
            server.shutdown()
            thread.join(timeout=5)
