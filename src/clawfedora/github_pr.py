"""Explicitly approved GitHub draft PR publication from a local reviewed staging directory.

Default: entirely offline and read-only. Remote mutation requires all of:
--apply, exact repository approval and matching expected base SHA.
Never updates an existing branch, merges or publishes a normal PR.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any, cast

API = "https://api.github.com"
REPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")
BRANCH = re.compile(r"atelier/[a-z0-9][a-z0-9._-]{2,60}\Z")
MAX_FILES = 60
MAX_FILE_BYTES = 300_000
MAX_TOTAL_BYTES = 2_000_000
MAX_RESPONSE_BYTES = 1_000_000
BLOCKED_PARTS = frozenset({
    ".git", ".terraform", "node_modules", ".venv", "__pycache__", "secrets",
    "backups", "private", ".ssh", ".source-provenance.json",
})
BLOCKED_SUFFIXES = (".key", ".pem", ".p12", ".pfx", ".tfstate", ".tfvars", ".dump", ".db")
SUSPECT_CONTENT = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?:ghp_|github_pat_|gho_|ghu_)[A-Za-z0-9_]{24,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
)


class PublicationError(ValueError):
    """Explicit refusal without echoing the authentication token or payload."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: urllib.request.Request, fp: Any, code: int,
        msg: str, headers: Any, newurl: str,
    ) -> None:
        raise PublicationError("redirection API refusée")


def _valid_repo(value: str) -> str:
    if REPO.fullmatch(value) is None or ".." in value:
        raise PublicationError("identifiant du dépôt invalide")
    return value


def _valid_sha(value: str) -> str:
    if SHA.fullmatch(value) is None:
        raise PublicationError("SHA Git complet de 40 caractères requis")
    return value


def _valid_branch(value: str) -> str:
    if BRANCH.fullmatch(value) is None or ".." in value or value.endswith(".lock"):
        raise PublicationError("branche de proposition invalide (atelier/slug attendu)")
    return value


def _safe_relative(relative: PurePosixPath, *, allow_workflows: bool) -> None:
    pieces = relative.parts
    if relative.is_absolute() or not pieces or "." in pieces or ".." in pieces:
        raise PublicationError("chemin de fichier dangereux")
    if any(part.casefold() in BLOCKED_PARTS for part in pieces):
        raise PublicationError("dossier protégé ou confidentiel interdit")
    filename = pieces[-1].casefold()
    if filename == ".env" or filename.startswith(".env.") or filename.startswith("id_rsa"):
        raise PublicationError("fichier potentiellement secret interdit")
    if filename.startswith("id_ed25519") or filename.endswith(BLOCKED_SUFFIXES):
        raise PublicationError("fichier sensible ou binaire interdit")
    if filename in (".source-provenance.json", ".ds_store") or filename.endswith(".tfplan"):
        raise PublicationError("manifest ou plan sensible interdit")
    if pieces[:2] == (".github", "workflows") and not allow_workflows:
        raise PublicationError("workflow GitHub Actions : --allow-workflows requis")


def collect_files(
    root: Path, *, allow_workflows: bool = False,
) -> list[tuple[str, bytes]]:
    if root.is_symlink() or not root.is_dir():
        raise PublicationError("dossier de préparation non valide")
    root = root.resolve(strict=True)
    if (root / ".source-provenance.json").exists():
        raise PublicationError("un snapshot importé ne peut pas être publié directement")
    found: list[tuple[str, bytes]] = []
    total_bytes = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise PublicationError("lien symbolique refusé dans la proposition")
        if path.is_dir():
            continue
        if not path.is_file():
            raise PublicationError("entrée non régulière refusée")
        relative = PurePosixPath(path.relative_to(root).as_posix())
        _safe_relative(relative, allow_workflows=allow_workflows)
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            raise PublicationError("fichier trop volumineux")
        total_bytes += size
        if total_bytes > MAX_TOTAL_BYTES:
            raise PublicationError("proposition trop volumineuse")
        content = path.read_bytes()
        if b"\x00" in content:
            raise PublicationError("fichier binaire refusé")
        try:
            decoded = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PublicationError("fichier non UTF-8 refusé") from exc
        if any(pattern.search(decoded) for pattern in SUSPECT_CONTENT):
            raise PublicationError("contenu sensible détecté, publication refusée")
        found.append((relative.as_posix(), content))
        if len(found) > MAX_FILES:
            raise PublicationError("trop de fichiers dans la proposition")
    if not found:
        raise PublicationError("aucun fichier à proposer")
    return found


def make_plan(
    *, repo: str, base: str, base_sha: str, branch: str,
    changes: Path, allow_workflows: bool,
) -> dict[str, Any]:
    _valid_repo(repo)
    _valid_sha(base_sha)
    _valid_branch(branch)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", base):
        raise PublicationError("branche de base invalide")
    files = collect_files(changes, allow_workflows=allow_workflows)
    manifest = {
        "repository": repo, "base": base, "base_sha": base_sha,
        "branch": branch, "files": [
            [name, hashlib.sha256(content).hexdigest()]
            for name, content in files
        ],
    }
    manifest_sha256 = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "manifest_sha256": manifest_sha256,
        "mode": "OFFLINE_DRY_RUN",
        "repository": repo,
        "base": base,
        "expected_base_sha": base_sha,
        "proposal_branch": branch,
        "draft_only": True,
        "files": [
            {
                "path": name, "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
            for name, content in files
        ],
        "warning": (
            "Aucun accès distant en mode aperçu. Examinez tous les fichiers locaux "
            "avant d'autoriser la création d'une branche et d'une PR brouillon."
        ),
    }


def _api_request(
    path: str, *, method: str, token: str, payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not path.startswith("/repos/") or "//" in path or "?" in path:
        raise PublicationError("API GitHub hors périmètre")
    if method not in ("GET", "POST"):
        raise PublicationError("méthode API interdite")
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload else None
    request = urllib.request.Request(
        API + path, method=method, data=encoded,
        headers={
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "Authorization": "Bearer " + token,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "clawfedora-github-draft-publisher",
        },
    )
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(request, timeout=20) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise PublicationError(f"GitHub a refusé l'action HTTP {exc.code}") from None
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise PublicationError("GitHub indisponible : état distant à vérifier") from exc
    if len(body) > MAX_RESPONSE_BYTES:
        raise PublicationError("réponse GitHub trop volumineuse")
    try:
        parsed: object = json.loads(body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise PublicationError("réponse GitHub invalide") from exc
    if not isinstance(parsed, dict):
        raise PublicationError("objet GitHub inattendu")
    return cast(dict[str, Any], parsed)


def _expected_sha(record: dict[str, Any], label: str) -> str:
    value = record.get("sha")
    if not isinstance(value, str) or SHA.fullmatch(value) is None:
        raise PublicationError(f"SHA de {label} manquant ou invalide")
    return value


def publish_draft(
    *, repo: str, base: str, base_sha: str, branch: str, changes: Path,
    title: str, body: str, approve_repo: str, approve_manifest: str = "",
    allow_workflows: bool = False,
) -> dict[str, Any]:
    """Only explicit caller-driven publication. Never merges or updates main."""
    plan = make_plan(
        repo=repo, base=base, base_sha=base_sha, branch=branch, changes=changes,
        allow_workflows=allow_workflows,
    )
    if approve_repo != repo:
        raise PublicationError("l'approbation explicite du dépôt ne correspond pas")
    if approve_manifest != plan["manifest_sha256"]:
        raise PublicationError("empreinte du plan non approuvée ou devenue obsolète")
    if not 8 <= len(title.strip()) <= 180 or not 8 <= len(body.strip()) <= 60000:
        raise PublicationError("titre ou description de PR insuffisant")
    if any(pattern.search(title + "\n" + body) for pattern in SUSPECT_CONTENT):
        raise PublicationError("contenu sensible dans la description de PR")
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise PublicationError("GITHUB_TOKEN requis uniquement pour publication")
    prefix = "/repos/" + urllib.parse.quote(repo, safe="/")
    # No mutation until all validations and exact remote head comparison pass.
    meta = _api_request(prefix, method="GET", token=token)
    if meta.get("default_branch") != base or meta.get("archived") is True:
        raise PublicationError("base différente de la branche principale ou dépôt archivé")
    ref = _api_request(
        prefix + "/git/ref/heads/" + urllib.parse.quote(base, safe=""),
        method="GET", token=token,
    )
    remote_object = ref.get("object")
    if not isinstance(remote_object, dict) or remote_object.get("sha") != base_sha:
        raise PublicationError("branche principale modifiée : nouveau SHA requis")
    commit = _api_request(
        prefix + "/git/commits/" + base_sha, method="GET", token=token,
    )
    initial_tree = commit.get("tree")
    if not isinstance(initial_tree, dict):
        raise PublicationError("arbre Git de base introuvable")
    tree_sha = _expected_sha(initial_tree, "l'arbre de base")
    # Re-read and compare hashes: cannot silently publish changed local material.
    files = collect_files(changes, allow_workflows=allow_workflows)
    actual = [(name, hashlib.sha256(content).hexdigest()) for name, content in files]
    planned = [(entry["path"], entry["sha256"]) for entry in plan["files"]]
    if actual != planned:
        raise PublicationError("les fichiers ont changé après prévisualisation")
    tree_entries: list[dict[str, str]] = []
    for name, contents in files:
        record = _api_request(
            prefix + "/git/blobs", method="POST", token=token,
            payload={"content": contents.decode("utf-8"), "encoding": "utf-8"},
        )
        tree_entries.append({
            "path": name, "mode": "100644", "type": "blob",
            "sha": _expected_sha(record, "blob GitHub"),
        })
    new_tree = _api_request(
        prefix + "/git/trees", method="POST", token=token,
        payload={"base_tree": tree_sha, "tree": tree_entries},
    )
    new_commit = _api_request(
        prefix + "/git/commits", method="POST", token=token,
        payload={
            "message": "docs: proposition contrôlée par atelier OpenClaw",
            "tree": _expected_sha(new_tree, "arbre créé"), "parents": [base_sha],
        },
    )
    created_sha = _expected_sha(new_commit, "commit créé")
    _api_request(
        prefix + "/git/refs", method="POST", token=token,
        payload={"ref": "refs/heads/" + branch, "sha": created_sha},
    )
    # Failure here may leave a branch; NEVER auto-delete or force-update it.
    pr = _api_request(
        prefix + "/pulls", method="POST", token=token,
        payload={
            "title": title.strip(), "body": body.strip(), "head": branch,
            "base": base, "draft": True, "maintainer_can_modify": False,
        },
    )
    url = pr.get("html_url")
    if not isinstance(url, str) or not url.startswith(
        "https://github.com/" + repo + "/pull/"
    ):
        raise PublicationError("PR potentiellement créée : vérifier l'état dans GitHub")
    if pr.get("draft") is not True:
        raise PublicationError("GitHub n'a pas confirmé le statut brouillon")
    return {
        "mode": "DRAFT_PR_CREATED",
        "repository": repo,
        "branch": branch,
        "commit_sha": created_sha,
        "url": url,
        "draft": True,
        "files_count": len(files),
        "next_step": "Relire le diff et la CI sur GitHub ; revue humaine avant fusion.",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clawfedora-github-pr",
        description="Prévisualisation locale puis PR brouillon GitHub sur approbation explicite",
    )
    parser.add_argument("--repo", required=True)
    parser.add_argument("--base", default="main")
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--changes", required=True, type=Path)
    parser.add_argument("--allow-workflows", action="store_true")
    parser.add_argument("--title", default="")
    parser.add_argument("--body-file", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--approve-repo", default="")
    parser.add_argument("--approve-manifest", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        plan = make_plan(
            repo=args.repo, base=args.base, base_sha=args.base_sha,
            branch=args.branch, changes=args.changes,
            allow_workflows=args.allow_workflows,
        )
        if not args.apply:
            print(json.dumps(plan, ensure_ascii=False, indent=2))
            return 0
        if args.body_file is None or args.body_file.is_symlink():
            raise PublicationError("description de PR requise dans un fichier régulier")
        if not args.body_file.is_file() or args.body_file.stat().st_size > 60_000:
            raise PublicationError("description de PR absente ou trop volumineuse")
        body = args.body_file.read_text(encoding="utf-8")
        result = publish_draft(
            repo=args.repo, base=args.base, base_sha=args.base_sha,
            branch=args.branch, changes=args.changes, title=args.title,
            body=body, approve_repo=args.approve_repo,
            approve_manifest=args.approve_manifest,
            allow_workflows=args.allow_workflows,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (PublicationError, OSError, UnicodeError) as exc:
        print(json.dumps({
            "mode": "REFUSED_OR_INCOMPLETE",
            "error": str(exc),
            "advice": "Vérifier le dépôt distant et la branche avant tout nouvel essai.",
        }, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
