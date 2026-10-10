"""Private OpenAI-compatible speech endpoint for Open WebUI slim.

STT uses faster-whisper on CPU/int8 so Qwen keeps the Intel GPU. TTS uses Fedora's espeak-ng.
The service is loopback-only, bearer-token protected and intentionally implements only the
small OpenAI audio surface Open WebUI needs.
"""

from __future__ import annotations

import argparse
import hmac
import importlib
import json
import subprocess
import tempfile
import threading
from email import policy as email_policy
from email.parser import BytesParser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

from clawfedora.core_config import root_contract
from clawfedora.local_http import LocalServer

MAX_TEXT = 20_000


class SpeechServer(LocalServer):
    token: str
    config: dict[str, Any]
    model: Any = None
    model_lock: threading.Lock


def _load_whisper(server: SpeechServer) -> Any:
    with server.model_lock:
        if server.model is None:
            module = importlib.import_module("faster_whisper")
            model_cls = module.WhisperModel
            speech = server.config
            server.model = model_cls(
                str(speech["stt_model"]),
                device=str(speech["stt_device"]),
                compute_type=str(speech["stt_compute_type"]),
                download_root=str(speech["model_root"]),
            )
        return server.model


def prepare(repo_root: Path, runtime: Path) -> None:
    speech = dict(root_contract(repo_root, "webui_policy.yaml")["speech"])
    speech["model_root"] = runtime / "models/whisper"
    speech["model_root"].mkdir(parents=True, exist_ok=True)
    server = SpeechServer(("127.0.0.1", 0), SpeechHandler)
    try:
        server.config = speech
        server.model_lock = threading.Lock()
        _load_whisper(server)
    finally:
        server.server_close()


def _multipart(content_type: str, body: bytes) -> dict[str, tuple[str | None, bytes]]:
    raw = (
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode()
        + body
    )
    message = BytesParser(policy=email_policy.default).parsebytes(raw)
    if not message.is_multipart():
        raise ValueError("multipart/form-data requis")
    values: dict[str, tuple[str | None, bytes]] = {}
    for part in message.iter_parts():
        if part.get_content_disposition() != "form-data":
            continue
        name = part.get_param("name", header="content-disposition")
        if not isinstance(name, str) or not name:
            continue
        payload = part.get_payload(decode=True)
        if not isinstance(payload, bytes):
            payload = b""
        values[name] = (part.get_filename(), payload)
    return values


class SpeechHandler(BaseHTTPRequestHandler):
    server: SpeechServer

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def _auth(self) -> bool:
        header = self.headers.get("Authorization", "")
        expected = "Bearer " + self.server.token
        return hmac.compare_digest(header, expected)

    def _json(self, status: int, value: dict[str, Any]) -> None:
        raw = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _body(self, limit: int) -> bytes:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Content-Length invalide") from exc
        if not 0 < length <= limit or self.headers.get("Transfer-Encoding"):
            raise ValueError("requête absente ou trop volumineuse")
        return self.rfile.read(length)

    def do_GET(self) -> None:
        if not self._auth():
            self._json(HTTPStatus.UNAUTHORIZED, {"error": {"message": "authentification locale"}})
            return
        if self.path == "/v1/audio/models":
            self._json(
                HTTPStatus.OK,
                {"models": [{"id": "clawfedora-tts", "name": "ClawFedora voix locale"}]},
            )
            return
        if self.path == "/v1/audio/voices":
            voice = str(self.server.config["tts_voice"])
            self._json(HTTPStatus.OK, {"voices": [{"id": voice, "name": voice}]})
            return
        if self.path == "/v1/models":
            self._json(
                HTTPStatus.OK,
                {"data": [{"id": "clawfedora-tts"}, {"id": "clawfedora-whisper"}]},
            )
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": {"message": "endpoint absent"}})

    def do_POST(self) -> None:
        if not self._auth():
            self._json(HTTPStatus.UNAUTHORIZED, {"error": {"message": "authentification locale"}})
            return
        try:
            if self.path == "/v1/audio/transcriptions":
                self._transcribe()
                return
            if self.path == "/v1/audio/speech":
                self._speak()
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": {"message": "endpoint absent"}})
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": {"message": str(exc)[:500]}})

    def _transcribe(self) -> None:
        speech = self.server.config
        raw = self._body(int(speech["max_audio_bytes"]) + 1_000_000)
        content_type = self.headers.get("Content-Type", "")
        fields = _multipart(content_type, raw)
        file_field = fields.get("file")
        if file_field is None or not file_field[1]:
            raise ValueError("fichier audio requis")
        filename, audio = file_field
        if len(audio) > int(speech["max_audio_bytes"]):
            raise ValueError("audio supérieur à la limite")
        suffix = Path(filename or "audio.wav").suffix[:10] or ".wav"
        language_raw = fields.get("language", (None, b""))[1].decode(
            "utf-8", errors="ignore"
        ).strip()
        language = language_raw or str(speech["language"])
        with tempfile.NamedTemporaryFile(suffix=suffix) as handle:
            handle.write(audio)
            handle.flush()
            model = _load_whisper(self.server)
            with self.server.model_lock:
                segments, _info = model.transcribe(
                    handle.name,
                    language=language,
                    beam_size=5,
                    vad_filter=True,
                    condition_on_previous_text=True,
                )
                text = " ".join(str(segment.text).strip() for segment in segments).strip()
        if not text:
            raise ValueError("transcription vide")
        self._json(HTTPStatus.OK, {"text": text})

    def _speak(self) -> None:
        if self.headers.get_content_type() != "application/json":
            raise ValueError("JSON requis")
        raw = self._body(128_000)
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("objet JSON requis")
        text = value.get("input")
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
            raise ValueError("texte TTS invalide")
        voice = str(value.get("voice") or self.server.config["tts_voice"])
        if voice != str(self.server.config["tts_voice"]):
            raise ValueError("voix non autorisée")
        command = [
            "espeak-ng",
            "--stdout",
            "-v",
            voice,
            "-s",
            str(int(self.server.config["tts_speed"])),
            "--stdin",
        ]
        result = subprocess.run(
            command,
            input=text.encode("utf-8"),
            check=True,
            capture_output=True,
            timeout=60,
        )
        audio = result.stdout
        if not audio.startswith(b"RIFF"):
            raise RuntimeError("synthèse vocale invalide")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(audio)))
        self.end_headers()
        self.wfile.write(audio)


def make_server(
    repo_root: Path, runtime: Path, token: str, port: int | None = None
) -> SpeechServer:
    policy = root_contract(repo_root, "webui_policy.yaml")
    speech = dict(policy["speech"])
    if speech.get("enabled") is not True:
        raise ValueError("voix locale désactivée")
    if str(speech.get("host")) != "127.0.0.1":
        raise ValueError("service vocal loopback requis")
    if len(token) < 32:
        raise ValueError("jeton vocal privé requis")
    server = SpeechServer(
        ("127.0.0.1", int(speech["port"]) if port is None else port),
        SpeechHandler,
    )
    speech["model_root"] = runtime / "models/whisper"
    server.token = token
    server.config = speech
    server.model_lock = threading.Lock()
    return server


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--prepare", action="store_true")
    args = parser.parse_args()
    if args.prepare:
        prepare(args.root, args.runtime_root)
        print("SPEECH_PREPARE=PASS")
        return
    if args.token_file is None:
        raise ValueError("--token-file requis")
    if args.token_file.is_symlink() or args.token_file.stat().st_mode & 0o077:
        raise PermissionError("jeton vocal privé 0600 requis")
    token = args.token_file.read_text(encoding="utf-8").strip()
    with make_server(args.root, args.runtime_root, token) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
