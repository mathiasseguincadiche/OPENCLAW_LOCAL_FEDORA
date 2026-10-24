from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

import pytest
from test_chat_projects import TOKEN, ask, tree_hash
from test_chat_projects import chat as chat
from test_daily_worker import planned as planned
from test_webui_actions import API

from clawfedora import chat_projects
from clawfedora.project_common import read_json, write_json
from clawfedora.project_control import request_pause, write_progress
from clawfedora.project_worker import worker_lock
from clawfedora.usage_view import activity, project_hint
from clawfedora.webui_bridge import MODEL_IDS, STICKY_MARKER, local_sticky, strip_banners


def get(server: Any, query: str = "", token: str = TOKEN, host: str = "") -> tuple[int, Any]:
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    connection.request(
        "GET",
        "/v1/atelier" + query,
        headers={
            "Authorization": "Bearer " + token,
            "Host": host or f"127.0.0.1:{server.server_port}",
        },
    )
    response = connection.getresponse()
    value = json.loads(response.read())
    status = response.status
    assert response.getheader("Cache-Control") == "no-store"
    connection.close()
    return status, value


def test_guidance_is_authenticated_read_only_and_available_during_inference(chat: Any) -> None:
    server, runner, runtime, project = chat
    with worker_lock(runtime):
        before = tree_hash(runtime)
        code, view = get(server, "?project=" + project.name)
        assert code == 200 and view["activity"]["active"]
        assert view["selected"]["id"] == project.name
        assert view["selected"]["next_step"]
        assert view["projects"][0]["title"] == "Daily"
    assert tree_hash(runtime) == before
    assert runner.calls == []
    text = json.dumps(view)
    for private in ("Comparer deux architectures", "pid", "session_id", TOKEN, "workspaces/"):
        assert private not in text
    assert get(server, token="wrong")[0] == 401
    assert get(server, host="evil.example")[0] == 401


@pytest.mark.parametrize(
    "query",
    [
        "?project=../secret",
        "?project=absent-project",
        "?project=a&project=b",
        "?prompt=private",
    ],
)
def test_guidance_rejects_unknown_or_ambiguous_projects(chat: Any, query: str) -> None:
    server, runner, _, _ = chat
    assert get(server, query)[0] == 400
    assert runner.calls == []


def test_linked_project_is_excluded_and_cannot_be_selected(chat: Any, tmp_path: Path) -> None:
    server, runner, runtime, _ = chat
    outside = tmp_path / "private"
    outside.mkdir()
    write_json(outside / "project.json", {"project_id": "linked-project", "title": "SECRET"})
    (runtime / "projects/linked-project").symlink_to(outside, target_is_directory=True)
    assert "SECRET" not in json.dumps(get(server)[1])
    assert get(server, "?project=linked-project")[0] == 400
    assert runner.calls == []


def test_activity_uses_the_lock_and_recorded_time_without_a_percentage(chat: Any) -> None:
    _, _, runtime, project = chat
    with worker_lock(runtime):
        write_progress(runtime, project, "running", role="ingenieur-devops", session="private-run")
        path = runtime / "state/worker-status.json"
        record = read_json(path)
        record["started_at"] = (datetime.now(UTC) - timedelta(seconds=65)).isoformat()
        write_json(path, record)
        view = activity(runtime)
        assert view["active"] and view["project_id"] == project.name
        assert 65 <= view["elapsed_seconds"] <= 70
        assert "1 min" in view["elapsed_label"]
        assert "Rédaction" in view["label"]
        assert "private-run" not in json.dumps(view) and "%" not in json.dumps(view)
    view = activity(runtime)
    assert not view["active"] and "interrompu" in view["label"]
    assert view["elapsed_seconds"] is None and view["project_id"] == ""


@pytest.mark.parametrize("stamp", ["broken", "2026-01-01", "2999-01-01T00:00:00+00:00"])
def test_activity_does_not_invent_an_elapsed_time(chat: Any, stamp: str) -> None:
    _, _, runtime, project = chat
    with worker_lock(runtime):
        write_progress(runtime, project, "chat")
        path = runtime / "state/worker-status.json"
        write_json(path, {**read_json(path), "started_at": stamp})
        assert activity(runtime)["elapsed_seconds"] is None


def test_pause_and_guided_steps_have_the_same_guidance_as_the_chat(chat: Any) -> None:
    server, _, runtime, project = chat
    request_pause(runtime, project)
    hint = project_hint(runtime, project)
    assert "pause" in hint
    _, response = ask(
        server, MODEL_IDS[0], ("assistant", "📁 Projet : " + project.name), ("user", "!etat")
    )
    assert hint in response
    assert get(server, "?project=" + project.name)[1]["selected"]["next_step"] == hint


def test_visual_selection_is_persisted_without_erasing_the_answer_or_sticky_local(
    chat: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server, runner, runtime, project = chat
    source = STICKY_MARKER + "\n\nRéponse utile et privée."
    body = {
        "id": "message-1",
        "messages": [
            {"id": "question", "role": "user", "content": "QUESTION_PRIVATE"},
            {"id": "message-1", "role": "assistant", "content": source},
        ],
    }
    before = tree_hash(runtime)
    monkeypatch.setenv("OPENAI_API_KEY", TOKEN)
    original = API["atelier_view"]
    monkeypatch.setitem(
        API["Action"].action.__globals__,
        "atelier_view",
        lambda key, current=None: original(key, current, port=server.server_port),
    )

    async def choose(event: dict[str, Any]) -> str:
        assert event["data"]["input"]["type"] == "select"
        assert "QUESTION_PRIVATE" not in json.dumps(event)
        return project.name

    result = asyncio.run(
        API["Action"]().action(
            body,
            __id__="choose",
            __user__={"role": "admin"},
            __event_call__=choose,
        )
    )
    assert body["messages"][-1]["content"] == source
    assert result["messages"][0]["content"].endswith(source)
    assert chat_projects.thread_state(result["messages"])[0] == project.name
    assert local_sticky(result["messages"])
    assert strip_banners(result["messages"][0]["content"]) == "Réponse utile et privée."
    assert runner.calls == [] and tree_hash(runtime) == before


@pytest.mark.parametrize("reply", [None, False, {"error": "disconnected"}, "", "../other"])
def test_cancelled_or_forged_selection_cannot_change_the_thread(
    monkeypatch: pytest.MonkeyPatch,
    reply: Any,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", TOKEN)
    monkeypatch.setitem(
        API["Action"].action.__globals__,
        "atelier_view",
        lambda key: {
            "projects": [{"id": "daily-project", "title": "Daily", "state": "Prêt"}],
        },
    )
    body = {
        "id": "message-1",
        "messages": [
            {"id": "message-1", "role": "assistant", "content": "Réponse conservée"},
        ],
    }

    async def choose(event: Any) -> Any:
        return reply

    if isinstance(reply, str) and reply:
        with pytest.raises(ValueError, match="non proposé"):
            asyncio.run(
                API["Action"]().action(
                    body,
                    __id__="choose",
                    __user__={"role": "admin"},
                    __event_call__=choose,
                )
            )
    else:
        assert (
            asyncio.run(
                API["Action"]().action(
                    body,
                    __id__="choose",
                    __user__={"role": "admin"},
                    __event_call__=choose,
                )
            )
            is None
        )
    assert body["messages"][0]["content"] == "Réponse conservée"


def test_grouped_action_still_requires_its_own_positive_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", TOKEN)
    globals_ = API["Action"].action.__globals__
    monkeypatch.setitem(
        globals_,
        "atelier_view",
        lambda *args: {
            "selected": {"id": "daily-project", "next_step": "Préparer le plan"},
        },
    )
    calls: list[str] = []
    monkeypatch.setitem(
        globals_, "local_bridge", lambda command, *args, **kwargs: calls.append(command)
    )
    events: list[Any] = []

    async def browser(event: dict[str, Any]) -> Any:
        events.append(event)
        return "start" if event["type"] == "input" else {"error": "disconnected"}

    asyncio.run(
        API["Action"]().action(
            {"messages": [{"role": "assistant", "content": "📁 Projet : daily-project"}]},
            __id__="project_actions",
            __user__={"role": "admin"},
            __event_call__=browser,
        )
    )
    assert calls == [] and events[-1]["type"] == "confirmation"
    assert "daily-project" in events[-1]["data"]["title"]


@pytest.mark.parametrize(
    "state, expected",
    [
        ("AWAITING_PRACTICE", "Complétez l’étape guidée"),
        ("AWAITING_FEEDBACK", "demandez le retour"),
    ],
)
def test_guidance_prioritizes_the_human_learning_step(chat: Any, state: str, expected: str) -> None:
    server, runner, runtime, project = chat
    path = project / "context/learning/tasks/design-choice.json"
    write_json(path, {"status": state})
    hint = get(server, "?project=" + project.name)[1]["selected"]["next_step"]
    assert expected in hint
    assert runner.calls == []


def test_reselecting_a_project_preserves_answer_and_downloads_without_duplicate_markers() -> None:
    content = "📁 Projet : old-project\n\nGuide rédigé.\n\n[Télécharger](http://127.0.0.1/fichier)"
    body = {
        "id": "last",
        "messages": [
            {"id": "first", "role": "user", "content": "Question conservée"},
            {"id": "last", "role": "assistant", "content": content},
        ],
    }
    result = API["_selection"](body, "new-project")
    reply = result["messages"][0]["content"]
    assert reply.startswith("📁 Projet : new-project\n\n")
    assert "old-project" not in reply and "[Télécharger]" in reply
    assert body["messages"][1]["content"] == content
    assert body["messages"][0]["content"] == "Question conservée"
    for invalid in ({**body, "id": "other-message"}, {"messages": []}):
        with pytest.raises(ValueError):
            API["_selection"](invalid, "new-project")


def test_activity_shortcut_and_resources_menu_do_not_call_a_model(
    chat: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server, runner, runtime, project = chat
    monkeypatch.setenv("OPENAI_API_KEY", TOKEN)
    original = API["atelier_view"]
    monkeypatch.setitem(
        API["Action"].action.__globals__,
        "atelier_view",
        lambda key: original(key, port=server.server_port),
    )
    notices: list[dict[str, Any]] = []

    async def notice(event: dict[str, Any]) -> None:
        notices.append(event)

    with worker_lock(runtime):
        write_progress(runtime, project, "chat", session="private-session")
        asyncio.run(
            API["Action"]().action(
                {},
                __id__="activity",
                __user__={"role": "admin"},
                __event_emitter__=notice,
            )
        )
    assert "discussion" in notices[-1]["data"]["content"]
    assert "private-session" not in json.dumps(notices)
    assert runner.calls == []
    read = API["read_only_bridge"]
    monkeypatch.setitem(
        API["Action"].action.__globals__,
        "read_only_bridge",
        lambda cmd, history, key: read(cmd, history, key=key, port=server.server_port),
    )

    async def choose_resource(event: dict[str, Any]) -> str:
        assert event["data"]["input"]["type"] == "select"
        return "budget"

    asyncio.run(
        API["Action"]().action(
            {"messages": []},
            __id__="resources",
            __user__={"role": "admin"},
            __event_call__=choose_resource,
            __event_emitter__=notice,
        )
    )
    assert "budget" in notices[-1]["data"]["content"].lower()
    assert runner.calls == []


def test_project_removed_while_menu_is_open_is_not_selected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", TOKEN)

    def metadata(key: str, current: str | None = None) -> dict[str, Any]:
        if current:
            raise ValueError("Projet introuvable")
        return {"projects": [{"id": "daily-project", "title": "Daily", "state": "Prêt"}]}

    monkeypatch.setitem(API["Action"].action.__globals__, "atelier_view", metadata)

    async def choose(event: Any) -> str:
        return "daily-project"

    body = {"id": "last", "messages": [{"id": "last", "role": "assistant", "content": "Réponse"}]}
    with pytest.raises(ValueError, match="introuvable"):
        asyncio.run(
            API["Action"]().action(
                body,
                __id__="choose",
                __user__={"role": "admin"},
                __event_call__=choose,
            )
        )
    assert body["messages"][0]["content"] == "Réponse"
