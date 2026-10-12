"""Opt-in, fail-closed server-side streaming for the native Fedora Gateway.

Only the Mentor's plain local chat is eligible. The Gateway HTTP bearer is
operator-privileged and must never be exposed to Open WebUI or model tools.
"""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any

from clawfedora.project_worker import AgentRunner, openclaw_runner
from clawfedora.stream_transport import GATEWAY_PORT, gateway_local_deltas

MARKER = Path("state/webui/native-sse.enabled")
APPROVAL = "local-mentor-sse-v1"


def opted_in(runtime: Path) -> bool:
    """Explicit 0600 opt-in, never enabled by an environment variable or API."""
    file = runtime / MARKER
    try:
        mode = file.lstat().st_mode
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(mode) or mode & 0o077:
        raise ValueError("activation SSE non privée ou fichier lié")
    if file.read_text(encoding="utf-8").strip() != APPROVAL:
        raise ValueError("activation SSE non reconnue")
    if not (runtime / ".openclaw-fedora-runtime").is_file():
        raise ValueError("SSE exige un runtime géré")
    return True


def _private_config(runtime: Path) -> dict[str, Any]:
    path = runtime / "state/openclaw/openclaw.json"
    # Refuse symlinks, directory targets and a group/world-readable operator
    # credential. Access is confined to the service account's runtime.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "r", encoding="utf-8") as reader:
        mode = os.fstat(reader.fileno()).st_mode
        if not stat.S_ISREG(mode) or mode & 0o077:
            raise ValueError("configuration Gateway non privée (0600 requis)")
        config: Any = json.load(reader)
    if not isinstance(config, dict):
        raise ValueError("configuration Gateway invalide")
    return config


def operator_token(runtime: Path) -> str:
    """Read the *existing* Gateway credential; never generate or log a new one."""
    if not opted_in(runtime):
        raise ValueError("streaming non activé")
    config = _private_config(runtime)
    gateway = config.get("gateway")
    if not isinstance(gateway, dict):
        raise ValueError("configuration Gateway absente")
    http = gateway.get("http")
    endpoints = http.get("endpoints") if isinstance(http, dict) else None
    chat = endpoints.get("chatCompletions") if isinstance(endpoints, dict) else None
    if (
        gateway.get("mode") != "local"
        or gateway.get("bind") != "loopback"
        or gateway.get("port", GATEWAY_PORT) != GATEWAY_PORT
        or not isinstance(chat, dict)
        or chat.get("enabled") is not True
    ):
        raise ValueError("Gateway SSE non activé uniquement en boucle locale")
    auth = gateway.get("auth")
    if not isinstance(auth, dict) or auth.get("mode") != "token":
        raise ValueError("Gateway SSE exige une authentification par jeton")
    value = auth.get("token")
    if isinstance(value, dict):
        # Accept only the explicit environment reference supported by
        # OpenClaw. No arbitrary filename, command or shell interpolation.
        if (
            value.get("source") != "env"
            or value.get("id") != "OPENCLAW_GATEWAY_TOKEN"
        ):
            raise ValueError("référence du jeton Gateway non autorisée")
        value = os.environ.get("OPENCLAW_GATEWAY_TOKEN")
    if (
        not isinstance(value, str)
        or not 32 <= len(value) <= 4096
        or any(ch.isspace() for ch in value)
        or value.startswith(chr(36) + "{")
    ):
        raise ValueError("jeton Gateway privé indisponible")
    return value


def native_source(
    runtime: Path, repo_root: Path, *, preflight: AgentRunner | None = None
) -> Callable[[str, str, str], Generator[str, None, None]]:
    """Check CLI-equivalent preflight before issuing any Gateway HTTP request.

    This factory returns a normal function, not a generator: failures before
    HTTP headers yield a 409 without streaming an untrusted partial answer.
    The WebUI handler keeps the shared worker lock through generator closure.
    """
    checker = preflight or openclaw_runner(runtime, repo_root, preflight_only=True)

    def source(role: str, prompt: str, session: str) -> Generator[str, None, None]:
        if role != "chef-operations":
            raise ValueError("SSE réservé au Mentor local")
        # The admission preflight is exactly the CLI runner's version, Ollama
        # digest, seven-role roster, read-only tools and no-fallback gate.
        checker(role, prompt, session)
        token = operator_token(runtime)
        return gateway_local_deltas(role, prompt, session, operator_token=token)

    return source
