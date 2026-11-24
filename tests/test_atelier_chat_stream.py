"""Native dashboard SSE: no Gateway secrets in browser, fail closed on partial output."""
from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import closing
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

import pytest

from clawfedora import atelier_chat, atelier_chat_stream, dashboard

ROOT = Path(__file__).resolve().parents[1]


def _prepare(tmp_path: Path) -> tuple[Path, str]:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    chat = atelier_chat.create(runtime, None, "chef-operations")
    return runtime, str(chat["id"])


def _project(runtime: Path) -> None:
    project = runtime / "projects/opsdesk"
    project.mkdir(parents=True)
    (project / "project.json").write_text(
        '{"project_id":"opsdesk","title":"OpsDesk","status":"IN_PROGRESS"}',
        encoding="utf-8",
    )


def _permit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(atelier_chat_stream.native_stream, "opted_in", lambda _: True)


def test_opt_in_off_and_all_unsafe_scopes_are_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, identifier = _prepare(tmp_path)
    assert atelier_chat_stream.enabled(runtime) is False
    with pytest.raises(ValueError, match="non activé"):
        atelier_chat_stream.allowed(runtime, identifier, "Une question")
    _permit(monkeypatch)
    for message in ("!continuer", "/etat", "  /projet opsdesk", " "):
        with pytest.raises(ValueError, match="questions texte"):
            atelier_chat_stream.allowed(runtime, identifier, message)
    _project(runtime)
    project_chat = atelier_chat.create(runtime, "opsdesk", "chef-operations")
    with pytest.raises(ValueError, match="sans projet"):
        atelier_chat_stream.allowed(runtime, project_chat["id"], "Une question")
    other = atelier_chat.create(runtime, None, "ingenieur-devops")
    with pytest.raises(ValueError, match="Mentor"):
        atelier_chat_stream.allowed(runtime, other["id"], "Une question")


def test_completed_stream_is_the_only_one_that_commits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, identifier = _prepare(tmp_path)
    _permit(monkeypatch)
    calls: list[tuple[str, str]] = []

    def fake(
        _repo: Path, _runtime: Path, doc: dict[str, Any], msg: str,
    ) -> Iterator[str]:
        assert doc["pending"]["message"] == msg
        calls.append((doc["agent"], msg))
        yield "Bon"
        yield "jour"

    monkeypatch.setattr(atelier_chat_stream, "_bridge_deltas", fake)
    events = list(atelier_chat_stream.stream(ROOT, runtime, identifier, "Bonjour !"))
    assert [event["type"] for event in events] == ["delta", "delta", "complete"]
    assert events[-1] == {"type": "complete", "id": identifier}
    doc = atelier_chat.read(runtime, identifier)
    assert doc["pending"] is None
    assert doc["messages"][-1] == {"role": "assistant", "content": "Bonjour"}
    assert calls == [("chef-operations", "Bonjour !")]


def test_partial_stream_or_disconnect_keeps_pending_and_aborts_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, identifier = _prepare(tmp_path)
    _permit(monkeypatch)
    closed: list[str] = []

    def fake(
        _repo: Path, _runtime: Path, _doc: dict[str, Any], _msg: str,
    ) -> Iterator[str]:
        try:
            yield "réponse partielle"
            yield "suite"
        finally:
            closed.append("closed")

    monkeypatch.setattr(atelier_chat_stream, "_bridge_deltas", fake)
    with closing(atelier_chat_stream.stream(ROOT, runtime, identifier, "Question")) as stream:
        assert next(stream) == {"type": "delta", "text": "réponse partielle"}
    assert closed == ["closed"]
    doc = atelier_chat.read(runtime, identifier)
    assert doc["pending"]["message"] == "Question"
    assert doc["messages"] == []
    with pytest.raises(ValueError, match="incertain"):
        atelier_chat_stream.allowed(runtime, identifier, "Retenter")


def test_upstream_failure_never_commits_partial_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, identifier = _prepare(tmp_path)
    _permit(monkeypatch)

    def broken(*_args: Any) -> Iterator[str]:
        yield "début"
        raise ValueError("Gateway incomplete")

    monkeypatch.setattr(atelier_chat_stream, "_bridge_deltas", broken)
    with pytest.raises(ValueError, match="incomplete"):
        list(atelier_chat_stream.stream(ROOT, runtime, identifier, "Question"))
    assert atelier_chat.read(runtime, identifier)["pending"] is not None
    assert atelier_chat.read(runtime, identifier)["messages"] == []


def _http(
    port: int, path: str, data: dict[str, Any] | None = None, *,
    origin: bool = True,
) -> tuple[int, bytes]:
    conn = HTTPConnection("127.0.0.1", port, timeout=6)
    headers = {"Host": f"127.0.0.1:{port}"}
    if data is not None:
        headers["Content-Type"] = "application/json"
        if origin:
            headers["Origin"] = f"http://127.0.0.1:{port}"
    conn.request("POST" if data is not None else "GET", path,
                 json.dumps(data) if data is not None else None, headers)
    response = conn.getresponse()
    status, raw = response.status, response.read()
    conn.close()
    return status, raw


def test_dashboard_sse_is_same_origin_scoped_and_persists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, identifier = _prepare(tmp_path)
    _permit(monkeypatch)
    called: list[str] = []

    def fake(
        _repo: Path, _runtime: Path, _doc: dict[str, Any], _msg: str,
    ) -> Iterator[str]:
        called.append("bridge")
        yield "premier"
        yield "second"

    monkeypatch.setattr(atelier_chat_stream, "_bridge_deltas", fake)
    with dashboard.make_server(ROOT, runtime, 0) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_port
            cap, data = _http(port, "/api/chat/stream-capability")
            assert cap == 200 and json.loads(data)["enabled"] is True
            request = {"id": identifier, "message": "Décris Fedora"}
            status, _ = _http(port, "/api/chat/send-stream", request, origin=False)
            assert status == 403 and called == []
            status, data = _http(port, "/api/chat/send-stream", request)
            assert status == 200
            assert data.count(b"data: ") == 3
            frames = [json.loads(line.removeprefix(b"data: "))
                      for line in data.splitlines() if line.startswith(b"data: ")]
            assert [x["type"] for x in frames] == ["delta", "delta", "complete"]
            assert frames[-1]["id"] == identifier
            assert called == ["bridge"]
            doc = atelier_chat.read(runtime, identifier)
            assert doc["messages"][-1]["content"] == "premiersecond"
            assert doc["pending"] is None
            assert b"operator" not in data
            status, _ = _http(port, "/api/chat/send-stream", {
                "id": identifier, "message": "!continuer",
            })
            assert status == 400 and called == ["bridge"]
        finally:
            server.shutdown()
            thread.join(timeout=5)


def test_native_stream_reuses_bridge_preflight_and_validated_sse_frames(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from clawfedora.webui_bridge import make_server

    runtime, identifier = _prepare(tmp_path)
    _permit(monkeypatch)
    routes: list[str] = []

    def fail_cli(*_args: Any) -> dict[str, Any]:
        pytest.fail("CLI should not replace a qualified SSE source")

    def remote(role: str, prompt: str, session: str) -> Iterator[str]:
        assert role == "chef-operations"
        assert "Fedora" in prompt
        assert len(session) == 36
        routes.append("stream")
        yield "un "
        yield "test"

    def bridge(_repo: Path, _runtime: Path, bearer: str, _port: int) -> Any:
        assert bearer and len(bearer) == 64
        return make_server(
            ROOT, runtime, bearer, 0,
            runner=fail_cli, stream_runner=remote,
        )

    monkeypatch.setattr(atelier_chat_stream, "make_policy_bridge", bridge)
    events = list(atelier_chat_stream.stream(ROOT, runtime, identifier, "Fedora ?"))
    assert "".join(x["text"] for x in events if x["type"] == "delta").endswith(
        "un test"
    )
    assert events[-1]["type"] == "complete"
    assert routes == ["stream"]
    assert atelier_chat.read(runtime, identifier)["pending"] is None


def test_invisible_banner_prefix_alone_is_not_a_completed_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, identifier = _prepare(tmp_path)
    _permit(monkeypatch)

    def empty(*_args: Any) -> Iterator[str]:
        yield "\u200b"

    monkeypatch.setattr(atelier_chat_stream, "_bridge_deltas", empty)
    with pytest.raises(ValueError, match="vide"):
        list(atelier_chat_stream.stream(ROOT, runtime, identifier, "Question"))
    doc = atelier_chat.read(runtime, identifier)
    assert doc["messages"] == [] and doc["pending"] is not None


def _extended(runtime: Path) -> Path:
    marker = runtime / atelier_chat_stream.native_stream.MARKER
    marker.parent.mkdir(parents=True, exist_ok=True)
    (runtime / ".openclaw-fedora-runtime").touch()
    marker.write_text(atelier_chat_stream.native_stream.EXTENDED_APPROVAL + "\n")
    marker.chmod(0o600)
    return marker


@pytest.mark.parametrize("project_bound", [False, True])
def test_v2_admits_each_role_and_rejects_actions(
    tmp_path: Path, project_bound: bool,
) -> None:
    from clawfedora.core_config import AGENT_IDS

    runtime, _ = _prepare(tmp_path)
    marker = _extended(runtime)
    _project(runtime)
    project = "opsdesk" if project_bound else None
    for role in AGENT_IDS:
        chat = atelier_chat.create(runtime, project, role)
        identifier = chat["id"]
        doc = atelier_chat_stream.allowed(runtime, identifier, "Une question")
        assert doc["agent"] == role and doc["project"] == project
        for action in ("!lancer", "/etat", "approuver livraison ABCD"):
            with pytest.raises(ValueError, match="questions texte"):
                atelier_chat_stream.allowed(runtime, identifier, action)
    marker.write_text(atelier_chat_stream.native_stream.APPROVAL + "\n")
    assert not atelier_chat_stream.native_stream.extended_opted_in(runtime)


def test_json_and_sse_cannot_overwrite_same_turn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, identifier = _prepare(tmp_path)
    _extended(runtime)

    def source(*_args: Any) -> Iterator[str]:
        yield "Premier "
        yield "second"

    monkeypatch.setattr(atelier_chat_stream, "_bridge_deltas", source)
    with closing(atelier_chat_stream.stream(ROOT, runtime, identifier, "Question")) as events:
        assert next(events)["text"] == "Premier "
        with pytest.raises(ValueError, match="déjà en cours"):
            atelier_chat.send(ROOT, runtime, identifier, "!fedora etat")
        with pytest.raises(ValueError, match="déjà en cours"):
            list(atelier_chat_stream.stream(ROOT, runtime, identifier, "Autre"))
        assert [event["type"] for event in events] == ["delta", "complete"]
    doc = atelier_chat.read(runtime, identifier)
    assert doc["pending"] is None and len(doc["messages"]) == 2
    assert doc["messages"][-1]["content"] == "Premier second"


def test_v2_project_stream_has_canonical_context_and_no_cli_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from clawfedora import chat_projects
    from clawfedora.webui_bridge import make_server

    runtime, _ = _prepare(tmp_path)
    _extended(runtime)
    _project(runtime)
    chat = atelier_chat.create(runtime, "opsdesk", "ingenieur-devops")
    seen: list[str] = []

    def context(_repo: Path, _runtime: Path, project: Path, question: str,
                *, include_revisions: bool) -> str:
        assert project.name == "opsdesk" and include_revisions
        assert question == "Décris la CI"
        return "Contexte canonique OpsDesk, lecture seule"

    def fail_cli(*_args: Any) -> dict[str, Any]:
        pytest.fail("Aucun repli CLI")

    def remote(role: str, prompt: str, _session: str) -> Iterator[str]:
        assert role == "ingenieur-devops" and "Contexte canonique OpsDesk" in prompt
        seen.append(role)
        yield "CI "
        yield "validée"

    def bridge(_repo: Path, _runtime: Path, bearer: str, _port: int,
               *, native_thread: tuple[str, str | None]) -> Any:
        assert native_thread == ("ingenieur-devops", "opsdesk")
        return make_server(ROOT, runtime, bearer, 0, runner=fail_cli,
                           stream_runner=remote, native_thread=native_thread)

    monkeypatch.setattr(chat_projects, "project_context", context)
    monkeypatch.setattr(atelier_chat_stream, "make_policy_bridge", bridge)
    events = list(atelier_chat_stream.stream(ROOT, runtime, chat["id"], "Décris la CI"))
    assert seen == ["ingenieur-devops"]
    assert events[-1]["type"] == "complete"
    doc = atelier_chat.read(runtime, chat["id"])
    assert doc["project"] == "opsdesk" and doc["pending"] is None
    assert doc["messages"][-1]["content"].endswith("CI validée")


def test_v2_refuses_history_switch_and_missing_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from clawfedora.webui_bridge import make_server

    runtime, _ = _prepare(tmp_path)
    _extended(runtime)
    _project(runtime)
    chat = atelier_chat.create(runtime, "opsdesk", "ingenieur-devops")

    def forbidden(*_args: Any) -> Iterator[str]:
        pytest.fail("Le mauvais projet ne doit pas atteindre le modèle")
        yield "never"

    def bridge(_repo: Path, _runtime: Path, bearer: str, _port: int,
               *, native_thread: tuple[str, str | None]) -> Any:
        return make_server(ROOT, runtime, bearer, 0, stream_runner=forbidden,
                           native_thread=native_thread)

    chat["messages"] = [
        {"role": "user", "content": "Question passée"},
        {"role": "assistant", "content": "📁 Projet : autre-projet\n\nAutre contenu"},
    ]
    atelier_chat._save(runtime, chat)
    monkeypatch.setattr(atelier_chat_stream, "make_policy_bridge", bridge)
    with pytest.raises(ValueError, match="refusée"):
        list(atelier_chat_stream.stream(ROOT, runtime, chat["id"], "Question"))
    assert atelier_chat.read(runtime, chat["id"])["pending"] is not None
    (runtime / "projects/opsdesk/project.json").unlink()
    with pytest.raises(ValueError, match="introuvable"):
        atelier_chat_stream.allowed(runtime, chat["id"], "Question")
