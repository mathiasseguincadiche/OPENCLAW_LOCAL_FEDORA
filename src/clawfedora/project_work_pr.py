"""Draft-only GitHub PRs for an *active* project milestone.

Preview is offline. Publication requires a human-supplied exact manifest, a
local token, a worker lock and single-use attempt tracking. Existing delivered
project PR rules stay unchanged. Nothing executes on host or remote VMs.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
from typing import Any

from clawfedora import github_pr, github_refresh, project_roadmap, source_connectors
from clawfedora.core_config import resolve_runtime_root
from clawfedora.project_common import (
    assert_no_symlinks,
    now,
    project_path,
    read_json,
    sha256_file,
    validate_task_id,
    write_json,
)
from clawfedora.project_intake import _validate_source, validate_input_integrity
from clawfedora.project_worker import worker_lock

ATTEMPTS = "context/github-work-pr"
MAX_FILES = 15
MAX_DIFF_LINES = 160


def _linked(project: Path, repo: str, base_sha: str) -> Path:
    """Use only the latest *verified local* GitHub snapshot as the PR base."""
    initial_dir, initial_sha = github_refresh._initial(project, repo)
    registry = github_refresh._read_registry(project, repo, initial_sha)
    revisions: list[dict[str, Any]] = registry["revisions"]
    current = str(revisions[-1]["commit"]) if revisions else initial_sha
    if current != base_sha:
        raise ValueError("SHA de base non conforme au dernier snapshot GitHub enregistré")
    if revisions:
        source, _hashes = github_refresh._snapshot(project, repo, current)
        return source
    return initial_dir


def _directory(project: Path, milestone_id: str) -> Path:
    return project / "work" / "github-pr" / validate_task_id(milestone_id)


def _attempt(project: Path, milestone_id: str, branch: str) -> Path:
    tag = hashlib.sha256(branch.encode("utf-8")).hexdigest()[:32]
    return project / ATTEMPTS / (validate_task_id(milestone_id) + "-" + tag + ".json")


def _paths(allowed: list[str]) -> list[str]:
    if not 1 <= len(allowed) <= MAX_FILES or len(set(allowed)) != len(allowed):
        raise ValueError("fichiers explicitement autorisés : 1 à 15 chemins distincts")
    for value in allowed:
        if not isinstance(value, str) or not value or "\\" in value:
            raise ValueError("chemin de proposition invalide")
        relative = PurePosixPath(value)
        if value != relative.as_posix() or relative.is_absolute():
            raise ValueError("chemin de proposition non canonique")
        github_pr._safe_relative(relative, allow_workflows=False)
    return sorted(allowed)


def _guard(project: Path, milestone_id: str) -> dict[str, Any]:
    manifest = read_json(project / "project.json")
    if manifest.get("status") not in {"IN_PROGRESS", "VALIDATING", "REVIEW"}:
        raise ValueError("le projet doit être en cours, en validation ou en revue")
    roadmap = project_roadmap.load(project)
    milestone = next(
        (item for item in roadmap["milestones"] if item["id"] == milestone_id), None
    )
    if milestone is None:
        raise ValueError("jalon absent de la feuille de route")
    if milestone["state"] not in {"IN_PROGRESS", "BLOCKED"}:
        raise ValueError("jalon non actif : IN_PROGRESS ou BLOCKED requis")
    return milestone


def _diff(original: Path, changes: list[tuple[str, bytes]]) -> tuple[list[dict[str, Any]], str]:
    report: list[dict[str, Any]] = []
    diff_lines: list[str] = []
    for name, content in changes:
        baseline = original / name
        if baseline.is_symlink():
            raise ValueError("fichier du snapshot initial lié interdit")
        if baseline.exists() and not baseline.is_file():
            raise ValueError("type de fichier de base invalide")
        if baseline.is_file():
            old = baseline.read_bytes()
            if b"\x00" in old or len(old) > github_pr.MAX_FILE_BYTES:
                raise ValueError("base non textuelle ou trop volumineuse")
            try:
                old_text = old.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError("base non UTF-8") from exc
            old_sha = hashlib.sha256(old).hexdigest()
        else:
            old_text, old_sha = "", ""
        new_text = content.decode("utf-8")
        if old_text == new_text:
            raise ValueError("proposition inchangée par rapport au snapshot : " + name)
        kind = "modified" if baseline.is_file() else "added"
        report.append({
            "path": name, "change": kind, "base_sha256": old_sha,
            "new_sha256": hashlib.sha256(content).hexdigest(),
        })
        fragment = difflib.unified_diff(
            old_text.splitlines(keepends=True), new_text.splitlines(keepends=True),
            fromfile="a/" + name if baseline.is_file() else "/dev/null",
            tofile="b/" + name,
        )
        for line in fragment:
            if len(diff_lines) >= MAX_DIFF_LINES:
                break
            diff_lines.append(line.rstrip("\r\n")[:500])
    text = "\n".join(diff_lines)
    if len(diff_lines) == MAX_DIFF_LINES:
        text += "\n[diff tronqué : consulter tous les fichiers locaux avant publication]"
    return report, text


def plan(
    runtime: Path, project_id: str, repo: str, base_sha: str, branch: str,
    milestone_id: str, allowed: list[str],
) -> dict[str, Any]:
    """Offline: compare explicitly selected staged files with the pinned snapshot."""
    repo = source_connectors._safe_repo(repo)
    base_sha = github_pr._valid_sha(base_sha)
    branch = github_pr._valid_branch(branch)
    milestone_id = validate_task_id(milestone_id)
    allowed_paths = _paths(allowed)
    project = project_path(runtime, project_id)
    assert_no_symlinks(project, label="projet")
    failures = validate_input_integrity(project)
    if failures:
        raise ValueError("sources initiales altérées: " + "; ".join(failures))
    milestone = _guard(project, milestone_id)
    original = _linked(project, repo, base_sha)
    stage = _directory(project, milestone_id)
    if not stage.is_dir() or stage.is_symlink():
        raise ValueError("dossier de proposition absent ou lié")
    _validate_source(stage, label="proposition GitHub")
    changes = github_pr.collect_files(stage, allow_workflows=False)
    if [name for name, _ in changes] != allowed_paths:
        raise ValueError("fichiers proposés différents des chemins explicitement autorisés")
    files, diff = _diff(original, changes)
    proposal = github_pr.make_plan(
        repo=repo, base="main", base_sha=base_sha, branch=branch,
        changes=stage, allow_workflows=False,
    )
    # Approval binds user choice, milestone revision, source revision and file bytes.
    identity = {
        "project_id": project_id, "repo": repo, "base_sha": base_sha,
        "branch": branch, "milestone_id": milestone_id,
        "milestone_updated_at": milestone["updated_at"],
        "allowed": allowed_paths, "files": files,
        "publisher_manifest": proposal["manifest_sha256"],
    }
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "mode": "OFFLINE_PREVIEW", "project_id": project_id, "repository": repo,
        "base_sha": base_sha, "branch": branch, "milestone_id": milestone_id,
        "files": files, "diff": diff, "approval_sha256": digest,
        "publisher_manifest": proposal["manifest_sha256"],
        "verification": "NOT_VERIFIED", "draft_only": True,
        "remote_writes": False,
    }


def publish(
    runtime: Path, project_id: str, repo: str, base_sha: str, branch: str,
    milestone_id: str, allowed: list[str], *,
    approve_repo: str, approve_sha256: str, title: str, body: str,
) -> dict[str, Any]:
    """One attempt only; no retry or rollback after ambiguous GitHub failures."""
    if approve_repo != repo or not approve_sha256:
        raise ValueError("approbation du dépôt et empreinte du plan requises")
    if not os.environ.get("GITHUB_TOKEN"):
        raise ValueError("GITHUB_TOKEN absent : aucune publication possible")
    with worker_lock(runtime):
        preview = plan(runtime, project_id, repo, base_sha, branch, milestone_id, allowed)
        if approve_sha256 != preview["approval_sha256"]:
            raise ValueError("plan modifié depuis l'approbation : refaire la prévisualisation")
        project = project_path(runtime, project_id)
        record = _attempt(project, milestone_id, branch)
        if record.exists() or record.is_symlink():
            raise ValueError("publication déjà tentée : vérifier GitHub avant toute autre action")
        if record.parent.is_symlink():
            raise ValueError("dossier d'historique lié interdit")
        # Explicitly reject pre-existing remote branches before any Git object write.
        endpoint = "/repos/" + repo + "/git/ref/heads/" + branch
        try:
            github_pr._api_request(
                endpoint, method="GET", token=os.environ["GITHUB_TOKEN"]
            )
        except github_pr.PublicationError as exc:
            if "HTTP 404" not in str(exc):
                raise
        else:
            raise ValueError("branche distante déjà présente : publication refusée")
        write_json(record, {
            "state": "ATTEMPTED", "project_id": project_id, "repository": repo,
            "milestone_id": milestone_id, "base_sha": base_sha, "branch": branch,
            "approval_sha256": approve_sha256, "at": now(),
            "verification": "NOT_VERIFIED",
        })
        record.chmod(0o600)
        result = github_pr.publish_draft(
            repo=repo, base="main", base_sha=base_sha, branch=branch,
            changes=_directory(project, milestone_id), title=title, body=body,
            approve_repo=repo, approve_manifest=preview["publisher_manifest"],
            allow_workflows=False,
        )
        write_json(record, {
            **read_json(record), "state": "CREATED", "url": result["url"],
            "published_at": now(),
        })
        return {**result, "milestone_id": milestone_id, "verification": "NOT_VERIFIED"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clawfedora-github-work-pr",
        description="Prévisualiser une modification de jalon et créer une PR brouillon approuvée",
    )
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--milestone-id", required=True)
    parser.add_argument("--file", action="append", required=True, dest="allowed")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--approve-repo", default="")
    parser.add_argument("--approve-sha256", default="")
    parser.add_argument("--title", default="")
    parser.add_argument("--body-file", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        runtime = resolve_runtime_root(str(args.runtime_root) if args.runtime_root else None)
        params = {
            "runtime": runtime, "project_id": args.project_id, "repo": args.repo,
            "base_sha": args.base_sha, "branch": args.branch,
            "milestone_id": args.milestone_id, "allowed": args.allowed,
        }
        if not args.apply:
            print(json.dumps(plan(**params), ensure_ascii=False, indent=2))
            return 0
        if args.body_file is None or args.body_file.is_symlink():
            raise ValueError("description de PR requise dans un fichier régulier")
        if not args.body_file.is_file() or args.body_file.stat().st_size > 60_000:
            raise ValueError("description de PR absente ou trop volumineuse")
        result = publish(
            **params, approve_repo=args.approve_repo,
            approve_sha256=args.approve_sha256,
            title=args.title, body=args.body_file.read_text(encoding="utf-8"),
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, UnicodeError, KeyError) as exc:
        print(json.dumps({
            "mode": "REFUSED_OR_INCOMPLETE", "error": str(exc),
            "advice": "Vérifier le dépôt et la branche avant de refaire une proposition.",
        }, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
