"""Explicit read-only GitHub refresh for a long-running project.

Immutable revisions are recorded outside the sealed intake. Neither the model nor a
GitHub webhook may approve updates. Versioned files are NOT automatically indexed
or sent to a cloud model; the current agent task plan remains pinned to its intake.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from contextlib import nullcontext
from pathlib import Path
from typing import Any

from clawfedora import source_connectors
from clawfedora.core_config import resolve_runtime_root
from clawfedora.project_common import (
    assert_no_symlinks,
    now,
    project_path,
    read_json,
    sha256_file,
    write_json,
)
from clawfedora.project_intake import _validate_source, validate_input_integrity
from clawfedora.project_worker import worker_lock

STORE = "context/github-updates"


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


def _directory(project: Path, repository: str) -> Path:
    key = hashlib.sha256(repository.lower().encode()).hexdigest()[:20]
    return project / STORE / key


def _initial(project: Path, repository: str) -> tuple[Path, str]:
    candidates: list[tuple[Path, str]] = []
    intake = project / "intake"
    for item in sorted(intake.iterdir()):
        if not item.is_dir() or item.is_symlink():
            continue
        provenance = item / ".source-provenance.json"
        if not provenance.is_file():
            continue
        value = read_json(provenance)
        if value.get("provider") != "github" or value.get("repository") != repository:
            continue
        commit = source_connectors._safe_sha(str(value.get("commit", "")))
        candidates.append((item, commit))
    if len(candidates) != 1:
        raise ValueError(
            "dépôt non lié de façon unique: importer d'abord un snapshot GitHub initial "
            "dans l'intake, puis ne plus modifier cet intake"
        )
    return candidates[0]


def _files(root: Path, *, exclude_provenance: bool = False) -> dict[str, str]:
    assert_no_symlinks(root, label="snapshot GitHub")
    hashes: dict[str, str] = {}
    for item in sorted(root.rglob("*")):
        if not item.is_file():
            continue
        relative = item.relative_to(root).as_posix()
        if exclude_provenance and relative == ".source-provenance.json":
            continue
        hashes[relative] = sha256_file(item)
    return hashes


def _read_registry(project: Path, repository: str, initial: str) -> dict[str, Any]:
    root = _directory(project, repository)
    ledger = root / "ledger.json"
    if not ledger.exists():
        return {"schema_version": 1, "repository": repository, "initial_commit": initial,
                "revisions": []}
    data = read_json(ledger)
    entries = data.get("revisions")
    if (
        data.get("schema_version") != 1 or data.get("repository") != repository
        or data.get("initial_commit") != initial or not isinstance(entries, list)
        or len(entries) > 100 or any(not isinstance(item, dict) for item in entries)
    ):
        raise ValueError("registre GitHub incohérent")
    previous = initial
    seen: set[str] = set()
    for item in entries:
        commit = source_connectors._safe_sha(str(item.get("commit", "")))
        if commit in seen or item.get("previous_commit") != previous:
            raise ValueError("chaîne des révisions GitHub invalide")
        seen.add(commit)
        previous = commit
    return data


def _snapshot(project: Path, repository: str, commit: str) -> tuple[Path, dict[str, str]]:
    root = _directory(project, repository) / commit
    manifest = read_json(root / "manifest.json")
    if manifest.get("commit") != commit or manifest.get("repository") != repository:
        raise ValueError("provenance de révision GitHub divergente")
    actual = _files(root / "files")
    expected = manifest.get("hashes")
    if (
        not isinstance(expected, dict) or expected != actual
        or manifest.get("digest") != _digest(actual)
    ):
        raise ValueError("snapshot GitHub modifié depuis son approbation")
    return root / "files", actual


def _diff(old: dict[str, str], new: dict[str, str]) -> list[dict[str, str]]:
    changes: list[dict[str, str]] = []
    for path in sorted(old.keys() | new.keys()):
        if path not in old:
            kind = "added"
        elif path not in new:
            kind = "removed"
        elif old[path] != new[path]:
            kind = "modified"
        else:
            continue
        changes.append({"path": path, "change": kind})
    return changes


def _affected(project: Path) -> dict[str, Any]:
    """Potentially stale scopes; no declaration or proof is modified."""
    roadmap_path = project / "context/continuous_roadmap.json"
    milestones: list[str] = []
    if roadmap_path.is_file():
        from clawfedora.project_roadmap import load

        milestones = [str(item["id"]) for item in load(project)["milestones"]]
    return {
        "milestones_to_review": milestones,
        "plan_to_review": (project / "context/project_plan.json").exists(),
        "operator_proofs_to_review": (project / "context/operator-proofs").exists(),
        "evidence_to_review": (project / "evidence").exists(),
        "verification": "NOT_VERIFIED",
    }


def inspect(project: Path) -> list[dict[str, Any]]:
    """Read-only report for dashboard and chat; no network and no secret contents."""
    assert_no_symlinks(project, label="projet")
    root = project / STORE
    if not root.exists():
        return []
    result: list[dict[str, Any]] = []
    for folder in sorted(root.iterdir()):
        if not folder.is_dir():
            raise ValueError("stockage des révisions GitHub invalide")
        record = read_json(folder / "ledger.json")
        repository = source_connectors._safe_repo(str(record.get("repository", "")))
        initial_dir, initial_commit = _initial(project, repository)
        if record.get("initial_commit") != initial_commit:
            raise ValueError("révision GitHub liée à un autre import initial")
        registry = _read_registry(project, repository, initial_commit)
        revisions: list[dict[str, Any]] = registry["revisions"]
        if not revisions:
            continue
        last = revisions[-1]
        commit = str(last["commit"])
        _, hashes = _snapshot(project, repository, commit)
        if _digest(hashes) != last.get("digest"):
            raise ValueError("digest GitHub du registre divergent")
        result.append({
            "repository": repository,
            "initial_commit": initial_commit,
            "current_commit": commit,
            "previous_commit": last["previous_commit"],
            "updated_at": last["updated_at"],
            "revision_count": len(revisions),
            "changes": last["changes"],
            "needs_requalification": last["needs_requalification"],
            "agent_context": "INITIAL_INTAKE_UNCHANGED",
        })
    return result


def refresh(
    runtime: Path, project_id: str, repository: str, commit: str, *,
    approve: str | None = None, apply: bool = False,
) -> dict[str, Any]:
    """Preview reads only; apply requires the exact digest of that same preview."""
    repository = source_connectors._safe_repo(repository)
    commit = source_connectors._safe_sha(commit)
    if apply and (not approve or len(approve) != 64):
        raise ValueError("empreinte SHA-256 de prévisualisation requise pour --apply")
    project = project_path(runtime, project_id)
    context = worker_lock(runtime, allow_gaming=True) if apply else nullcontext()
    with context:
        assert_no_symlinks(project, label="projet à actualiser")
        failures = validate_input_integrity(project)
        if failures:
            raise ValueError("intake/sources modifiés: " + "; ".join(failures))
        initial_dir, initial_commit = _initial(project, repository)
        registry = _read_registry(project, repository, initial_commit)
        revisions = registry["revisions"]
        old_commit = revisions[-1]["commit"] if revisions else initial_commit
        if old_commit == commit or any(row["commit"] == commit for row in revisions):
            raise ValueError("commit déjà enregistré pour ce projet")
        if len(revisions) >= 100:
            raise ValueError("limite de 100 révisions atteinte")
        if revisions:
            _, old_files = _snapshot(project, repository, old_commit)
        else:
            old_files = _files(initial_dir, exclude_provenance=True)
        from clawfedora.project_cloud import consent_path

        if apply and consent_path(runtime, project).exists():
            raise ValueError("révoquer l'accord cloud avant la mise à jour GitHub")
        with tempfile.TemporaryDirectory(prefix="clawfedora-github-update-") as work:
            incoming = Path(work) / "files"
            incoming.mkdir()
            source = source_connectors._github_snapshot(incoming, repository, commit)
            # In addition to existing path/size filters, reject embedded credentials.
            _validate_source(incoming, label="nouveau snapshot GitHub")
            new_files = _files(incoming)
            delta = _diff(old_files, new_files)
            value = {
                "repository": repository, "initial_commit": initial_commit,
                "previous_commit": old_commit, "commit": commit,
                "old_digest": _digest(old_files), "new_digest": _digest(new_files),
                "changes": delta, "skipped": source["skipped"],
            }
            fingerprint = _digest(value)
            assessment = _affected(project)
            result = {
                "status": "PREVIEW", "project_id": project_id,
                **value, "approve_sha256": fingerprint,
                "needs_requalification": assessment,
                "remote_writes": False,
                "agent_context": "INITIAL_INTAKE_UNCHANGED",
            }
            if not apply:
                return result
            if approve != fingerprint:
                raise ValueError("empreinte périmée ou divergente: refaire la prévisualisation")
            root = _directory(project, repository)
            root.mkdir(parents=True, exist_ok=True)
            target = root / commit
            if target.exists():
                raise ValueError("révision déjà stockée: intervention manuelle requise")
            with tempfile.TemporaryDirectory(prefix=".github-stage-", dir=root) as staging:
                temporary = Path(staging)
                shutil.copytree(incoming, temporary / "files")
                manifest = {
                    "repository": repository, "commit": commit,
                    "hashes": new_files, "digest": _digest(new_files),
                    "source": source, "saved_at": now(),
                }
                write_json(temporary / "manifest.json", manifest)
                # Rename within the same filesystem and publish the registry last.
                os.rename(temporary, target)
            entry = {
                "commit": commit, "previous_commit": old_commit,
                "updated_at": now(), "digest": _digest(new_files),
                "changes": delta, "skipped": source["skipped"],
                "needs_requalification": assessment,
            }
            try:
                write_json(root / "ledger.json", {**registry, "revisions": [*revisions, entry]})
                (root / "ledger.json").chmod(0o600)
            except OSError:
                shutil.rmtree(target)
                raise
            return {**result, "status": "RECORDED", "remote_writes": False}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clawfedora-github-refresh",
        description="Comparer puis conserver un nouveau commit GitHub sans modifier l'intake",
    )
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--github", required=True, help="dépôt initial lié: propriétaire/nom")
    parser.add_argument("--commit", required=True, help="SHA Git complet de la nouvelle version")
    parser.add_argument("--approve", help="SHA-256 exact renvoyé par la prévisualisation")
    parser.add_argument("--apply", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        runtime = resolve_runtime_root(str(args.runtime_root) if args.runtime_root else None)
        report = refresh(
            runtime, args.project_id, args.github, args.commit,
            approve=args.approve, apply=args.apply,
        )
        print(json.dumps(report, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
