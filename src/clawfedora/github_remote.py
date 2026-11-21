"""Opt-in GitHub repository creation and branch-policy governance.

Plans are offline. Writes require explicit target, manifest SHA-256 and local
GITHUB_TOKEN. A new personal repository is created private by default.
Settings are inspected without assuming plan features or admin permissions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, cast

from clawfedora.github_pr import NoRedirect, PublicationError, _valid_repo

API = "https://api.github.com"
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{1,79}\Z")
BRANCH = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}\Z")
MAX_REPLY = 1_000_000
RULESET = "Atelier - PR obligatoires sur la branche principale"


class GitHubRemoteError(ValueError):
    """GitHub operation refused or incomplete without exposing a token or response body."""

    def __init__(self, message: str, *, status: int = 0):
        super().__init__(message)
        self.status = status


def _request(
    path: str, *, method: str, token: str, data: dict[str, Any] | None = None,
) -> object:
    if not (
        path == "/user" or path == "/user/repos" or
        path.startswith("/repos/")
    ) or "//" in path or "?" in path:
        raise GitHubRemoteError("endpoint GitHub hors périmètre")
    if method not in ("GET", "POST", "PUT"):
        raise GitHubRemoteError("méthode GitHub interdite")
    if method == "POST" and path not in ("/user/repos",) and not path.endswith("/rulesets"):
        raise GitHubRemoteError("écriture GitHub non autorisée")
    if method == "PUT" and not path.endswith("/actions/permissions/workflow"):
        raise GitHubRemoteError("modification de permissions hors périmètre")
    if method == "GET" and path == "/user/repos":
        raise GitHubRemoteError("lecture du catalogue de dépôts interdite")
    body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data else None
    request = urllib.request.Request(
        API + path, data=body, method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "Authorization": "Bearer " + token,
            "X-GitHub-Api-Version": "2026-03-10",
            "User-Agent": "clawfedora-github-governance",
        },
    )
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(request, timeout=20) as response:
            raw = response.read(MAX_REPLY + 1)
    except urllib.error.HTTPError as exc:
        raise GitHubRemoteError(
            f"GitHub a refusé la demande : HTTP {exc.code}", status=exc.code,
        ) from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise GitHubRemoteError(
            "GitHub indisponible ; vérifier l'état distant avant de recommencer",
        ) from exc
    if len(raw) > MAX_REPLY:
        raise GitHubRemoteError("réponse GitHub trop volumineuse")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise GitHubRemoteError("réponse GitHub invalide") from exc


def _object(value: object, description: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GitHubRemoteError(f"objet GitHub invalide pour {description}")
    return cast(dict[str, Any], value)


def _token() -> str:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise GitHubRemoteError("GITHUB_TOKEN local requis pour une requête distante")
    return token


def _manifest(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def create_plan(
    name: str, description: str = "", *, visibility: str = "private",
) -> dict[str, Any]:
    if NAME.fullmatch(name) is None or name in (".", "..") or ".." in name:
        raise GitHubRemoteError("nom de dépôt GitHub invalide")
    if not isinstance(description, str) or len(description) > 200 or "\n" in description:
        raise GitHubRemoteError("description de dépôt invalide")
    if visibility not in ("private", "public"):
        raise GitHubRemoteError("visibilité private ou public requise")
    values = {
        "name": name, "description": description,
        "private": visibility == "private", "auto_init": True,
        "has_wiki": False, "has_issues": True, "is_template": False,
    }
    return {
        "mode": "OFFLINE_REPOSITORY_PLAN",
        "name": name, "visibility": visibility,
        "payload": values,
        "manifest_sha256": _manifest(values),
        "remote_created": False,
        "warning": (
            "Aucune requête réseau en aperçu. Un dépôt public exige une "
            "confirmation supplémentaire et expose immédiatement le README initial."
        ),
    }


def create_repository(
    name: str, description: str = "", *, visibility: str = "private",
    approve_name: str, approve_manifest: str, approve_public: bool = False,
) -> dict[str, Any]:
    plan = create_plan(name, description, visibility=visibility)
    if approve_name != name or approve_manifest != plan["manifest_sha256"]:
        raise GitHubRemoteError("approbation du dépôt ou de son plan absente")
    if visibility == "public" and not approve_public:
        raise GitHubRemoteError("dépôt public : accord spécifique requis")
    token = _token()
    user = _object(_request("/user", method="GET", token=token), "compte")
    login = user.get("login")
    if not isinstance(login, str) or NAME.fullmatch(login) is None:
        raise GitHubRemoteError("identité GitHub du propriétaire non confirmée")
    created = _object(
        _request("/user/repos", method="POST", token=token, data=plan["payload"]),
        "nouveau dépôt",
    )
    expected = login + "/" + name
    if (
        created.get("full_name") != expected or
        created.get("private") is not (visibility == "private")
    ):
        raise GitHubRemoteError(
            "dépôt potentiellement créé avec paramètres inattendus : vérifier sur GitHub",
        )
    url = created.get("html_url")
    if not isinstance(url, str) or url != "https://github.com/" + expected:
        raise GitHubRemoteError("dépôt potentiellement créé : URL à vérifier")
    return {
        "mode": "REPOSITORY_CREATED", "repository": expected,
        "visibility": visibility, "url": url,
        "default_branch": created.get("default_branch"),
        "next_step": (
            "Auditer les réglages, protéger la branche, puis proposer les "
            "fichiers du projet par PR brouillon ; aucune protection supposée active."
        ),
    }


def policy_payload(repo: str, branch: str, kind: str) -> dict[str, Any]:
    _valid_repo(repo)
    if BRANCH.fullmatch(branch) is None or ".." in branch:
        raise GitHubRemoteError("branche principale invalide")
    if kind == "workflow-readonly":
        return {
            "default_workflow_permissions": "read",
            "can_approve_pull_request_reviews": False,
        }
    if kind != "pr-ruleset":
        raise GitHubRemoteError("protection GitHub inconnue")
    return {
        "name": RULESET, "target": "branch", "enforcement": "active",
        "bypass_actors": [],
        "conditions": {"ref_name": {
            "include": ["refs/heads/" + branch], "exclude": [],
        }},
        "rules": [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
            {"type": "pull_request", "parameters": {
                "dismiss_stale_reviews_on_push": False,
                "require_code_owner_review": False,
                "require_last_push_approval": False,
                "required_approving_review_count": 0,
                "required_review_thread_resolution": True,
            }},
        ],
    }


def policy_plan(repo: str, branch: str = "main", kind: str = "pr-ruleset") -> dict[str, Any]:
    payload = policy_payload(repo, branch, kind)
    intent = {"repo": repo, "branch": branch, "kind": kind, "payload": payload}
    return {
        "mode": "OFFLINE_POLICY_PLAN", **intent,
        "manifest_sha256": _manifest(intent),
        "warning": (
            "La disponibilité et l'application effective des rulesets dépendent "
            "du plan GitHub, des permissions et des règles déjà configurées."
        ),
    }


def _repo_info(repo: str, token: str) -> dict[str, Any]:
    result = _object(_request("/repos/" + repo, method="GET", token=token), "dépôt")
    if result.get("full_name") != repo or result.get("archived") is True:
        raise GitHubRemoteError("dépôt cible absent, renommé ou archivé")
    return result


def settings_audit(repo: str) -> dict[str, Any]:
    _valid_repo(repo)
    token = _token()
    info = _repo_info(repo, token)
    result: dict[str, Any] = {
        "mode": "READ_ONLY_GITHUB_SETTINGS_AUDIT",
        "repository": repo, "visibility": "private" if info.get("private") else "public",
        "default_branch": info.get("default_branch"),
        "rulesets": {"state": "NOT_EVALUATED"},
        "workflow_permissions": {"state": "NOT_EVALUATED"},
        "limitations": [
            "Un ruleset listé n'est pas une preuve de son application effective",
            "L'absence d'autorisation API ne signifie pas que le contrôle est désactivé",
            "La recette graphique navigateur et les tests Fedora ne sont pas évalués",
        ],
    }
    prefix = "/repos/" + repo
    try:
        rules = _request(prefix + "/rulesets", method="GET", token=token)
        if isinstance(rules, list):
            result["rulesets"] = {
                "state": "LISTED_NOT_VALIDATED", "items": [
                    {
                        "name": item.get("name"),
                        "enforcement": item.get("enforcement"),
                    } for item in rules[:50] if isinstance(item, dict)
                ],
            }
    except GitHubRemoteError as exc:
        result["rulesets"] = {"state": "NOT_EVALUATED", "http_status": exc.status}
    try:
        workflow = _object(_request(
            prefix + "/actions/permissions/workflow", method="GET", token=token,
        ), "autorisations GitHub Actions")
        result["workflow_permissions"] = {
            "state": "OBSERVED",
            "default_workflow_permissions": workflow.get("default_workflow_permissions"),
            "can_approve_pull_request_reviews": workflow.get("can_approve_pull_request_reviews"),
        }
    except GitHubRemoteError as exc:
        result["workflow_permissions"] = {
            "state": "NOT_EVALUATED", "http_status": exc.status,
        }
    return result


def apply_policy(
    repo: str, branch: str, kind: str, *, approve_repo: str,
    approve_manifest: str,
) -> dict[str, Any]:
    plan = policy_plan(repo, branch, kind)
    if approve_repo != repo or approve_manifest != plan["manifest_sha256"]:
        raise GitHubRemoteError("dépôt ou empreinte du plan non approuvé")
    token = _token()
    info = _repo_info(repo, token)
    if info.get("default_branch") != branch:
        raise GitHubRemoteError("branche principale changée : revoir le plan")
    prefix = "/repos/" + repo
    if kind == "pr-ruleset":
        current = _request(prefix + "/rulesets", method="GET", token=token)
        if not isinstance(current, list):
            raise GitHubRemoteError("règles existantes non évaluables : écriture refusée")
        if any(isinstance(item, dict) and item.get("name") == RULESET for item in current):
            raise GitHubRemoteError("ruleset Atelier déjà présent ; ne pas créer de doublon")
        created = _object(_request(
            prefix + "/rulesets", method="POST", token=token, data=plan["payload"],
        ), "ruleset")
        if created.get("name") != RULESET or created.get("enforcement") != "active":
            raise GitHubRemoteError("ruleset potentiellement créé : vérifier GitHub")
        return {
            "mode": "RULESET_CREATED_UNVERIFIED_ENFORCEMENT",
            "repository": repo, "ruleset_id": created.get("id"),
            "next_step": "Vérifier l'application effective dans Settings > Rules.",
        }
    _request(
        prefix + "/actions/permissions/workflow", method="PUT", token=token,
        data=plan["payload"],
    )
    checked = _object(_request(
        prefix + "/actions/permissions/workflow", method="GET", token=token,
    ), "permissions appliquées")
    if (
        checked.get("default_workflow_permissions") != "read" or
        checked.get("can_approve_pull_request_reviews") is not False
    ):
        raise GitHubRemoteError("permissions potentiellement changées : vérifier GitHub")
    return {"mode": "WORKFLOW_READONLY_VERIFIED", "repository": repo}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clawfedora-github-remote")
    commands = parser.add_subparsers(dest="action", required=True)
    create = commands.add_parser("create")
    create.add_argument("--name", required=True)
    create.add_argument("--description", default="")
    create.add_argument("--visibility", choices=("private", "public"), default="private")
    create.add_argument("--apply", action="store_true")
    create.add_argument("--approve-name", default="")
    create.add_argument("--approve-manifest", default="")
    create.add_argument("--approve-public", action="store_true")
    audit = commands.add_parser("audit")
    audit.add_argument("--repo", required=True)
    policy = commands.add_parser("policy")
    policy.add_argument("--repo", required=True)
    policy.add_argument("--branch", default="main")
    policy.add_argument("--kind", choices=("pr-ruleset", "workflow-readonly"),
                        default="pr-ruleset")
    policy.add_argument("--apply", action="store_true")
    policy.add_argument("--approve-repo", default="")
    policy.add_argument("--approve-manifest", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.action == "create":
            value = (
                create_repository(
                    args.name, args.description, visibility=args.visibility,
                    approve_name=args.approve_name,
                    approve_manifest=args.approve_manifest,
                    approve_public=args.approve_public,
                ) if args.apply else create_plan(
                    args.name, args.description, visibility=args.visibility,
                )
            )
        elif args.action == "audit":
            value = settings_audit(args.repo)
        else:
            value = (
                apply_policy(
                    args.repo, args.branch, args.kind,
                    approve_repo=args.approve_repo,
                    approve_manifest=args.approve_manifest,
                ) if args.apply else policy_plan(args.repo, args.branch, args.kind)
            )
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return 0
    except (GitHubRemoteError, PublicationError, OSError, ValueError) as exc:
        print(json.dumps({
            "mode": "REFUSED_OR_INCOMPLETE", "error": str(exc),
            "next_step": "Contrôler la situation réelle dans GitHub avant de retenter.",
        }, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
