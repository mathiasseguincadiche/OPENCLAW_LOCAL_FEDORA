"""Open WebUI Action: controlled project shortcuts for a single-admin Fedora atelier.

The tool never interprets or executes model output or approves a project
transition by itself. Form input and the selected marker are sent only to
the existing authenticated OpenClaw bridge on loopback, never to a cloud host.
The bridge issues a distinct one-time code for creating the project.
"""

from __future__ import annotations

import asyncio
import http.client
import json
import os
import re
from typing import Any
from urllib.parse import urlencode

# Only fixed commands are exposed. The bridge performs all project-state checks.
# Every state-changing button requires an affirmative browser confirmation first.
PROJECT_ACTIONS = {
    "validate": ("!valider", "Afficher le brouillon et préparer sa confirmation humaine ?"),
    "analyze": ("!analyser", "Lancer l'analyse du projet sélectionné ?"),
    "plan": ("!planifier", "Préparer un plan pour le projet sélectionné ?"),
    "start": ("!lancer", "Démarrer les tâches du projet approuvé ?"),
    "pause": ("!pause", "Mettre en pause le projet sélectionné ?"),
    "resume": ("!reprendre", "Reprendre les tâches de ce projet ?"),
    "audit": ("!auditer", "Demander l'audit du travail terminé ?"),
    "review": ("!relire", "Demander une seconde relecture ?"),
    "deliver": ("!livrer", "Préparer la livraison ? Une confirmation distincte restera requise."),
}

READ_ONLY_ACTIONS = {
    "projects": "!projets",
    "status": "!etat",
    "sources": "!sources",
    "help": "!aide",
    "models": "!modele",
    "budget": "!budget",
}

PROJECT_MENU = {
    "analyze": "Analyser les sources", "answer": "Répondre à une précision",
    "plan": "Préparer le plan", "validate": "Relire et préparer la validation",
    "start": "Lancer les tâches", "pause": "Mettre en pause", "resume": "Reprendre",
    "audit": "Valider les livrables", "review": "Relire le projet",
    "revise": "Demander une révision", "deliver": "Préparer la livraison",
}
RESOURCE_MENU = {
    "projects": "Lister les projets", "sources": "Voir les sources du projet",
    "models": "Quel modèle choisir ?", "budget": "Consulter le budget cloud",
    "help": "Toutes les commandes",
}


def _project_id(history: object) -> str | None:
    marker = _project_marker(history)
    if marker is None:
        return None
    identifier = marker.removeprefix("📁 Projet : ").removesuffix(" · pont")
    if re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}[a-z0-9]", identifier) is None:
        raise ValueError("Projet non reconnu. Utilisez Choisir un projet.")
    return identifier


def atelier_view(key: str, current: str | None = None, *, port: int = 18891) -> dict[str, Any]:
    """Read only bounded metadata from the authenticated local bridge."""
    if not isinstance(key, str) or len(key) < 32:
        raise ValueError("jeton du pont local absent")
    path = "/v1/atelier" + ("?" + urlencode({"project": current}) if current else "")
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=8)
    try:
        connection.request("GET", path, headers={"Authorization": "Bearer " + key})
        response = connection.getresponse()
        raw = response.read(64_001)
        if response.status != 200 or len(raw) > 64_000:
            raise ValueError("État indisponible. Actualisez ou choisissez un projet existant.")
        value = json.loads(raw)
        if not isinstance(value, dict) or not isinstance(value.get("projects"), list):
            raise ValueError("État de l’atelier invalide")
        if len(value["projects"]) > 50 or not isinstance(value.get("activity"), dict):
            raise ValueError("État de l’atelier hors limites")
        return value
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Atelier indisponible. Vérifiez son état dans l’Atelier Projets.") from exc
    finally:
        connection.close()


async def _choose(call: Any, title: str, message: str, choices: dict[str, str]) -> str | None:
    if call is None:
        raise ValueError("formulaire navigateur indisponible")
    answer = await call({"type": "input", "data": {
        "title": title, "message": message, "placeholder": "Choisir…",
        "input": {"type": "select", "options": [
            {"value": key, "label": label} for key, label in choices.items()
        ]},
    }})
    if type(answer) is not str or not answer.strip():
        return None
    if answer not in choices:
        raise ValueError("Choix non proposé. Ouvrez de nouveau le menu.")
    return answer


def _selection(body: dict[str, Any], identifier: str) -> dict[str, Any]:
    """Update only this answer's context marker; preserve its content and the other turns."""
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ValueError("Utilisez ce bouton sous une réponse de la conversation.")
    last = messages[-1]
    if (
        not isinstance(last, dict) or last.get("role") != "assistant"
        or not isinstance(last.get("id"), str) or not last["id"]
        or last["id"] != body.get("id") or not isinstance(last.get("content"), str)
    ):
        raise ValueError("Réponse de conversation non reconnue : utilisez le dernier message.")
    content = last["content"]
    head, separator, rest = content.partition("\n\n")
    bridge = head.endswith(" · pont") and head.startswith("📁")
    if re.fullmatch(r"📁 Projet : [a-z0-9][a-z0-9-]{1,62}[a-z0-9](?: · pont)?", head) or (
        head == "📁 Aucun projet · pont"
    ):
        content = rest if separator else ""
    marker = "📁 Projet : " + identifier + (" · pont" if bridge else "")
    return {"messages": [{"id": last["id"], "role": "assistant",
                          "content": marker + "\n\n" + content}]}


def _project_marker(history: object) -> str | None:
    if not isinstance(history, list):
        raise ValueError("historique invalide")
    # The server revalidates this marker against its project registry.
    for item in reversed(history):
        if not isinstance(item, dict) or item.get("role") != "assistant":
            continue
        content = item.get("content")
        if not isinstance(content, str):
            continue
        marker = content.split("\n", 1)[0][:160]
        if marker.startswith("📁 Projet : "):
            return marker
        if marker.startswith("📁 Aucun projet"):
            return None
    return None


def local_bridge(
    command: str, history: object, *, key: str, port: int = 18891,
    mutation: bool = False, creation_brief: str | None = None,
    clarification: tuple[int, str] | None = None,
    revision: tuple[str, str] | None = None,
) -> str:
    create = creation_brief is not None
    if sum((create, clarification is not None, revision is not None)) > 1:
        raise ValueError("paramètres incompatibles")
    if revision is not None:
        if not mutation or command != "!modifier":
            raise ValueError("révision non autorisée")
        task_id, reason = revision
        if not isinstance(task_id, str) or not isinstance(reason, str):
            raise ValueError("identifiant ou motif de révision invalide")
        task_id = task_id.strip().lower()
        cleaned = " ".join(reason.split())
        if (
            re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}[a-z0-9]", task_id) is None
            or not cleaned or len(cleaned) > 2000 or "\x00" in reason
        ):
            raise ValueError("identifiant ou motif de révision invalide")
        command = f"!modifier {task_id} {cleaned}"
    if clarification is not None:
        if not mutation or command != "!repondre":
            raise ValueError("réponse de précision non autorisée")
        number, answer = clarification
        if (
            type(number) is not int or not 1 <= number <= 30
            or not isinstance(answer, str) or not answer.strip()
            or len(answer) > 1500 or "\x00" in answer
        ):
            raise ValueError("numéro ou réponse de précision invalide")
        cleaned = " ".join(answer.split())
        if len(cleaned) > 1500:
            raise ValueError("réponse trop longue")
        command = f"!repondre {number} {cleaned}"
    if create:
        if not mutation or not command.startswith("!creer ") or len(command) > 200:
            raise ValueError("création non autorisée")
        title = command.removeprefix("!creer ")
        if (
            not title.strip() or len(title) > 193
            or any(char in title for char in ("\n", "\r", "\x00"))
            or not isinstance(creation_brief, str)
            or not creation_brief.strip()
            or len(creation_brief.encode("utf-8")) > 12_000
            or "\x00" in creation_brief
        ):
            raise ValueError("titre ou demande de projet invalide")
    elif mutation and clarification is None and revision is None:
        if command not in {item[0] for item in PROJECT_ACTIONS.values()}:
            raise ValueError("action mutante non autorisée")
    elif not mutation and command not in READ_ONLY_ACTIONS.values():
        raise ValueError("action non autorisée")
    if not isinstance(key, str) or len(key) < 32:
        raise ValueError("jeton du pont local absent")
    marker = _project_marker(history)
    if mutation and not create and marker is None:
        raise ValueError("sélectionner d'abord le projet dans le chat avec !projet <id>")
    # A fixed command and project marker only. Never forward prompt, files or
    # history from the browser to initiate a project mutation.
    recent = ([{"role": "assistant", "content": marker}] if marker else [])
    if creation_brief is not None:
        recent.append({"role": "user", "content": creation_brief})
    recent.append({"role": "user", "content": command})
    payload = {
        "model": "openclaw/chef-operations",
        "stream": False,
        "messages": recent,
    }
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=8)
    try:
        connection.request(
            "POST", "/v1/chat/completions",
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
        )
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError("pont OpenClaw indisponible ou commande refusée")
        raw = response.read(64_001)
        if len(raw) > 64_000:
            raise ValueError("réponse trop volumineuse")
        parsed = json.loads(raw)
        message = parsed["choices"][0]["message"]["content"]
        if not isinstance(message, str):
            raise ValueError("réponse de commande invalide")
        return message[:2_500]
    finally:
        connection.close()


def read_only_bridge(
    command: str, history: object, *, key: str, port: int = 18891
) -> str:
    return local_bridge(command, history, key=key, port=port)


# Namespace metadata distinguishes ClawFedora-owned folders from user folders.
# Open WebUI itself owns the chats, their permissions and their history.
FOLDER_ROOT_NAME = "Projets ClawFedora"
FOLDER_KIND_KEY = "clawfedora_folder_kind"
FOLDER_PROJECT_KEY = "clawfedora_project_id"
FOLDER_SCHEMA_KEY = "clawfedora_schema"
PROJECT_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{1,62}[a-z0-9]")


def _folder_project_rows(view: dict[str, Any]) -> list[dict[str, str]]:
    """Bound the project list obtained from the authenticated local bridge."""
    raw = view.get("projects")
    if not isinstance(raw, list) or len(raw) > 50:
        raise ValueError("registre de projets indisponible ou trop volumineux")
    entries: list[dict[str, str]] = []
    used: set[str] = set()
    for row in raw:
        if not isinstance(row, dict):
            raise ValueError("entrée de projet incorrecte")
        project_id, title = row.get("id"), row.get("title")
        if (
            not isinstance(project_id, str)
            or PROJECT_ID_PATTERN.fullmatch(project_id) is None
            or project_id in used
            or not isinstance(title, str)
            or not title.strip()
            or len(title) > 193
        ):
            raise ValueError("projet invalide ou dupliqué")
        used.add(project_id)
        # Folder names are display-only, not instructions and not file paths.
        clean = " ".join(title.split())
        clean = "".join(char for char in clean if ord(char) >= 32)[:72].strip()
        if not clean:
            clean = project_id
        entries.append({"id": project_id, "title": clean})
    return entries


def _managed(folder: Any, kind: str, project_id: str | None = None) -> bool:
    metadata = getattr(folder, "meta", None)
    if not isinstance(metadata, dict):
        return False
    if metadata.get(FOLDER_SCHEMA_KEY) != 1 or metadata.get(FOLDER_KIND_KEY) != kind:
        return False
    if kind == "project":
        return metadata.get(FOLDER_PROJECT_KEY) == project_id
    return metadata.get(FOLDER_PROJECT_KEY) is None


async def _native_folders_for_projects(
    user_id: str, rows: list[dict[str, str]],
) -> tuple[str, dict[str, str], int]:
    """Create only namespaced native WebUI folders, never migrate chats.

    This function deliberately uses the native installed WebUI 0.12.3 folder
    ORM, not direct SQL and not an admin API token. Existing personal folders
    and conversations are left untouched. Repeat calls are idempotent.
    """
    from open_webui.models.folders import FolderForm, Folders

    if not isinstance(user_id, str) or not user_id or len(user_id) > 128:
        raise ValueError("identité Open WebUI absente")
    folder_list = await Folders.get_folders_by_user_id(user_id)
    roots = [f for f in folder_list if _managed(f, "root")]
    if len(roots) > 1:
        raise ValueError("plusieurs racines ClawFedora : intervention manuelle requise")
    root = roots[0] if roots else None
    if root and root.parent_id is not None:
        raise ValueError("dossier racine ClawFedora déplacé : contrôle manuel requis")
    created = 0
    if root is None:
        if any(
            f.parent_id is None and f.name.casefold() == FOLDER_ROOT_NAME.casefold()
            for f in folder_list
        ):
            raise ValueError("nom du dossier racine déjà utilisé par un dossier personnel")
        root = await Folders.insert_new_folder(
            user_id,
            FolderForm(
                name=FOLDER_ROOT_NAME,
                meta={FOLDER_SCHEMA_KEY: 1, FOLDER_KIND_KEY: "root"},
            ),
        )
        if root is None:
            raise ValueError("impossible de créer le dossier de projets dans Open WebUI")
        created += 1
        folder_list.append(root)
        # Display the newly created project entries in the native sidebar.
        expanded = await Folders.update_folder_is_expanded_by_id_and_user_id(
            root.id, user_id, True,
        )
        if expanded is None:
            raise ValueError("impossible de développer la nouvelle racine de projets")

    mapping: dict[str, str] = {}
    for row in rows:
        project_id = row["id"]
        matches = [
            f for f in folder_list if _managed(f, "project", project_id)
        ]
        if len(matches) > 1:
            raise ValueError("dossier ClawFedora dupliqué : contrôle manuel requis")
        folder = matches[0] if matches else None
        if folder is not None and folder.parent_id != root.id:
            raise ValueError("dossier projet déplacé : contrôle manuel requis")
        if folder is None:
            name = row["title"] + " · " + project_id
            if any(f.parent_id == root.id and f.name.casefold() == name.casefold()
                   for f in folder_list):
                raise ValueError("collision avec un dossier existant")
            folder = await Folders.insert_new_folder(
                user_id,
                FolderForm(
                    name=name,
                    meta={
                        FOLDER_SCHEMA_KEY: 1,
                        FOLDER_KIND_KEY: "project",
                        FOLDER_PROJECT_KEY: project_id,
                    },
                    parent_id=root.id,
                ),
                root.id,
            )
            if folder is None:
                raise ValueError("impossible de créer le dossier d'un projet Open WebUI")
            created += 1
            folder_list.append(folder)
        mapping[project_id] = folder.id
    return root.id, mapping, created


async def _chat_to_project_folder(
    user_id: str, chat_id: str, folder_id: str,
) -> str:
    """Move only a saved conversation owned by the active Open WebUI user."""
    from open_webui.models.chats import Chats

    if (
        not isinstance(chat_id, str) or not 8 <= len(chat_id) <= 128
        or re.fullmatch(r"[a-zA-Z0-9-]+", chat_id) is None
    ):
        raise ValueError("conversation enregistrée introuvable : envoyer un premier message")
    chat = await Chats.get_chat_by_id_and_user_id(chat_id, user_id)
    if chat is None:
        raise ValueError("conversation absente ou appartenant à un autre compte")
    if chat.folder_id == folder_id:
        return "déjà classée"
    moved = await Chats.update_chat_folder_id_by_id_and_user_id(
        chat_id, user_id, folder_id,
    )
    if moved is None or moved.folder_id != folder_id:
        raise ValueError("déplacement de conversation non confirmé")
    return "classée"


class Action:
    actions = [
        {"id": "choose", "name": "Choisir un projet"},
        {"id": "folder_sync", "name": "Afficher les projets dans le menu"},
        {"id": "folder_link", "name": "Classer cette conversation"},
        {"id": "status", "name": "Projet et prochaine étape"},
        {"id": "activity", "name": "Activité de l’atelier"},
        {"id": "create", "name": "Créer un projet"},
        {"id": "project_actions", "name": "Actions du projet"},
        {"id": "resources", "name": "Sources, modèles et aide"},
    ]

    async def action(
        self,
        body: dict[str, Any],
        __id__: str | None = None,
        __user__: dict[str, Any] | None = None,
        __event_emitter__: Any = None,
        __event_call__: Any = None,
        **_: Any,
    ) -> dict[str, Any] | None:
        if (__user__ or {}).get("role") != "admin":
            raise ValueError("action interdite")
        secret = os.environ.get("OPENAI_API_KEY", "")
        history = body.get("messages")
        if __id__ in {"folder_sync", "folder_link"}:
            if __event_call__ is None:
                raise ValueError("confirmation navigateur indisponible")
            user_id = (__user__ or {}).get("id")
            if not isinstance(user_id, str) or not user_id:
                raise ValueError("compte utilisateur Open WebUI absent")
            view = await asyncio.to_thread(atelier_view, secret)
            rows = _folder_project_rows(view)
            if not rows:
                if __event_emitter__ is not None:
                    await __event_emitter__({"type": "notification", "data": {
                        "type": "info", "content": "Aucun projet à afficher : créez-en un d'abord.",
                    }})
                return None
            if __id__ == "folder_sync":
                confirmed = await __event_call__({
                    "type": "confirmation", "data": {
                        "title": "Mes projets dans Open WebUI",
                        "message": (
                            f"Créer les dossiers natifs pour {len(rows)} projet(s) "
                            "sous « Projets ClawFedora » ? Les conversations existantes "
                            "ne seront ni déplacées, ni copiées, ni effacées."
                        ),
                    },
                })
                if confirmed is not True:
                    return None
                _root, mapping, created = await _native_folders_for_projects(user_id, rows)
                message = (
                    f"{len(mapping)} projet(s) disponibles dans la section Dossiers "
                    f"Open WebUI ({created} nouveau(x) dossier(s)). "
                    "Actualisez la barre latérale si nécessaire. Pour lier une "
                    "conversation à son projet, utilisez « Classer cette conversation »."
                )
                if __event_emitter__ is not None:
                    await __event_emitter__({"type": "notification", "data": {
                        "type": "info", "content": message,
                    }})
                return None

            # Only the saved current chat can be moved; no bulk chat migration.
            chat_id = body.get("chat_id")
            if (
                type(chat_id) is not str or not 8 <= len(chat_id) <= 128
                or re.fullmatch(r"[a-zA-Z0-9-]+", chat_id) is None
            ):
                raise ValueError(
                    "conversation non enregistrée : envoyer un message et réessayer"
                )
            # Read and check owner before any folder mutation.
            from open_webui.models.chats import Chats
            owner_chat = await Chats.get_chat_by_id_and_user_id(chat_id, user_id)
            if owner_chat is None:
                raise ValueError("conversation absente ou non autorisée")
            choices = {row["id"]: f"{row['title']} ({row['id']})" for row in rows}
            chosen = await _choose(
                __event_call__, "Classer la conversation",
                "Sélectionnez le projet ClawFedora auquel associer ce fil.",
                choices,
            )
            if chosen is None:
                return None
            refreshed = await asyncio.to_thread(atelier_view, secret, chosen)
            if (refreshed.get("selected") or {}).get("id") != chosen:
                raise ValueError("le projet n'est plus disponible")
            # Verify the assistant message can preserve the chosen marker
            # before moving anything in Open WebUI.
            result = _selection(body, chosen)
            confirmed = await __event_call__({
                "type": "confirmation", "data": {
                    "title": "Classer ce fil dans « " + chosen + " »",
                    "message": (
                        "Déplacer uniquement CETTE conversation dans le dossier "
                        "Open WebUI du projet et sélectionner ce projet dans son fil ? "
                        "Un éventuel ancien classement sera remplacé. Aucun "
                        "historique terminal n'est importé."
                    ),
                },
            })
            if confirmed is not True:
                return None
            _root, mapping, _created = await _native_folders_for_projects(
                user_id, [row for row in rows if row["id"] == chosen],
            )
            outcome = await _chat_to_project_folder(user_id, chat_id, mapping[chosen])
            if __event_emitter__ is not None:
                await __event_emitter__({"type": "notification", "data": {
                    "type": "info",
                    "content": (
                        f"Conversation {outcome} dans « {chosen} ». "
                        "Le dossier contient l'historique WebUI de ce fil ; "
                        "les sessions terminal OpenClaw restent séparées."
                    ),
                }})
            return result
        if __id__ == "choose":
            view = await asyncio.to_thread(atelier_view, secret)
            choices = {
                str(row["id"]): f"{row['title']} · {row['state']} ({row['id']})"
                for row in view["projects"]
                if isinstance(row, dict) and isinstance(row.get("id"), str)
                and re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}[a-z0-9]", row["id"])
            }
            if not choices:
                if __event_emitter__ is not None:
                    await __event_emitter__({"type": "notification", "data": {
                        "type": "info", "content": "Aucun projet. Utilisez Créer un projet.",
                    }})
                return None
            chosen = await _choose(
                __event_call__, "Choisir le projet de cette conversation",
                "Choisissez un projet. Ses fichiers restent inchangés. "
                "Utilisez le bouton sous la dernière réponse pour les prochains échanges.", choices,
            )
            if chosen is None:
                return None
            refreshed = await asyncio.to_thread(atelier_view, secret, chosen)
            if (refreshed.get("selected") or {}).get("id") != chosen:
                raise ValueError("Ce projet n’est plus disponible. Actualisez la liste.")
            # Native Open WebUI action responses persist the updated answer. A notification
            # alone would show the selection without preserving it in the conversation.
            result = _selection(body, chosen)
            if __event_emitter__ is not None:
                await __event_emitter__({"type": "notification", "data": {
                    "type": "info", "content": "Projet sélectionné : " + chosen +
                    ". Consultez Projet et prochaine étape pour continuer.",
                }})
            return result
        if __id__ == "activity":
            view = await asyncio.to_thread(atelier_view, secret)
            state = view["activity"]
            output = str(state["label"])
            if state.get("elapsed_label"):
                output += " · depuis " + str(state["elapsed_label"])
            if state.get("project_id"):
                output += " · projet " + str(state["project_id"])
            output += "\n" + str(state["hint"])
            if __event_emitter__ is not None:
                await __event_emitter__({"type": "notification", "data": {
                    "type": "info", "content": output,
                }})
            return None
        if __id__ == "project_actions":
            current = _project_id(history)
            if current is None:
                raise ValueError("Utilisez Choisir un projet, puis ouvrez Actions du projet.")
            view = await asyncio.to_thread(atelier_view, secret, current)
            selected = view.get("selected") or {}
            __id__ = await _choose(
                __event_call__, "Actions du projet « " + current + " »",
                str(selected.get("next_step", "Consultez l’état du projet avant de continuer.")),
                PROJECT_MENU,
            )
            if __id__ is None:
                return None
        elif __id__ == "resources":
            __id__ = await _choose(
                __event_call__, "Sources, modèles et aide",
                "Ces consultations ne lancent aucune génération ni appel cloud.", RESOURCE_MENU,
            )
            if __id__ is None:
                return None
        if __id__ in READ_ONLY_ACTIONS:
            output = await asyncio.to_thread(
                read_only_bridge, READ_ONLY_ACTIONS[__id__], history, key=secret
            )
        elif __id__ == "create":
            if __event_call__ is None:
                raise ValueError("formulaire navigateur indisponible")
            title = await __event_call__({
                "type": "input", "data": {
                    "title": "Nouveau projet", "message": "Titre du projet (193 caractères max)",
                    "placeholder": "Exemple : Infrastructure Terraform",
                },
            })
            if type(title) is not str or not title.strip():
                return None
            brief = await __event_call__({
                "type": "input", "data": {
                    "title": "Objectif du projet",
                    "message": "Décris le besoin, les livrables et les contraintes.",
                    "placeholder": "Objectif, contexte et résultat attendu…",
                },
            })
            if type(brief) is not str or not brief.strip():
                return None
            title, brief = title.strip(), brief.strip()
            if (
                len(title) > 193 or any(c in title for c in ("\n", "\r", "\x00"))
                or len(brief.encode("utf-8")) > 12_000 or "\x00" in brief
            ):
                raise ValueError("titre ou demande de projet trop long ou invalide")
            confirmed = await __event_call__({
                "type": "confirmation", "data": {
                    "title": "Préparer un nouveau projet",
                    "message": (
                        f"Préparer « {title} » à partir de {len(brief.encode('utf-8'))} "
                        "octets ? Une confirmation distincte sera demandée "
                        "pour créer réellement le projet."
                    ),
                },
            })
            if confirmed is not True:
                return None
            output = await asyncio.to_thread(
                local_bridge, "!creer " + title, history,
                key=secret, mutation=True, creation_brief=brief,
            )
        elif __id__ == "answer":
            if __event_call__ is None:
                raise ValueError("formulaire navigateur indisponible")
            if _project_marker(history) is None:
                raise ValueError("sélectionner d'abord un projet")
            number_raw = await __event_call__({
                "type": "input", "data": {
                    "title": "Question de cadrage",
                    "message": "Numéro affiché par !questions (entre 1 et 30)",
                    "placeholder": "1",
                },
            })
            if type(number_raw) is not str or not number_raw.strip():
                return None
            number_raw = number_raw.strip()
            if not number_raw.isdecimal() or not 1 <= int(number_raw) <= 30:
                raise ValueError("numéro de question invalide")
            number = int(number_raw)
            answer_raw = await __event_call__({
                "type": "input", "data": {
                    "title": f"Réponse à la question {number}",
                    "message": "Votre réponse de cadrage (maximum 1 500 caractères)",
                    "placeholder": "Votre réponse…",
                },
            })
            if type(answer_raw) is not str or not answer_raw.strip():
                return None
            if len(answer_raw) > 1500 or "\x00" in answer_raw:
                raise ValueError("réponse de cadrage invalide")
            confirmed = await __event_call__({
                "type": "confirmation", "data": {
                    "title": "Enregistrer la réponse",
                    "message": (
                        f"Enregistrer votre réponse à la question {number} "
                        "du projet sélectionné ?"
                    ),
                },
            })
            if confirmed is not True:
                return None
            output = await asyncio.to_thread(
                local_bridge, "!repondre", history, key=secret,
                mutation=True, clarification=(number, answer_raw),
            )
        elif __id__ == "revise":
            if __event_call__ is None:
                raise ValueError("formulaire navigateur indisponible")
            if _project_marker(history) is None:
                raise ValueError("sélectionner d'abord un projet")
            task_raw = await __event_call__({
                "type": "input", "data": {
                    "title": "Réviser une tâche",
                    "message": "Identifiant de la tâche figurant dans !etat",
                    "placeholder": "tache-001",
                },
            })
            if type(task_raw) is not str or not task_raw.strip():
                return None
            task_id = task_raw.strip().lower()
            if re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}[a-z0-9]", task_id) is None:
                raise ValueError("identifiant de tâche invalide")
            reason_raw = await __event_call__({
                "type": "input", "data": {
                    "title": f"Motif de révision : {task_id}",
                    "message": "Pourquoi reprendre cette tâche ? (maximum 2 000 caractères)",
                    "placeholder": "Décrire précisément le changement attendu…",
                },
            })
            if type(reason_raw) is not str or not reason_raw.strip():
                return None
            if len(" ".join(reason_raw.split())) > 2000 or "\x00" in reason_raw:
                raise ValueError("motif de révision invalide")
            confirmed = await __event_call__({
                "type": "confirmation", "data": {
                    "title": "Préparer la révision",
                    "message": (
                        f"Préparer la révision de {task_id} ? Le pont calculera les "
                        "tâches affectées et exigera ensuite une phrase d'approbation "
                        "indépendante avant toute modification."
                    ),
                },
            })
            if confirmed is not True:
                return None
            output = await asyncio.to_thread(
                local_bridge, "!modifier", history, key=secret,
                mutation=True, revision=(task_id, reason_raw),
            )
        elif __id__ in PROJECT_ACTIONS:
            # Only a positive response from the actual browser counts, not an
            # LLM claim, a missing callback or a dict containing an error.
            if __event_call__ is None:
                raise ValueError("confirmation navigateur indisponible")
            command, warning = PROJECT_ACTIONS[__id__]
            if _project_marker(history) is None:
                raise ValueError("projet non sélectionné")
            confirmed = await __event_call__(
                {"type": "confirmation", "data": {
                    "title": "Projet « " + str(_project_id(history)) + " »", "message": warning,
                }}
            )
            if confirmed is not True:
                return None
            output = await asyncio.to_thread(
                local_bridge, command, history, key=secret, mutation=True
            )
        else:
            raise ValueError("action interdite")
        if __event_emitter__ is not None:
            await __event_emitter__(
                {"type": "notification", "data": {"type": "info", "content": output}}
            )
        return None
