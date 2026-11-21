"""Native WebUI 0.12.3 project folders: bounded, opt-in, owner-only.

The real WebUI classes are imported only inside Actions at runtime. These
tests substitute the documented pinned-version methods without starting an
admin account, changing a SQLite database, or contacting GitHub/Notion.
"""

from __future__ import annotations

import asyncio
import runpy
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
API = runpy.run_path(str(ROOT / "plugins/openwebui/clawfedora_project_actions.py"))
PROJECTS = [
    {"id": "projet-alpha", "title": "Infrastructure Linux", "state": "IN_PROGRESS"},
    {"id": "projet-beta", "title": "Documentation et GitHub", "state": "PLANNED"},
]


@pytest.fixture
def native(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    state = SimpleNamespace(
        folders=[], chats={"chat-12345678": SimpleNamespace(
            id="chat-12345678", user_id="admin-1", folder_id=None,
        )}, calls=[],
    )
    for name in ("open_webui", "open_webui.models"):
        module = ModuleType(name)
        module.__path__ = []
        monkeypatch.setitem(sys.modules, name, module)

    class FolderForm:
        def __init__(
            self, name: str, meta: dict[str, Any] | None = None,
            parent_id: str | None = None,
        ) -> None:
            self.name = name
            self.meta = meta
            self.parent_id = parent_id

    class Folders:
        @staticmethod
        async def get_folders_by_user_id(user_id: str) -> list[Any]:
            assert user_id == "admin-1"
            return list(state.folders)

        @staticmethod
        async def insert_new_folder(
            user_id: str, form: FolderForm, parent_id: str | None = None,
        ) -> Any:
            assert user_id == "admin-1"
            created = SimpleNamespace(
                id="folder-" + str(len(state.folders) + 1),
                name=form.name,
                meta=form.meta,
                parent_id=parent_id,
                user_id=user_id,
            )
            state.calls.append(("create", created.name))
            state.folders.append(created)
            return created

        @staticmethod
        async def update_folder_is_expanded_by_id_and_user_id(
            folder_id: str, user_id: str, expanded: bool,
        ) -> Any:
            assert user_id == "admin-1" and expanded is True
            state.calls.append(("expand", folder_id))
            return next(f for f in state.folders if f.id == folder_id)

    class Chats:
        @staticmethod
        async def get_chat_by_id_and_user_id(chat_id: str, user_id: str) -> Any:
            chat = state.chats.get(chat_id)
            return chat if chat is not None and chat.user_id == user_id else None

        @staticmethod
        async def update_chat_folder_id_by_id_and_user_id(
            chat_id: str, user_id: str, folder_id: str,
        ) -> Any:
            chat = await Chats.get_chat_by_id_and_user_id(chat_id, user_id)
            if chat is not None:
                chat.folder_id = folder_id
                state.calls.append(("move", chat_id, folder_id))
            return chat

    folders_module = ModuleType("open_webui.models.folders")
    folders_module.Folders = Folders
    folders_module.FolderForm = FolderForm
    chats_module = ModuleType("open_webui.models.chats")
    chats_module.Chats = Chats
    monkeypatch.setitem(sys.modules, "open_webui.models.folders", folders_module)
    monkeypatch.setitem(sys.modules, "open_webui.models.chats", chats_module)
    return state


def test_project_rows_reject_duplicate_invalid_ids_and_unbounded_lists() -> None:
    parse = API["_folder_project_rows"]
    assert len(parse({"projects": PROJECTS})) == 2
    for invalid in (
        {"projects": "not a list"},
        {"projects": PROJECTS * 30},
        {"projects": [PROJECTS[0], PROJECTS[0]]},
        {"projects": [{"id": "../outside", "title": "X"}]},
        {"projects": [{"id": "valid-id", "title": ""}]},
        {"projects": [{"id": "valid-id", "title": "a" * 200}]},
    ):
        with pytest.raises(ValueError):
            parse(invalid)


def test_folders_create_idempotently_preserve_user_folders_and_no_chat_moves(
    native: SimpleNamespace,
) -> None:
    native.folders.append(SimpleNamespace(
        id="personal", name="Mes idées", parent_id=None, meta=None,
    ))
    rows = API["_folder_project_rows"]({"projects": PROJECTS})
    first = asyncio.run(API["_native_folders_for_projects"]("admin-1", rows))
    assert first[2] == 3   # one root and two projects
    assert set(first[1]) == {"projet-alpha", "projet-beta"}
    assert [x for x in native.calls if x[0] == "move"] == []
    assert native.folders[0].name == "Mes idées"
    assert ("expand", first[0]) in native.calls

    second = asyncio.run(API["_native_folders_for_projects"]("admin-1", rows))
    assert second[0] == first[0]
    assert second[1] == first[1]
    assert second[2] == 0
    assert len(native.folders) == 4


def test_collision_personal_folder_is_not_claimed(native: SimpleNamespace) -> None:
    native.folders.append(SimpleNamespace(
        id="user-root", name="Projets ClawFedora",
        parent_id=None, meta={"custom": "mine"},
    ))
    with pytest.raises(ValueError, match="personnel"):
        asyncio.run(API["_native_folders_for_projects"](
            "admin-1", API["_folder_project_rows"]({"projects": PROJECTS}),
        ))
    assert len(native.folders) == 1
    assert native.calls == []


def test_owned_chat_only(native: SimpleNamespace) -> None:
    rows = API["_folder_project_rows"]({"projects": PROJECTS})
    _root, mapping, _count = asyncio.run(
        API["_native_folders_for_projects"]("admin-1", rows),
    )
    with pytest.raises(ValueError, match="absente"):
        asyncio.run(
            API["_chat_to_project_folder"]("admin-1", "unknown-chat-123", mapping["projet-alpha"]),
        )
    native.chats["foreign-chat"] = SimpleNamespace(
        id="foreign-chat", user_id="other", folder_id=None,
    )
    with pytest.raises(ValueError, match="autre compte"):
        asyncio.run(
            API["_chat_to_project_folder"]("admin-1", "foreign-chat", mapping["projet-alpha"]),
        )
    assert [x for x in native.calls if x[0] == "move"] == []
    assert asyncio.run(
        API["_chat_to_project_folder"]("admin-1", "chat-12345678", mapping["projet-alpha"]),
    ) == "classée"
    assert asyncio.run(
        API["_chat_to_project_folder"]("admin-1", "chat-12345678", mapping["projet-alpha"]),
    ) == "déjà classée"
    assert len([x for x in native.calls if x[0] == "move"]) == 1


def test_sync_action_needs_positive_confirmation(
    native: SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "k" * 64)
    monkeypatch.setitem(
        API["Action"].action.__globals__, "atelier_view",
        lambda _key: {"projects": PROJECTS},
    )

    async def decline(_event: dict[str, Any]) -> Any:
        return {"error": "disconnected"}

    action = API["Action"]()
    asyncio.run(action.action(
        {"messages": []}, __id__="folder_sync",
        __user__={"role": "admin", "id": "admin-1"}, __event_call__=decline,
    ))
    assert native.calls == []

    async def approve(event: dict[str, Any]) -> bool:
        assert event["type"] == "confirmation"
        assert "conversations existantes" in event["data"]["message"]
        return True

    asyncio.run(action.action(
        {"messages": []}, __id__="folder_sync",
        __user__={"role": "admin", "id": "admin-1"}, __event_call__=approve,
    ))
    assert len(native.folders) == 3
    assert not any(call[0] == "move" for call in native.calls)


def test_link_action_only_moves_current_chat_and_retains_thread_marker(
    native: SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "k" * 64)

    def fake_view(_key: str, chosen: str | None = None) -> dict[str, Any]:
        return {
            "projects": PROJECTS,
            "selected": {"id": chosen} if chosen else None,
        }

    monkeypatch.setitem(API["Action"].action.__globals__, "atelier_view", fake_view)
    body = {
        "chat_id": "chat-12345678", "id": "assistant-last",
        "messages": [
            {"id": "assistant-last", "role": "assistant", "content": "Bonjour"},
        ],
    }
    answers: list[Any] = ["projet-beta", True]

    async def confirm(event: dict[str, Any]) -> Any:
        assert event["type"] in {"input", "confirmation"}
        return answers.pop(0)

    result = asyncio.run(API["Action"]().action(
        body, __id__="folder_link",
        __user__={"role": "admin", "id": "admin-1"}, __event_call__=confirm,
    ))
    assert result is not None
    assert result["messages"][0]["content"].startswith("📁 Projet : projet-beta")
    assert native.chats["chat-12345678"].folder_id is not None
    assert len([c for c in native.calls if c[0] == "move"]) == 1
    assert all(c[0] not in {"delete", "merge", "export"} for c in native.calls)


@pytest.mark.parametrize("chat_id", [None, "", "not saved", "../../local"])
def test_invalid_chat_id_never_creates_folder(
    native: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, chat_id: Any,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "k" * 64)
    monkeypatch.setitem(
        API["Action"].action.__globals__, "atelier_view",
        lambda _key: {"projects": PROJECTS},
    )

    async def approve(_event: dict[str, Any]) -> bool:
        pytest.fail("invalid chat must be rejected before dialog")

    with pytest.raises(ValueError, match="non enregistrée"):
        asyncio.run(API["Action"]().action(
            {"chat_id": chat_id, "messages": []},
            __id__="folder_link",
            __user__={"role": "admin", "id": "admin-1"}, __event_call__=approve,
        ))
    assert native.calls == []


def test_user_and_callback_are_required(
    native: SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "k" * 64)
    for actor in ({"role": "pending", "id": "admin-1"}, {"role": "admin"}):
        with pytest.raises(ValueError):
            asyncio.run(API["Action"]().action(
                {"messages": []}, __id__="folder_sync", __user__=actor,
            ))
    assert native.calls == []
