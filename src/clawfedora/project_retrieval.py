"""Bounded local cross-source retrieval for approved GitHub revisions and project notes.

The existing SQLite FTS5 search remains authoritative for intake/Notion
documents. Only the *latest* verified approved GitHub snapshot is searched
here, without reindexing or importing older versions into the agent's plan.
No remote API, embeddings, cloud transfer or cross-project reads are used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from clawfedora import github_refresh, source_connectors
from clawfedora.core_config import resolve_runtime_root
from clawfedora.knowledge import search
from clawfedora.project_common import project_path
from clawfedora.project_intake import validate_input_integrity

MAX_QUERY = 1000
MAX_TERMS = 12
MAX_GITHUB_FILES = 240
MAX_GITHUB_TEXT = 6_000_000
MAX_EXCERPT = 700
STOP = frozenset({
    "les", "des", "une", "pour", "dans", "avec", "sur", "que", "qui",
    "the", "and", "est", "sont", "aux", "par", "comment", "entre",
})


def _terms(query: str) -> list[str]:
    if not isinstance(query, str) or len(query) > MAX_QUERY:
        raise ValueError("requête de recherche absente ou supérieure à 1000 caractères")
    return list(dict.fromkeys(
        value for value in re.findall(r"[^\W_]+", query.casefold())
        if len(value) > 2 and value not in STOP
    ))[:MAX_TERMS]


def _git_candidates(
    project: Path, terms: list[str], changes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for change in changes:
        repo, commit = str(change["repository"]), str(change["current_commit"])
        # _snapshot validates the manifest and the *complete* file inventory.
        root, hashes = github_refresh._snapshot(project, repo, commit)
        if len(hashes) > MAX_GITHUB_FILES or sum(
            (root / name).stat().st_size for name in hashes
        ) > MAX_GITHUB_TEXT:
            raise ValueError("révision GitHub hors limites de recherche")
        for relative, expected_hash in sorted(hashes.items()):
            file = root / relative
            if file.stat().st_size > 1_000_000:
                continue
            payload = file.read_bytes()
            if hashlib.sha256(payload).hexdigest() != expected_hash:
                raise ValueError("source GitHub modifiée pendant la recherche")
            try:
                body = payload.decode("utf-8")
            except UnicodeDecodeError:
                continue
            if "\x00" in body:
                continue
            lowered = body.casefold()
            path_terms = relative.casefold()
            in_text = [term for term in terms if term in lowered]
            in_path = [term for term in terms if term in path_terms]
            if not in_text and not in_path:
                continue
            if in_text:
                center = min(lowered.find(term) for term in in_text)
                start = max(0, center - 140)
                end = min(len(body), start + MAX_EXCERPT)
            else:
                start, end = 0, min(len(body), MAX_EXCERPT)
            snippet = body[start:end]
            if not snippet.strip():
                continue
            score = (
                12 * len(set(in_text)) + 5 * len(set(in_path))
                + min(sum(lowered.count(term) for term in in_text), 20)
            )
            found.append({
                "path": f"github:{repo}@{commit}/{relative}",
                "page": 1,
                "line": body.count("\n", 0, start) + 1,
                "text": snippet,
                "source_sha256": expected_hash,
                "representation_path": (root / relative).relative_to(project).as_posix(),
                "representation_sha256": expected_hash,
                "start_char": start,
                "excerpt_sha256": hashlib.sha256(snippet.encode()).hexdigest(),
                "kind": "github-approved-revision",
                "repository": repo,
                "commit": commit,
                "stale": False,
                "sources": [],
                "_score": score,
            })
    return sorted(found, key=lambda item: (
        -item["_score"], item["repository"], item["path"]
    ))


def retrieve(
    repo_root: Path, project: Path, query: str, *,
    include_revisions: bool = True,
) -> list[dict[str, Any]]:
    """Four diverse, cited passages maximum, preserving the legacy 4k cap."""
    terms = _terms(query)
    if not terms:
        return []
    if validate_input_integrity(project):
        raise ValueError("sources initiales du projet altérées : recherche refusée")

    indexed = search(repo_root, project, query)
    if not include_revisions:
        return indexed
    changes = github_refresh.inspect(project)
    if not changes:
        return indexed

    # The FTS index may still contain the *original* GitHub commit.
    # The approved latest revision supersedes only those files, not Notion
    # notes, independent project documents or other repositories.
    previous_prefixes = tuple(
        "intake/GitHub-" + entry["repository"].replace("/", "-")
        + "-" + entry["initial_commit"][:12] + "/"
        for entry in changes
    )
    indexed = [
        hit for hit in indexed
        if not str(hit["path"]).startswith(previous_prefixes)
    ]
    fresh = _git_candidates(project, terms, changes)
    # Prefer two distinct current GitHub files and two distinct original
    # sources when both groups are relevant. Fill unused places by rank.
    result: list[dict[str, Any]] = []
    queued = [*fresh[:2], *indexed[:2], *fresh[2:], *indexed[2:]]
    used: set[str] = set()
    remaining = 4_000
    for hit in queued:
        name = str(hit["path"])
        if name in used or len(result) >= 4 or remaining <= 0:
            continue
        # One cited passage per source first; never repeat a stale revision.
        used.add(name)
        excerpt = str(hit["text"])[:min(MAX_EXCERPT, remaining)]
        if not excerpt:
            continue
        item = {k: v for k, v in hit.items() if not k.startswith("_")}
        item["text"] = excerpt
        item["excerpt_sha256"] = hashlib.sha256(excerpt.encode()).hexdigest()
        result.append(item)
        remaining -= len(excerpt)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clawfedora-source-search",
        description="Recherche locale dans les documents et révisions GitHub approuvées",
    )
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument(
        "--initial-only", action="store_true",
        help="ne pas consulter les révisions GitHub approuvées",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        runtime = resolve_runtime_root(str(args.runtime_root) if args.runtime_root else None)
        project = project_path(runtime, args.project_id)
        # The CLI cannot send sources to a cloud model. It only emits local JSON.
        from clawfedora.core_config import resolve_repo_root

        root = resolve_repo_root()
        hits = retrieve(root, project, args.query, include_revisions=not args.initial_only)
        print(json.dumps({
            "project_id": args.project_id,
            "mode": "LOCAL_ONLY",
            "sources": hits,
            "cloud_transfer": False,
            "validation": "TEXTUAL_MATCH_NOT_TECHNICAL_PROOF",
        }, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
