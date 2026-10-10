"""Render a private personal Open WebUI deployment without storing gateway credentials."""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any

from clawfedora.core_config import root_contract
from clawfedora.project_common import assert_no_symlinks


def _secret(path: Path) -> str:
    if not path.exists():
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write(secrets.token_hex(32) + "\n")
    if path.is_symlink() or path.stat().st_mode & 0o077:
        raise ValueError("secret privé 0600 requis")
    value = path.read_text().strip()
    if not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ValueError("secret d’intégration invalide")
    return value


def environment(
    repo_root: Path,
    token: str,
    secret: str,
    speech_token: str,
    *,
    sealed: bool,
) -> dict[str, str]:
    policy = root_contract(repo_root, "webui_policy.yaml")
    disabled = (
        "ENABLE_CONTEXT_COMPACTION",
        "ENABLE_MEMORY_SYSTEM_CONTEXT",
        "ENABLE_MEMORY_BACKGROUND_REVIEW",
        "ENABLE_MEMORIES",
        "ENABLE_CALENDAR",
        "ENABLE_NOTES",
        "ENABLE_EVALUATION_ARENA_MODELS",
        "USER_PERMISSIONS_CHAT_MULTIPLE_MODELS",
        "USER_PERMISSIONS_CHAT_CALL",
        "ENABLE_OLLAMA_API",
        "ENABLE_AUTOMATIONS",
        "ENABLE_SUBAGENTS",
        "ENABLE_TITLE_GENERATION",
        "ENABLE_TAGS_GENERATION",
        "ENABLE_FOLLOW_UP_GENERATION",
        "ENABLE_SEARCH_QUERY_GENERATION",
        "ENABLE_RETRIEVAL_QUERY_GENERATION",
        "ENABLE_CODE_EXECUTION",
        "ENABLE_CODE_INTERPRETER",
        "ENABLE_IMAGE_GENERATION",
        "ENABLE_WEB_SEARCH",
        "ENABLE_COMMUNITY_SHARING",
        "ENABLE_FORWARD_USER_INFO_HEADERS",
        "USER_PERMISSIONS_CHAT_WEB_UPLOAD",
        "ENABLE_PERSISTENT_CONFIG",
        "ENABLE_API_KEY",
    )
    return {
        **dict.fromkeys(disabled, "false"),
        "USER_PERMISSIONS_CHAT_FILE_UPLOAD": "true",
        "USER_PERMISSIONS_CHAT_STT": "true",
        "USER_PERMISSIONS_CHAT_TTS": "true",
        "HOST": "127.0.0.1",
        "PORT": str(policy["web_port"]),
        "UVICORN_WORKERS": "1",
        "WEBUI_AUTH": "true",
        "ENABLE_SIGNUP": "false" if sealed else "true",
        "DEFAULT_USER_ROLE": "pending",
        "WEBUI_SECRET_KEY": secret,
        "ENABLE_OPENAI_API": "true",
        "OPENAI_API_BASE_URL": "http://127.0.0.1:18891/v1",
        "OPENAI_API_KEY": token,
        "DEFAULT_MODELS": "openclaw/chef-operations",
        "OFFLINE_MODE": "true",
        "BYPASS_EMBEDDING_AND_RETRIEVAL": "true",
        "DEFAULT_LOCALE": "fr-FR",
        "WEBUI_NAME": "Atelier IA Fedora",
        "WEBUI_BANNERS": json.dumps(
            [
                {
                    "id": "clawfedora-projects",
                    "type": "info",
                    "title": "Piloter les projets",
                    "content": "Importer, approuver et livrer: [ouvrir l’atelier Projets](http://127.0.0.1:18890).",
                    "dismissible": False,
                    "timestamp": 0,
                }
            ],
            ensure_ascii=False,
        ),
        "AIOHTTP_CLIENT_TIMEOUT": "660",
        "AUDIO_STT_ENGINE": "openai",
        "AUDIO_STT_MODEL": "clawfedora-whisper",
        "AUDIO_STT_OPENAI_API_BASE_URL": "http://127.0.0.1:18893/v1",
        "AUDIO_STT_OPENAI_API_KEY": speech_token,
        "AUDIO_STT_OPENAI_API_REQUEST_FORMAT": "multipart",
        "AUDIO_STT_SUPPORTED_CONTENT_TYPES": (
            "audio/mpeg,audio/mp3,audio/wav,audio/x-wav,audio/webm,audio/ogg,audio/flac,"
            "audio/mp4,video/webm,video/mp4"
        ),
        "AUDIO_TTS_ENGINE": "openai",
        "AUDIO_TTS_MODEL": "clawfedora-tts",
        "AUDIO_TTS_VOICE": "fr-fr",
        "AUDIO_TTS_OPENAI_API_BASE_URL": "http://127.0.0.1:18893/v1",
        "AUDIO_TTS_OPENAI_API_KEY": speech_token,
    }


def render(repo_root: Path, runtime: Path, unit_root: Path) -> dict[str, Any]:
    for path in (repo_root, runtime, unit_root):
        if not path.is_absolute() or not re.fullmatch(r"[A-Za-z0-9_./-]+", str(path)):
            raise ValueError("chemins absolus sans espace ni caractères systemd spéciaux requis")
        for parent in (path, *path.parents):
            if parent.is_symlink():
                raise ValueError("chemin lié interdit")
    if not (runtime / ".openclaw-fedora-runtime").is_file():
        raise ValueError("runtime géré requis")
    state = runtime / "state/webui"
    if (runtime / "state").is_symlink() or state.is_symlink():
        raise ValueError("état WebUI lié interdit")
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    assert_no_symlinks(state, label="WebUI")
    state.chmod(0o700)
    (state / "data").mkdir(exist_ok=True, mode=0o700)
    token = _secret(state / "bridge.token")
    secret = _secret(state / "session.key")
    speech_token = _secret(state / "speech.token")
    env = environment(
        repo_root,
        token,
        secret,
        speech_token,
        sealed=(state / "sealed").exists(),
    )
    env_path = state / "webui.env"
    env_path.write_text("\n".join(f"{key}={value}" for key, value in env.items()) + "\n")
    env_path.chmod(0o600)
    policy = root_contract(repo_root, "webui_policy.yaml")
    python = runtime / "runtime/venv/bin/python"
    unit_root.mkdir(parents=True, exist_ok=True)
    common = "\n[Service]\nUMask=0077\nRestart=on-failure\nRestartSec=5\n"
    bridge = (
        "[Unit]\nDescription=Atelier IA - admission des conversations\n"
        "After=openclaw-gateway.service\n"
        + common
        + f"Environment=OPENCLAW_LOCAL_FEDORA_ROOT={runtime}\n"
        + f"ExecStart={python} -m clawfedora.webui_bridge "
        + f"--root {repo_root} --runtime-root {runtime}\n"
        + "NoNewPrivileges=true\n\n[Install]\nWantedBy=default.target\n"
    )
    speech = (
        "[Unit]\nDescription=Atelier IA - voix locale\n"
        + common
        + f"ExecStart={python} -m clawfedora.speech_server "
        + f"--root {repo_root} --runtime-root {runtime} --token-file {state / 'speech.token'}\n"
        + "NoNewPrivileges=true\nPrivateTmp=true\n\n[Install]\nWantedBy=default.target\n"
    )
    webui = (
        "[Unit]\nDescription=Atelier IA - Open WebUI personnel\n"
        "After=clawfedora-webui-bridge.service clawfedora-speech.service\n"
        "Requires=clawfedora-webui-bridge.service clawfedora-speech.service\n"
        + common
        + "ExecStart=/usr/bin/podman run --rm --name clawfedora-webui "
        "--label io.clawfedora.managed=true --network host --cap-drop ALL "
        "--security-opt no-new-privileges "
        + f"--memory {policy['memory_limit']} --cpus {policy['cpu_limit']} --pids-limit 256 "
        + f"--env-file {env_path} --volume {state / 'data'}:/app/backend/data:Z "
        + f"{policy['image']}\n"
        + "ExecStop=/usr/bin/podman stop --ignore --time 10 clawfedora-webui\n"
        + "TimeoutStartSec=120\nTimeoutStopSec=30\n\n[Install]\nWantedBy=default.target\n"
    )
    dashboard = (
        "[Unit]\nDescription=Atelier IA - projets\n"
        + common
        + f"ExecStart={python} -m clawfedora.cli --root {repo_root} dashboard "
        + f"--serve --runtime-root {runtime}\n"
        + "NoNewPrivileges=true\n\n[Install]\nWantedBy=default.target\n"
    )
    for name, content in (
        ("clawfedora-webui-bridge", bridge),
        ("clawfedora-speech", speech),
        ("clawfedora-webui", webui),
        ("clawfedora-dashboard", dashboard),
    ):
        unit = unit_root / f"{name}.service"
        if unit.is_symlink():
            raise ValueError("unité liée interdite")
        header = "# Managed by OPENCLAW_LOCAL_FEDORA\n"
        if unit.exists() and not unit.read_text().startswith(header):
            raise ValueError("unité existante non gérée: " + name)
        unit.write_text(header + content)
    (state / "enabled").touch(mode=0o600)
    return {
        "image": policy["image"],
        "webui": "http://127.0.0.1:3000",
        "projects": "http://127.0.0.1:18890",
        "sealed": (state / "sealed").exists(),
    }


def seal(repo_root: Path, runtime: Path) -> None:
    state = runtime / "state/webui"
    assert_no_symlinks(state, label="WebUI")
    database = state / "data/webui.db"
    plugin = repo_root / "plugins/openwebui/clawfedora_files.py"
    source = plugin.read_text(encoding="utf-8")
    if not source.strip() or plugin.is_symlink():
        raise ValueError("filtre Open WebUI géré absent ou lié")
    with closing(sqlite3.connect(database)) as db:
        users = db.execute('SELECT id, role FROM "user"').fetchall()
        if len(users) != 1 or users[0][1] != "admin":
            raise ValueError(
                "créer un seul compte administrateur dans l’interface avant de fermer les inscriptions"
            )
        admin_id = str(users[0][0])
        now = int(time.time())
        meta = json.dumps(
            {"description": "Transmet les uploads au moteur d'ingestion local ClawFedora."},
            ensure_ascii=False,
        )
        db.execute(
            '''
            INSERT INTO "function"
              (id, user_id, name, type, content, meta, valves, is_active, is_global,
               updated_at, created_at)
            VALUES (?, ?, ?, 'filter', ?, ?, NULL, 1, 1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              user_id=excluded.user_id,
              name=excluded.name,
              type='filter',
              content=excluded.content,
              meta=excluded.meta,
              is_active=1,
              is_global=1,
              updated_at=excluded.updated_at
            ''',
            (
                "clawfedora_files",
                admin_id,
                "ClawFedora — pièces jointes",
                source,
                meta,
                now,
                now,
            ),
        )
        db.commit()
    (state / "sealed").touch(mode=0o600)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("render", "seal"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--unit-root", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "seal":
        seal(args.root, args.runtime_root)
    print(json.dumps(render(args.root, args.runtime_root, args.unit_root)))


if __name__ == "__main__":
    main()
