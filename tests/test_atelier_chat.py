"""Native Atelier discussion contract: no native model tools or webui account."""
from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

import pytest

from clawfedora import atelier_chat, dashboard
from clawfedora.core_config import AGENT_IDS

ROOT = Path(__file__).resolve().parents[1]


def _project(runtime: Path, name: str) -> None:
    path = runtime / "projects" / name
    path.mkdir(parents=True, exist_ok=True)
    (path / "project.json").write_text(
        json.dumps({"project_id": name, "title": name, "status": "INTAKE_READY"}),
        encoding="utf-8",
    )


def _request(server: dashboard.DashboardServer, path: str,
             data: dict[str, Any] | None = None, *,
             origin: bool = True) -> tuple[int, Any]:
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    headers = {"Host": f"127.0.0.1:{server.server_port}"}
    if data is not None:
        headers["Content-Type"] = "application/json"
        if origin:
            headers["Origin"] = f"http://127.0.0.1:{server.server_port}"
    connection.request(
        "POST" if data is not None else "GET", path,
        body=json.dumps(data) if data is not None else None,
        headers=headers,
    )
    response = connection.getresponse()
    raw = response.read()
    value = json.loads(raw) if "application/json" in (
        response.getheader("Content-Type") or ""
    ) else raw.decode("utf-8")
    status = response.status
    connection.close()
    return status, value


def test_local_history_agent_scope_and_no_model_in_get(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _project(tmp_path, "opsdesk")
    called: list[tuple[str, str]] = []

    def answer(_repo: Path, _runtime: Path, doc: dict[str, Any], msg: str) -> str:
        called.append((doc["agent"], doc["project"]))
        return "📁 Projet : opsdesk\n\nRéponse locale " + msg

    monkeypatch.setattr(atelier_chat, "_policy_answer", answer)
    first = atelier_chat.create(tmp_path, "opsdesk", "ingenieur-devops")
    assert first["project"] == "opsdesk" and first["agent"] == "ingenieur-devops"
    assert (tmp_path / "state/atelier-chats").stat().st_mode & 0o077 == 0
    second = atelier_chat.send(ROOT, tmp_path, first["id"], "Contrôle infra")
    assert second["messages"][0]["role"] == "user"
    assert second["messages"][1]["role"] == "assistant"
    assert called == [("ingenieur-devops", "opsdesk")]
    assert atelier_chat.read(tmp_path, first["id"])["messages"] == second["messages"]
    assert atelier_chat.listing(tmp_path)["chats"][0]["id"] == first["id"]
    assert len(atelier_chat.listing(tmp_path)["agents"]) == 7
    assert set(atelier_chat.listing(tmp_path)["agents"]) == set(AGENT_IDS)
    with pytest.raises(ValueError, match="Projet"):
        atelier_chat.create(tmp_path, "missing", "ingenieur-devops")
    with pytest.raises(ValueError, match="Rôle"):
        atelier_chat.create(tmp_path, None, "root")
    with pytest.raises(ValueError, match="Identifiant"):
        atelier_chat.read(tmp_path, "../../etc/passwd")


def test_status_readonly_and_no_project_switch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _project(tmp_path, "opsdesk")
    session = atelier_chat.create(tmp_path, "opsdesk", "chef-operations")
    monkeypatch.setattr(atelier_chat, "fedora_status", lambda: "Fedora : lecture seule")
    monkeypatch.setattr(
        atelier_chat, "_policy_answer",
        lambda *_args: pytest.fail("No model for deterministic commands"),
    )
    changed = atelier_chat.send(ROOT, tmp_path, session["id"], "!fedora etat")
    assert "lecture seule" in changed["messages"][-1]["content"]
    monkeypatch.setattr(
        atelier_chat, "fedora_applications", lambda: "Flatpak : inventaire limité"
    )
    changed = atelier_chat.send(ROOT, tmp_path, session["id"], "!fedora applications")
    assert "inventaire limité" in changed["messages"][-1]["content"]
    changed = atelier_chat.send(ROOT, tmp_path, session["id"], "!projet autre")
    assert "immuable" in changed["messages"][-1]["content"]
    assert changed["project"] == "opsdesk"
    assert atelier_chat.read(tmp_path, session["id"])["project"] == "opsdesk"


def test_interrupted_turn_is_persisted_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = atelier_chat.create(tmp_path, None, "chef-operations")

    def disconnected(*_args: Any) -> str:
        raise OSError("réponse perdue")

    monkeypatch.setattr(atelier_chat, "_policy_answer", disconnected)
    with pytest.raises(OSError, match="perdue"):
        atelier_chat.send(ROOT, tmp_path, session["id"], "!lancer")
    assert atelier_chat.read(tmp_path, session["id"])["pending"]["message"] == "!lancer"
    with pytest.raises(ValueError, match="incertain"):
        atelier_chat.send(ROOT, tmp_path, session["id"], "!lancer")


def test_symlinks_and_malformed_history_are_rejected(tmp_path: Path) -> None:
    _project(tmp_path, "opsdesk")
    item = atelier_chat.create(tmp_path, "opsdesk", "chef-operations")
    outside = tmp_path / "outside"
    outside.write_text("{}")
    record = tmp_path / "state/atelier-chats" / (item["id"] + ".json")
    record.unlink()
    record.symlink_to(outside)
    with pytest.raises(ValueError, match="liée"):
        atelier_chat.read(tmp_path, item["id"])
    with pytest.raises(ValueError, match="liée"):
        atelier_chat.send(ROOT, tmp_path, item["id"], "test")
    record.unlink()
    record.write_text('{"id":"wrong"}')
    record.chmod(0o600)
    with pytest.raises(ValueError, match="invalide"):
        atelier_chat.read(tmp_path, item["id"])


def test_http_native_chat_same_origin_and_static_assets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _project(tmp_path, "opsdesk")
    monkeypatch.setattr(
        atelier_chat, "_policy_answer",
        lambda _root, _runtime, _document, _msg: "Réponse simulée sans modèle",
    )
    with dashboard.make_server(ROOT, tmp_path, 0) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            for asset in ("/discussions.html", "/discussions.js", "/discussions.css"):
                status, body = _request(server, asset)
                assert status == 200 and len(body) > 100
            assert _request(server, "/api/chats") == (
                200, {"agents": list(AGENT_IDS), "chats": []},
            )
            payload = {"agent": "ingenieur-devops", "project": "opsdesk"}
            assert _request(server, "/api/chat/new", payload, origin=False)[0] == 403
            status, created = _request(server, "/api/chat/new", payload)
            assert status == 201
            chat_id = created["id"]
            assert _request(server, "/api/chat?id=" + chat_id)[0] == 200
            status, updated = _request(
                server, "/api/chat/send", {"id": chat_id, "message": "Bonjour"},
            )
            assert status == 200
            assert updated["messages"][-1]["content"] == "Réponse simulée sans modèle"
            assert _request(
                server, "/api/chat/send", {"id": chat_id, "message": " "},
            )[0] == 400
            assert _request(
                server, "/api/chat/new", {"agent": "exec", "project": "opsdesk"},
            )[0] == 400
        finally:
            server.shutdown()
            worker.join(timeout=5)
