from __future__ import annotations

import json
import subprocess
import threading
from http.client import HTTPConnection
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from clawfedora import speech_server

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "s" * 64


def _request(
    server: Any,
    method: str,
    path: str,
    body: bytes = b"",
    *,
    token: str = TOKEN,
    content_type: str = "application/json",
) -> tuple[int, bytes, str]:
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    connection.request(
        method,
        path,
        body=body,
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": content_type,
            "Content-Length": str(len(body)),
        },
    )
    response = connection.getresponse()
    raw = response.read()
    result = response.status, raw, response.getheader("Content-Type", "")
    connection.close()
    return result


def test_speech_service_is_private_and_exposes_only_local_audio_surface(tmp_path: Path) -> None:
    with speech_server.make_server(ROOT, tmp_path, TOKEN, 0) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        assert _request(server, "GET", "/v1/audio/models", token="wrong")[0] == 401
        status, raw, _ = _request(server, "GET", "/v1/audio/models")
        assert status == 200 and json.loads(raw)["models"][0]["id"] == "clawfedora-tts"
        status, raw, _ = _request(server, "GET", "/v1/audio/voices")
        assert status == 200 and json.loads(raw)["voices"][0]["id"] == "fr-fr"
        assert _request(server, "GET", "/v1/unknown")[0] == 404
        server.shutdown()
        thread.join(timeout=3)


def test_speech_and_transcription_stay_local(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeWhisper:
        def transcribe(self, *_args: Any, **kwargs: Any) -> tuple[list[Any], object]:
            assert kwargs["language"] == "fr"
            assert kwargs["beam_size"] == 5 and kwargs["vad_filter"] is True
            return [SimpleNamespace(text=" bonjour "), SimpleNamespace(text="le monde")], object()

    monkeypatch.setattr(speech_server, "_load_whisper", lambda _server: FakeWhisper())

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        assert command[:4] == ["espeak-ng", "--stdout", "-v", "fr-fr"]
        assert kwargs["timeout"] == 60
        assert kwargs["input"] == b"Bonjour"
        assert "--stdin" in command
        assert "Bonjour" not in command
        return subprocess.CompletedProcess(command, 0, stdout=b"RIFFtest", stderr=b"")

    monkeypatch.setattr(speech_server.subprocess, "run", fake_run)

    with speech_server.make_server(ROOT, tmp_path, TOKEN, 0) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        speech = json.dumps(
            {"model": "clawfedora-tts", "voice": "fr-fr", "input": "Bonjour"}
        ).encode()
        status, raw, content_type = _request(server, "POST", "/v1/audio/speech", speech)
        assert status == 200 and raw.startswith(b"RIFF") and content_type == "audio/wav"

        # Even a crafted client voice must not enter the subprocess command line.
        hostile = json.dumps(
            {"model": "clawfedora-tts", "voice": "fr-fr --path=/tmp/evil", "input": "Bonjour"}
        ).encode()
        status, _, _ = _request(server, "POST", "/v1/audio/speech", hostile)
        assert status == 400

        boundary = "----clawfedora-test"
        multipart = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="model"\r\n\r\n'
            "clawfedora-whisper\r\n"
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="language"\r\n\r\n'
            "fr\r\n"
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="note.wav"\r\n'
            "Content-Type: audio/wav\r\n\r\n"
        ).encode() + b"RIFFaudio" + f"\r\n--{boundary}--\r\n".encode()
        status, raw, _ = _request(
            server,
            "POST",
            "/v1/audio/transcriptions",
            multipart,
            content_type=f"multipart/form-data; boundary={boundary}",
        )
        assert status == 200
        assert json.loads(raw)["text"] == "bonjour le monde"

        server.shutdown()
        thread.join(timeout=3)
