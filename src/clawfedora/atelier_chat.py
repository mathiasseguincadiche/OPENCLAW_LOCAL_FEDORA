"""Private, durable Atelier chats using the existing OpenClaw policy bridge.

No Open WebUI account/container or LM Studio plugin is needed. Browser input never
selects a model, injects history, or obtains the internal bridge bearer.
"""
from __future__ import annotations

import json
import os
import platform
import re
import secrets
import subprocess
import threading
import time
import uuid
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

from clawfedora import chat_projects
from clawfedora.core_config import AGENT_IDS
from clawfedora.project_common import PROJECT_ID_RE
from clawfedora.webui_bridge import make_server as make_policy_bridge

CHAT_ID = re.compile(r"^[a-f0-9]{32}$")
MAX_CHAT_BYTES = 850_000
MAX_USER_BYTES = 8_000
MAX_MESSAGES = 900


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


def read(runtime: Path, identifier: str) -> dict[str, Any]:
    path = _path(runtime, identifier)
    if not path.is_file() or path.stat().st_size > MAX_CHAT_BYTES:
        raise ValueError("Conversation introuvable ou illisible")
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
    return document


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
    history.extend(document["messages"])
    history.append({"role": "user", "content": message})
    payload: dict[str, Any] = {
        "model": "openclaw/" + document["agent"], "stream": False,
        "messages": history,
    }
    with make_policy_bridge(repo_root, runtime, bearer, 0) as bridge:
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
                return answer
            finally:
                client.close()
        finally:
            bridge.shutdown()
            worker.join(timeout=5)


def send(repo_root: Path, runtime: Path, identifier: str, message: str) -> dict[str, Any]:
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
    elif message.strip() == "!fedora etat":
        reply = chat_projects.bridge_reply(document["project"], fedora_status())
    else:
        # Persist the intent BEFORE handing off to the policy/approval engine.
        # An interrupted action must never be retried implicitly.
        document["pending"] = {"message": message, "started": int(time.time())}
        _save(runtime, document)
        reply = _policy_answer(repo_root, runtime, document, message)
    document["messages"].extend([
        {"role": "user", "content": message},
        {"role": "assistant", "content": reply},
    ])
    if document["title"] == "Nouvelle discussion":
        document["title"] = message.strip().replace("\n", " ")[:72]
    document["pending"] = None
    document["updated"] = int(time.time())
    _save(runtime, document)
    return document
