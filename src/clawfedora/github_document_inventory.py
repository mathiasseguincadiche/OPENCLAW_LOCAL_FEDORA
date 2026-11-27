"""Inventory documentary and technical paths at an exact Git revision."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

from clawfedora import source_connectors as sources
from clawfedora.github_quality import SIGNALS
from clawfedora.notion_inventory_diff import _private_path, _write_private_report
from clawfedora.notion_write import _digest

MAX_ENTRIES = 12_000
MAX_TREE_BYTES = 5 * 1024 * 1024
MAX_REPORT_BYTES = 8 * 1024 * 1024
CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
MODES = {"tree": {"040000"}, "blob": {"100644", "100755", "120000"}, "commit": {"160000"}}
PRIVATE_NAMES = {"private", "prive", "privé", "secrets", ".secrets", ".aws", ".kube"}
DOC_SUFFIXES = {".md", ".rst", ".adoc", ".txt"}
GRAPHIC_SUFFIXES = {".drawio", ".svg", ".png", ".jpg", ".webp", ".pdf"}
CLASSIFICATION = "private_local_only"


class InventoryError(ValueError):
    """A selected tree cannot produce a complete, safe inventory."""


def _local_git(root: Path, *args: str) -> bytes:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_NO_LAZY_FETCH="1", GIT_OPTIONAL_LOCKS="0",
               GIT_TERMINAL_PROMPT="0", GIT_ALLOW_PROTOCOL="")
    with tempfile.TemporaryFile() as output:
        try:
            result = subprocess.run(
                ["git", "--no-replace-objects", "-C", str(root), *args],
                stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.DEVNULL,
                env=env, timeout=25, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise InventoryError("Git local indisponible ou délai dépassé") from None
        if result.returncode != 0:
            raise InventoryError("révision ou arbre Git local indisponible")
        output.seek(0)
        value = output.read(MAX_TREE_BYTES + 1)
    if len(value) > MAX_TREE_BYTES:
        raise InventoryError("sortie d'inventaire Git trop volumineuse")
    return value


def _local_entries(raw: bytes) -> list[dict[str, str]]:
    if not raw:
        return []
    if not raw.endswith(b"\x00") or raw.count(b"\x00") > MAX_ENTRIES:
        raise InventoryError("arbre Git local incomplet ou trop volumineux")
    entries = []
    for line in raw[:-1].split(b"\x00"):
        try:
            metadata, path = line.split(b"\t", 1)
            mode, kind, oid = metadata.decode("ascii").split()
        except (UnicodeError, ValueError):
            raise InventoryError("métadonnées Git locales invalides") from None
        entries.append({
            "mode": mode, "type": kind, "sha": oid,
            "path": path.decode("utf-8", errors="surrogateescape"),
        })
    return entries


def _path(raw: str) -> tuple[PurePosixPath | None, str | None]:
    if len(raw) > 700 or CONTROL.search(raw) or any(0xD800 <= ord(char) <= 0xDFFF for char in raw):
        return None, "unsupported_path"
    parts = raw.split("/")
    if "\\" in raw or any(part in {"", ".", ".."} for part in parts):
        raise InventoryError("chemin d'arbre Git invalide")
    if any(part.casefold() in PRIVATE_NAMES or part.casefold().startswith(".env")
           for part in parts):
        return None, "confidential_path"
    try:
        return sources._safe_path(raw), None
    except sources.SourceImportError:
        return None, "excluded_path"


def _category(path: PurePosixPath) -> str:
    parts = tuple(part.casefold() for part in path.parts)
    basename, suffix = path.name.casefold(), path.suffix.casefold()
    if parts[:2] == (".github", "workflows") and suffix in {".yml", ".yaml"}:
        return "workflow"
    if parts[0] == "evidence" or parts[:2] == ("docs", "evidence"):
        return "evidence"
    if basename in {"license", "copying"} or basename.startswith(("license.", "copying.")):
        return "governance"
    if parts[0] == "docs" and suffix in GRAPHIC_SUFFIXES:
        return "documentation_asset"
    if suffix in DOC_SUFFIXES or basename.startswith("readme"):
        return "documentation"
    return "technical" if sources._is_text(path) else "asset_or_other"


def _inventory(
    commit: str, tree: str, entries: object, repository: str | None = None,
) -> dict[str, Any]:
    sources._safe_sha(commit)
    if not isinstance(tree, str) or not sources.SHA40.fullmatch(tree):
        raise InventoryError("identité d'arbre Git invalide")
    if not isinstance(entries, list) or len(entries) > MAX_ENTRIES:
        raise InventoryError("arbre Git incomplet ou budget d'entrées dépassé")
    seen: set[str] = set()
    excluded: Counter[str] = Counter()
    entries_by_type: Counter[str] = Counter()
    visible: dict[str, dict[str, str]] = {}
    directories: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise InventoryError("entrée Git invalide")
        path, kind, mode, sha = (entry.get(k) for k in ("path", "type", "mode", "sha"))
        if (
            not isinstance(path, str) or path in seen or not isinstance(kind, str)
            or kind not in MODES or not isinstance(mode, str) or mode not in MODES[kind]
            or not isinstance(sha, str) or not sources.SHA40.fullmatch(sha)
        ):
            raise InventoryError("identité, type ou chemin Git incohérent")
        seen.add(path)
        entries_by_type[kind] += 1
        relative, exclusion = _path(path)
        if exclusion is not None:
            excluded[exclusion] += 1
        elif kind == "tree":
            directories.add(path)
        elif mode in {"120000", "160000"}:
            excluded["symlink" if mode == "120000" else "submodule"] += 1
        elif relative is not None:
            visible[path] = {"path": path, "category": _category(relative), "mode": mode,
                             "git_blob": sha}
    paths = visible.keys() | directories
    signals = [{"id": name, "paths": sorted(path for path in choices if path in paths)}
               for name, choices in SIGNALS]
    body = {
        "schema": 1, "classification": CLASSIFICATION,
        "assessment": "GIT_DOCUMENTARY_METADATA_REVIEW_REQUIRED",
        "repository": repository, "commit": commit, "git_tree": tree,
        "entries_by_git_type": dict(sorted(entries_by_type.items())),
        "counts_by_category": dict(sorted(
            Counter(row["category"] for row in visible.values()).items()
        )),
        "excluded_entries": dict(sorted(excluded.items())),
        "signals": signals, "files": [visible[path] for path in sorted(visible)],
        "limits": ["file_contents_not_read", "links_and_anchors_not_checked",
                   "workflow_config_and_ci_status_not_checked", "path_presence_only"],
    }
    return {**body, "inventory_sha256": _digest(body)}


def inventory_local(root: Path, commit: str) -> dict[str, Any]:
    commit = sources._safe_sha(commit)
    if root.is_symlink() or not root.is_dir():
        raise InventoryError("dépôt local non lié requis")
    root = root.resolve(strict=True)
    identity = _local_git(root, "rev-parse", "--verify", commit + "^{commit}").strip()
    if identity != commit.encode("ascii"):
        raise InventoryError("Git n'a pas retourné le commit demandé")
    tree = _local_git(root, "rev-parse", "--verify", commit + "^{tree}").decode("ascii").strip()
    if not sources.SHA40.fullmatch(tree):
        raise InventoryError("identité d'arbre Git invalide")
    data = _local_git(root, "ls-tree", "-r", "-t", "-z", "--full-tree", tree)
    return _inventory(commit, tree, _local_entries(data))


def inventory_github(repository: str, commit: str) -> dict[str, Any]:
    repository, commit = sources._safe_repo(repository), sources._safe_sha(commit)
    tree, data = sources._github_tree(repository, commit)
    if data.get("sha") != tree:
        raise InventoryError("GitHub n'a pas retourné l'arbre demandé")
    return _inventory(commit, tree, data["tree"], repository)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inventorier les chemins d'un commit Git complet")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--path", type=Path)
    source.add_argument("--github")
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        output = _private_path(args.output)
        if output.exists():
            raise InventoryError("la destination doit être un fichier neuf")
        report = (inventory_local(args.path, args.commit) if args.path is not None
                  else inventory_github(args.github, args.commit))
        size = len(json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")) + 1
        if size > MAX_REPORT_BYTES:
            raise InventoryError("rapport d'inventaire trop volumineux")
        _write_private_report(output, report)
    except (InventoryError, sources.SourceImportError) as exc:
        print(f"GITHUB_DOCUMENTARY_INVENTORY=REFUSED {exc}")
        return 2
    except (OSError, ValueError, RecursionError):
        print("GITHUB_DOCUMENTARY_INVENTORY=REFUSED entrée ou destination illisible")
        return 2
    print(f"GITHUB_DOCUMENTARY_INVENTORY=REVIEW_REQUIRED sha256={report['inventory_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
