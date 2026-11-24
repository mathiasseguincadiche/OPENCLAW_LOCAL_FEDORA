"""Native downloads survive the temporary bridge and bind to completed turns."""
from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Generator
from http.client import HTTPConnection
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import pytest

from clawfedora import atelier_chat, atelier_chat_stream, dashboard, native_stream
from clawfedora.agents import deploy_workspaces
from clawfedora.file_artifacts import produce
from clawfedora.project_worker import _tool_receipts
from clawfedora.webui_bridge import make_server

ROOT = Path(__file__).resolve().parents[1]
ROLE = "redacteur-pedagogique"
SOURCE = "# Guide OPS\n\nVérifier les preuves.\n"


def _produce(runtime: Path) -> dict[str, Any]:
    return produce(runtime / "workspaces" / ROLE, ROLE, {
        "format": "markdown", "filename": "guide.md", "content": SOURCE,
        "exports": ["pdf", "docx", "odt"],
    })


@pytest.mark.parametrize("streaming", [False, True])
def test_native_downloads_survive_bridge_shutdown_and_bind_to_turn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, streaming: bool,
) -> None:
    deploy_workspaces(ROOT, tmp_path)
    old = _produce(tmp_path)
    chat = atelier_chat.create(tmp_path, None, ROLE)
    other = atelier_chat.create(tmp_path, None, ROLE)

    def runner(role: str, _prompt: str, _session: str) -> dict[str, Any]:
        assert role == ROLE
        _produce(tmp_path)
        return {"text": "Voici le guide."}

    def source(role: str, _prompt: str, _session: str) -> Generator[str, None, None]:
        assert role == ROLE
        _produce(tmp_path)
        yield "Voici le guide."

    if streaming:
        marker = tmp_path / native_stream.MARKER
        marker.parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / ".openclaw-fedora-runtime").touch()
        marker.write_text(native_stream.EXTENDED_APPROVAL + "\n")
        marker.chmod(0o600)

    def bridge(_repo: Path, _runtime: Path, bearer: str, _port: int,
               **kwargs: Any) -> Any:
        return make_server(ROOT, tmp_path, bearer, 0, runner=runner,
                           stream_runner=source, **kwargs)

    monkeypatch.setattr(atelier_chat, "make_policy_bridge", bridge)
    monkeypatch.setattr(atelier_chat_stream, "make_policy_bridge", bridge)
    if streaming:
        events = list(atelier_chat_stream.stream(ROOT, tmp_path, chat["id"], "Un guide"))
        assert events[-1]["type"] == "complete"
    else:
        atelier_chat.send(ROOT, tmp_path, chat["id"], "Un guide")
    message = atelier_chat.read(tmp_path, chat["id"])["messages"][-1]
    assert "Voici le guide." in message["content"]
    assert "127.0.0.1" not in message["content"]
    refs = message["artifacts"]
    assert {item["format"] for item in refs} == {"md", "pdf", "docx", "odt"}
    receipt = refs[0]["receipt"]
    assert receipt != old["references"]["pdf"].split(":")[1]
    raw, name = atelier_chat.download(tmp_path, chat["id"], receipt, "md")
    assert raw == SOURCE.encode() and name == "guide.md"
    for ref in refs:
        raw, name = atelier_chat.download(tmp_path, chat["id"], receipt, ref["format"])
        assert hashlib.sha256(raw).hexdigest() == ref["sha256"]
        assert len(raw) == ref["size"] and name == ref["name"]
    with pytest.raises(ValueError, match="absent"):
        atelier_chat.download(tmp_path, other["id"], receipt, "pdf")
    with pytest.raises(ValueError, match="absent"):
        atelier_chat.download(tmp_path, chat["id"], old["references"]["pdf"].split(":")[1], "pdf")

    with dashboard.make_server(ROOT, tmp_path, 0) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            query = urlencode({"id": chat["id"], "receipt": receipt, "format": "pdf"})
            conn = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            try:
                conn.request("GET", "/api/chat/artifact?" + query)
                result = conn.getresponse()
                assert result.status == 200
                assert result.read().startswith(b"%PDF-")
                assert "guide.pdf" in result.getheader("Content-Disposition")
                conn.request("GET", "/api/chat/artifact?" + query + "&role=chef-operations")
                result = conn.getresponse()
                assert result.status == 400
                result.read()
            finally:
                conn.close()
        finally:
            server.shutdown()
            thread.join(timeout=5)

    # Even if both a receipt and its file change, the committed digest refuses it.
    workspace = tmp_path / "workspaces" / ROLE / ".clawfedora-tool-evidence"
    target = workspace / (receipt + ".artifact.md.data")
    target.chmod(0o600)
    target.write_bytes(b"altered")
    proof = workspace / (receipt + ".json")
    proof.chmod(0o600)
    data = json.loads(proof.read_text())
    data["artifacts"]["md"]["sha256"] = hashlib.sha256(b"altered").hexdigest()
    proof.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="modifié"):
        atelier_chat.download(tmp_path, chat["id"], receipt, "md")


def test_interrupted_turn_does_not_publish_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    deploy_workspaces(ROOT, tmp_path)
    chat = atelier_chat.create(tmp_path, None, ROLE)
    workspace = tmp_path / "workspaces" / ROLE
    before = _tool_receipts(workspace)

    def runner(*_args: Any) -> dict[str, Any]:
        _produce(tmp_path)
        raise ValueError("génération interrompue")

    def bridge(_repo: Path, _runtime: Path, bearer: str, _port: int) -> Any:
        return make_server(ROOT, tmp_path, bearer, 0, runner=runner)

    monkeypatch.setattr(atelier_chat, "make_policy_bridge", bridge)
    with pytest.raises(ValueError):
        atelier_chat.send(ROOT, tmp_path, chat["id"], "Un fichier")
    new = _tool_receipts(workspace) - before
    assert len(new) == 1
    stored = atelier_chat.read(tmp_path, chat["id"])
    assert stored["pending"] is not None and stored["messages"] == []
    with pytest.raises(ValueError, match="absent"):
        atelier_chat.download(tmp_path, chat["id"], next(iter(new)).stem, "md")
