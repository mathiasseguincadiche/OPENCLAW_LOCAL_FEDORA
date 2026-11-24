"""Private, durable Atelier chats using the existing OpenClaw policy bridge.

No Open WebUI account/container or LM Studio plugin is needed. Browser input never
selects a model, injects history, or obtains the internal bridge bearer.
"""
from __future__ import annotations

import fcntl
import json
import os
import platform
import re
import secrets
import stat
import subprocess
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

from clawfedora import chat_artifacts, chat_projects
from clawfedora.chat_context import select_history
from clawfedora.core_config import AGENT_IDS
from clawfedora.project_common import PROJECT_ID_RE
from clawfedora.project_worker import worker_lock
from clawfedora.webui_bridge import make_server as make_policy_bridge

CHAT_ID = re.compile(r"^[a-f0-9]{32}$")
MAX_CHAT_BYTES = 850_000
MAX_USER_BYTES = 8_000
MAX_MESSAGES = 900
MAX_RECOVERIES = 40


def _directory(runtime: Path, *, create: bool) -> Path:
    state = runtime / "state"
    directory = state / "atelier-chats"
    if state.is_symlink() or directory.is_symlink():
        raise ValueError("Stockage des conversations lié : accès refusé")
    if create:
        state.mkdir(exist_ok=True, mode=0o700)
        directory.mkdir(exist_ok=True, mode=0o700)
        directory.chmod(0o700)
    elif not directory.is_dir():
        return directory
    if directory.exists() and (directory.stat().st_mode & 0o077):
        raise ValueError("Stockage des conversations non privé (0700 requis)")
    return directory


def _path(runtime: Path, identifier: str, *, create_dir: bool = False) -> Path:
    if not isinstance(identifier, str) or not CHAT_ID.fullmatch(identifier):
        raise ValueError("Identifiant de conversation invalide")
    path = _directory(runtime, create=create_dir) / (identifier + ".json")
    if path.is_symlink():
        raise ValueError("Conversation liée : accès refusé")
    return path


def _save(runtime: Path, document: dict[str, Any]) -> None:
    path = _path(runtime, document["id"], create_dir=True)
    data = (json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    if len(data) > MAX_CHAT_BYTES:
        raise ValueError("Conversation trop longue : ouvrir un nouveau fil")
    temporary = path.with_name(path.name + "." + secrets.token_hex(8) + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def turn_lock(runtime: Path, identifier: str) -> Iterator[None]:
    """Serialize JSON and SSE turns for the same durable chat, never block indefinitely."""
    chat = _path(runtime, identifier)
    if not chat.is_file():
        raise ValueError("Conversation introuvable")
    lock = chat.with_suffix(".lock")
    fd = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    with os.fdopen(fd, "w") as handle:
        mode = os.fstat(handle.fileno()).st_mode
        if not stat.S_ISREG(mode) or mode & 0o077:
            raise ValueError("Verrou de conversation non privé")
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("Une réponse est déjà en cours dans ce fil") from exc
        yield


def pending_intent(message: str) -> dict[str, Any]:
    """A fresh identifier prevents a stale recovery from clearing a newer turn."""
    return {"id": uuid.uuid4().hex, "message": message, "started": int(time.time())}


def _validate_intent(value: Any) -> None:
    # Older chats have no unique id. Keep them recoverable without rewriting
    # historical files; all new intents use a fresh server-generated identifier.
    if (
        not isinstance(value, dict)
        or set(value) not in ({"message", "started"}, {"id", "message", "started"})
        or not isinstance(value.get("message"), str) or not value["message"].strip()
        or len(value["message"].encode()) > MAX_USER_BYTES
        or type(value.get("started")) is not int or value["started"] < 0
        or (
            "id" in value and (
                not isinstance(value["id"], str) or not CHAT_ID.fullmatch(value["id"])
            )
        )
    ):
        raise ValueError("Intention de discussion invalide")


def _validate_recovery_log(document: dict[str, Any]) -> None:
    records = document.get("recoveries", [])
    if not isinstance(records, list) or len(records) > MAX_RECOVERIES:
        raise ValueError("Journal de récupération invalide")
    for record in records:
        if (
            not isinstance(record, dict)
            or set(record) != {"intent", "recorded_at", "after_messages", "outcome"}
            or record["outcome"] != "ABANDONED_UNCERTAIN"
            or type(record["recorded_at"]) is not int or record["recorded_at"] < 0
            or type(record["after_messages"]) is not int
            or not 0 <= record["after_messages"] <= len(document["messages"])
        ):
            raise ValueError("Journal de récupération invalide")
        _validate_intent(record["intent"])


def read(runtime: Path, identifier: str) -> dict[str, Any]:
    path = _path(runtime, identifier)
    if (not path.is_file() or path.stat().st_size > MAX_CHAT_BYTES
            or path.stat().st_mode & 0o077):
        raise ValueError("Conversation introuvable, non privée (0600) ou illisible")
    document = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(document, dict) or document.get("id") != identifier
        or document.get("agent") not in AGENT_IDS
        or not isinstance(document.get("messages"), list)
        or len(document["messages"]) > MAX_MESSAGES
    ):
        raise ValueError("Historique de conversation invalide")
    project = document.get("project")
    if project is not None and (
        not isinstance(project, str) or not PROJECT_ID_RE.fullmatch(project)
    ):
        raise ValueError("Projet enregistré invalide")
    if any(
        not isinstance(msg, dict)
        or msg.get("role") not in {"user", "assistant"}
        or not isinstance(msg.get("content"), str)
        for msg in document["messages"]
    ):
        raise ValueError("Messages enregistrés invalides")
    for message in document["messages"]:
        if "artifacts" not in message:
            continue
        artifacts = message["artifacts"]
        if (
            message["role"] != "assistant" or not isinstance(artifacts, list)
            or len(artifacts) > chat_artifacts.MAX_FILES_PER_TURN
        ):
            raise ValueError("fichiers de conversation invalides")
        for reference in artifacts:
            chat_artifacts.validate_reference(reference)
    if document.get("pending") is not None:
        _validate_intent(document["pending"])
    _validate_recovery_log(document)
    return document


def recover(
    runtime: Path, identifier: str, expected_pending: Any, *, human_approved: bool,
) -> dict[str, Any]:
    """Abandon only an explicitly acknowledged intent; never replay or cancel work.

    The local locks exclude active managed turns, not independent remote effects
    or a Gateway process whose cancellation has not been physically qualified.
    """
    if human_approved is not True:
        raise ValueError("Vérification et confirmation humaine explicites requises")
    _validate_intent(expected_pending)
    with turn_lock(runtime, identifier), worker_lock(runtime, allow_gaming=True):
        document = read(runtime, identifier)
        pending = document.get("pending")
        if pending is None or pending != expected_pending:
            raise ValueError("Intention obsolète : recharger la conversation")
        records = document.setdefault("recoveries", [])
        if len(records) >= MAX_RECOVERIES:
            raise ValueError("Journal de récupération plein : ouvrir un nouveau fil")
        records.append({
            "intent": pending,
            "recorded_at": int(time.time()),
            "after_messages": len(document["messages"]),
            "outcome": "ABANDONED_UNCERTAIN",
        })
        document["pending"] = None
        document["updated"] = int(time.time())
        # A single atomic write keeps the previous pending intact if saving fails.
        _save(runtime, document)
        return document


def download(runtime: Path, identifier: str, receipt: str, extension: str) -> tuple[bytes, str]:
    """Resolve only an artifact committed in this conversation, not a workspace listing."""
    document = read(runtime, identifier)
    if document["project"] and chat_projects.open_project(runtime, document["project"]) is None:
        raise ValueError("Projet du fil introuvable")
    for message in document["messages"]:
        for reference in message.get("artifacts", []):
            if reference["receipt"] == receipt and reference["format"] == extension:
                return chat_artifacts.native_bytes(runtime, document["agent"], reference)
    raise ValueError("Fichier absent de cette conversation")


def assistant_message(document: dict[str, Any], reply: str) -> dict[str, Any]:
    """Attach ephemeral receipt metadata only when the caller commits a complete turn."""
    message: dict[str, Any] = {"role": "assistant", "content": reply}
    references = document.pop("_turn_artifacts", [])
    if references:
        message["artifacts"] = [chat_artifacts.validate_reference(item) for item in references]
    return message


def listing(runtime: Path) -> dict[str, Any]:
    directory = _directory(runtime, create=False)
    chats: list[dict[str, Any]] = []
    if directory.is_dir():
        for path in sorted(directory.glob("*.json"))[:100]:
            if not CHAT_ID.fullmatch(path.stem) or path.is_symlink():
                continue
            try:
                item = read(runtime, path.stem)
                chats.append({
                    "id": item["id"], "title": item["title"],
                    "agent": item["agent"], "project": item["project"],
                    "updated": item["updated"],
                    "pending": item.get("pending") is not None,
                })
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                continue
    chats.sort(key=lambda item: item["updated"], reverse=True)
    return {"agents": list(AGENT_IDS), "chats": chats}


def create(runtime: Path, project: str | None, agent: str) -> dict[str, Any]:
    if agent not in AGENT_IDS:
        raise ValueError("Rôle OpenClaw inconnu")
    if project is not None and (
        not isinstance(project, str) or not PROJECT_ID_RE.fullmatch(project)
        or chat_projects.open_project(runtime, project) is None
    ):
        raise ValueError("Projet ClawFedora introuvable")
    now = int(time.time())
    document: dict[str, Any] = {
        "id": uuid.uuid4().hex, "project": project, "agent": agent,
        "title": "Nouvelle discussion", "created": now, "updated": now,
        "messages": [], "pending": None,
    }
    _save(runtime, document)
    return document


def fedora_status() -> str:
    """Fixed read-only inventory. No model-provided command, args or privilege."""
    services = [
        (["/usr/bin/systemctl", "is-active", "ollama.service"], "Ollama (système)"),
        (["/usr/bin/systemctl", "--user", "is-active", "openclaw-gateway.service"],
         "OpenClaw (utilisateur)"),
        (["/usr/bin/systemctl", "--user", "is-active", "clawfedora-dashboard.service"],
         "Atelier (utilisateur)"),
    ]
    lines = ["Diagnostic Fedora en lecture seule", "Noyau : " + platform.release()]
    for command, name in services:
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, check=False, timeout=3,
            )
            state = result.stdout.strip()
            if state not in {"active", "inactive", "failed", "activating", "deactivating"}:
                state = "indisponible"
        except (OSError, subprocess.TimeoutExpired):
            state = "indisponible"
        lines.append(name + " : " + state)
    lines.append("Aucun service ni application n'a été modifié.")
    return "\n".join(lines)


def fedora_applications() -> str:
    """List installed Flatpak apps without launching or modifying anything."""
    try:
        response = subprocess.run(
            ["/usr/bin/flatpak", "list", "--app", "--columns=application,name"],
            capture_output=True, text=True, check=False, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "Flatpak indisponible ; aucun changement effectué."
    if response.returncode:
        return "Inventaire Flatpak indisponible ; aucun changement effectué."
    rows = [row[:160] for row in response.stdout.splitlines() if row.strip()][:30]
    return ("Applications Flatpak installées (30 max, lecture seule) :\n"
            + ("\n".join(rows) if rows else "Aucune application détectée."))


def _policy_answer(
    repo_root: Path, runtime: Path, document: dict[str, Any], message: str
) -> str:
    # This bearer exists only in this process and is never delivered to the browser.
    bearer = secrets.token_hex(32)
    history = [
        {"role": "assistant", "content": chat_projects.bridge_reply(
            document["project"], "Contexte de conversation Atelier figé."
        )}
    ] if document["project"] else []
    relevant_history, context_stats = select_history(document["messages"], message)
    history.extend(relevant_history)
    history.append({"role": "user", "content": message})
    # Counts only; the full, unmodified transcript stays in the private chat file.
    document["context_window"] = context_stats
    payload: dict[str, Any] = {
        "model": "openclaw/" + document["agent"], "stream": False,
        "messages": history,
    }
    captured: list[dict[str, Any]] = []
    with make_policy_bridge(repo_root, runtime, bearer, 0) as bridge:
        bridge.artifact_sink = captured.extend
        worker = threading.Thread(target=bridge.serve_forever, daemon=True)
        worker.start()
        try:
            client = HTTPConnection("127.0.0.1", bridge.server_port, timeout=650)
            try:
                client.request(
                    "POST", "/v1/chat/completions", body=json.dumps(payload),
                    headers={"Authorization": "Bearer " + bearer,
                             "Content-Type": "application/json"},
                )
                response = client.getresponse()
                raw = response.read(150_000)
                value = json.loads(raw)
                if response.status != 200:
                    reason = value.get("error", {}).get("message", "réponse refusée")
                    raise ValueError("Pont OpenClaw : " + str(reason)[:250])
                answer = value["choices"][0]["message"]["content"]
                if not isinstance(answer, str) or len(answer.encode()) > 100_000:
                    raise ValueError("Réponse OpenClaw invalide")
                document["_turn_artifacts"] = captured
                return answer
            finally:
                client.close()
        finally:
            bridge.shutdown()
            worker.join(timeout=5)


def send(repo_root: Path, runtime: Path, identifier: str, message: str) -> dict[str, Any]:
    with turn_lock(runtime, identifier):
        return _send_locked(repo_root, runtime, identifier, message)


def _send_locked(
    repo_root: Path, runtime: Path, identifier: str, message: str,
) -> dict[str, Any]:
    if not isinstance(message, str) or not message.strip() or (
        len(message.encode("utf-8")) > MAX_USER_BYTES
    ):
        raise ValueError("Message non vide limité à 8 Ko")
    document = read(runtime, identifier)
    if document.get("pending") is not None:
        raise ValueError(
            "Tour précédent incertain : vérifier l'état du projet avant de réessayer. "
            "Aucune relance automatique d'une action potentiellement exécutée."
        )
    if len(document["messages"]) + 2 > MAX_MESSAGES:
        raise ValueError("Historique trop long : ouvrir une autre conversation")
    if document["project"] and chat_projects.open_project(runtime, document["project"]) is None:
        raise ValueError("Projet du fil introuvable : aucune action autorisée")
    command = chat_projects.parse_command(message)
    if command and command[0] in {"projet", "quitter"}:
        reply = chat_projects.bridge_reply(
            document["project"], "Le projet de cette conversation est immuable. "
            "Ouvrir un nouveau fil pour choisir un autre projet."
        )
    elif command and command[0] == "continuer":
        # This native command is read-only; it never goes to a model or replays
        # an old thread, and the selected project is immutable.
        reply = chat_projects.run_command(
            repo_root, runtime, command[0], command[1], document["project"],
        )
    elif message.strip() == "!fedora etat":
        reply = chat_projects.bridge_reply(document["project"], fedora_status())
    elif message.strip() == "!fedora applications":
        reply = chat_projects.bridge_reply(document["project"], fedora_applications())
    else:
        # Persist the intent BEFORE handing off to the policy/approval engine.
        # An interrupted action must never be retried implicitly.
        document["pending"] = pending_intent(message)
        _save(runtime, document)
        reply = _policy_answer(repo_root, runtime, document, message)
    document["messages"].extend([
        {"role": "user", "content": message},
        assistant_message(document, reply),
    ])
    if document["title"] == "Nouvelle discussion":
        document["title"] = message.strip().replace("\n", " ")[:72]
    document["pending"] = None
    document["updated"] = int(time.time())
    _save(runtime, document)
    return document
