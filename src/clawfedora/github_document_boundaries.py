"""Review exact duplicates and documentary public/private boundaries at one Git SHA."""
from __future__ import annotations

import argparse
import json
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

from markdown_it import MarkdownIt

from clawfedora import github_document_inventory as inv
from clawfedora import github_document_links as links
from clawfedora import source_connectors as sources
from clawfedora.notion_inventory_diff import _load_snapshot, _private_path, _write_private_report
from clawfedora.notion_write import _digest

MAX_SCOPES = 40
MAX_MARKERS = 30
MAX_FINDINGS = 2000
MAX_PASSAGES = 20_000
ARCHIVAL = {"archives", "archive", "examples", "exemples", "templates"}


def _path(value: object) -> str:
    if not isinstance(value, str) or not 0 < len(value) <= 700 or inv.CONTROL.search(value):
        raise inv.InventoryError("chemin de périmètre invalide")
    if "\\" in value or any(part in {"", ".", ".."} for part in value.split("/")):
        raise inv.InventoryError("périmètre Git relatif requis")
    return value


def _under(path: str, scope: str) -> bool:
    return path == scope or path.startswith(scope + "/")


def _policy(value: object) -> tuple[list[str], list[str]]:
    if value is None:
        return [], []
    if (
        not isinstance(value, dict) or set(value) != {"schema", "private_paths", "literals"}
        or type(value["schema"]) is not int or value["schema"] != 1
        or not isinstance(value["private_paths"], list) or len(value["private_paths"]) > MAX_SCOPES
        or not isinstance(value["literals"], list) or len(value["literals"]) > MAX_MARKERS
    ):
        raise inv.InventoryError("format de politique privée invalide")
    paths = sorted({_path(path).casefold() for path in value["private_paths"]})
    markers = []
    for text in value["literals"]:
        if not isinstance(text, str) or not 12 <= len(text) <= 512 or inv.CONTROL.search(text):
            raise inv.InventoryError("littéral de politique privée invalide")
        markers.append(text.casefold())
    if len(markers) != len(set(markers)):
        raise inv.InventoryError("littéraux de politique privée dupliqués")
    return paths, markers


def _protected(path: str, scopes: list[str], markers: list[str]) -> bool:
    key = path.casefold()
    return (
        inv._path(path)[0] is None or any(_under(key, scope) for scope in scopes)
        or any(marker in key for marker in markers)
    )


def _location(path: str, line: int | None = None) -> dict[str, Any]:
    context = "archive_or_template" if set(path.casefold().split("/")[:-1]) & ARCHIVAL else "document"
    report: dict[str, Any] = {"path": path, "context": context}
    if line is not None:
        report["line"] = line
    return report


def _passages(content: str) -> list[tuple[str, int]]:
    tokens = MarkdownIt().parse(content)
    result = []
    for index, token in enumerate(tokens[:-1]):
        if token.type != "paragraph_open" or token.map is None:
            continue
        parts = tokens[index + 1].children or []
        text = "".join(child.content if child.type == "text" else " "
                       for child in parts if child.type in {"text", "softbreak", "hardbreak"})
        plain = unicodedata.normalize("NFC", " ".join(text.casefold().split()))
        if len(plain) >= 120 and len(plain.split()) >= 18:
            result.append((_digest(plain), token.map[0] + 1))
    return result


class Audit:
    def __init__(
        self, inventory: dict[str, Any], entries: list[dict[str, Any]],
        blob: Callable[[str], bytes | None], repository: str | None, policy: object,
    ) -> None:
        self.inventory, self.blob, self.repository = inventory, blob, repository
        self.private_scopes, self.markers = _policy(policy)
        self.entries: dict[str, dict[str, Any]] = {row["path"]: row for row in entries}
        self.files: dict[str, str] = {row["path"]: row["git_blob"] for row in inventory["files"]}
        self.protected = {path for path in self.entries
                          if _protected(path, self.private_scopes, self.markers)}
        self.private_blobs = {self.entries[path]["sha"] for path in self.protected
                              if self.entries[path]["mode"] in {"100644", "100755"}}
        self.findings: list[dict[str, Any]] = []
        self.cache: dict[str, str | None] = {}
        self.read_bytes = 0

    def _add(self, code: str, locations: list[dict[str, Any]], **detail: Any) -> None:
        if len(self.findings) >= MAX_FINDINGS:
            raise inv.InventoryError("budget de constats dépassé : réduire le périmètre")
        self.findings.append({"code": code, "locations": locations, **detail})

    def _read(self, path: str) -> str | None:
        sha = self.files[path]
        if sha in self.cache:
            return self.cache[sha]
        if len(self.cache) >= links.MAX_BLOBS:
            raise inv.InventoryError("budget de documents dépassé : réduire le périmètre")
        size = self.entries[path].get("size")
        raw = (
            None if type(size) is int and size > links.MAX_DOCUMENT_BYTES else self.blob(sha)
        )
        content = None
        if raw is not None and len(raw) <= links.MAX_DOCUMENT_BYTES:
            self.read_bytes += len(raw)
            if self.read_bytes > links.MAX_TOTAL_BYTES:
                raise inv.InventoryError("budget de contenu dépassé : réduire le périmètre")
            links._check_blob(raw, sha)
            try:
                decoded = raw.decode("utf-8-sig")
                if "\0" not in decoded:
                    content = decoded
            except UnicodeError:
                pass
        self.cache[sha] = content
        return content

    def _check_boundary(self, path: str, content: str) -> None:
        for line, raw in enumerate(content.splitlines(), 1):
            key = raw.casefold()
            hits = [index for index, marker in enumerate(self.markers, 1) if marker in key]
            if hits:
                self._add("private_literal_in_public_document", [_location(path, line)],
                          operator_rule_positions=hits)
        for line, href in links._document(content).links:
            _, target, _ = links._destination(
                href, path, self.repository, self.inventory["commit"],
            )
            if target:
                parts = target.split("/")
                linked = any(self.entries.get("/".join(parts[:i]), {}).get("mode")
                             in {"120000", "160000"} for i in range(1, len(parts) + 1))
                if linked or _protected(target, self.private_scopes, self.markers):
                    self._add("restricted_target_reference", [_location(path, line)])

    def report(self, public_scopes: list[str]) -> dict[str, Any]:
        if len(public_scopes) > MAX_SCOPES:
            raise inv.InventoryError("trop de périmètres publics déclarés")
        scopes = sorted({_path(scope) for scope in public_scopes})
        if any(scope not in self.entries for scope in scopes):
            raise inv.InventoryError("périmètre public absent du commit")
        selected = self.entries.keys() if not scopes else {
            path for path in self.entries if any(_under(path, scope) for scope in scopes)
        }
        excluded = {path for path in selected & self.protected
                    if self.entries[path]["type"] != "tree"}
        if excluded:
            self._add("restricted_paths_in_public_scope", [], count=len(excluded))
        candidates = sorted(
            path for path in (selected & self.files.keys()) - self.protected if links._markdown(path)
        )
        if not candidates and not excluded:
            raise inv.InventoryError("aucun document Markdown dans le périmètre public")
        exact: dict[str, list[dict[str, Any]]] = defaultdict(list)
        repeated: dict[str, list[dict[str, Any]]] = defaultdict(list)
        checked: list[str] = []
        omitted: list[str] = []
        passage_count = 0
        for path in candidates:
            sha = self.files[path]
            location = _location(path)
            exact[sha].append(location)
            if sha in self.private_blobs:
                self._add("public_blob_matches_private_path", [location])
                omitted.append(path)
                continue
            content = self._read(path)
            if content is None:
                omitted.append(path)
                continue
            checked.append(path)
            self._check_boundary(path, content)
            for digest, line in _passages(content):
                passage_count += 1
                if passage_count > MAX_PASSAGES:
                    raise inv.InventoryError("budget de passages dépassé : réduire le périmètre")
                repeated[digest].append(_location(path, line))
        for locations in exact.values():
            if len(locations) > 1:
                self._add("identical_documents", locations)
        for locations in repeated.values():
            if len({location["path"] for location in locations}) > 1:
                self._add("repeated_normalized_passage", locations)
        report = {
            "schema": 1, "classification": inv.CLASSIFICATION,
            "assessment": "GIT_DOCUMENTARY_BOUNDARIES_REVIEW_REQUIRED",
            "repository": self.repository, "commit": self.inventory["commit"],
            "git_tree": self.inventory["git_tree"],
            "inventory_sha256": self.inventory["inventory_sha256"],
            "coverage": {
                "whole_tree_declared_public": not scopes, "declared_public_scopes": len(scopes),
                "policy_paths": len(self.private_scopes), "policy_literals": len(self.markers),
                "documents_checked": checked, "documents_not_read": omitted,
                "passages_examined": passage_count,
            },
            "counts_by_code": dict(sorted(Counter(row["code"] for row in self.findings).items())),
            "findings": self.findings,
            "limits": ["intended_visibility_declared_by_operator", "current_commit_only",
                       "literal_and_normalized_text_signals_only",
                       "private_blobs_and_external_targets_not_read", "no_acl_or_secret_scan"],
        }
        return {**report, "report_sha256": _digest(report)}



def audit_local(
    root: Path, commit: str, public_scopes: list[str], *, policy: object = None,
    repository: str | None = None, expected_inventory: str | None = None,
) -> dict[str, Any]:
    if repository is not None:
        repository = sources._safe_repo(repository)
    tree, entries = inv._local_tree(root, commit)
    inventory = inv._inventory(commit, tree, entries)
    links._require_inventory(inventory, expected_inventory)
    return Audit(inventory, entries, lambda sha: links._local_blob(root, sha),
                 repository, policy).report(public_scopes)


def audit_github(
    repository: str, commit: str, public_scopes: list[str], *, policy: object = None,
    expected_inventory: str | None = None,
) -> dict[str, Any]:
    repository = sources._safe_repo(repository)
    tree, data = sources._github_tree(repository, commit)
    if data.get("sha") != tree:
        raise inv.InventoryError("GitHub n'a pas retourné l'arbre demandé")
    entries = data["tree"]
    inventory = inv._inventory(commit, tree, entries, repository)
    links._require_inventory(inventory, expected_inventory)
    return Audit(inventory, entries, lambda sha: links._github_blob(repository, sha),
                 repository, policy).report(public_scopes)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Examiner doublons et frontières documentaires")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--path", type=Path)
    source.add_argument("--github")
    audience = parser.add_mutually_exclusive_group(required=True)
    audience.add_argument("--public-scope", action="append", default=[])
    audience.add_argument("--public-tree", action="store_true")
    parser.add_argument("--commit", required=True)
    parser.add_argument("--repository", help="Slug GitHub pour les liens absolus du clone")
    parser.add_argument("--private-policy", type=Path)
    parser.add_argument("--inventory-sha256")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        output = _private_path(args.output)
        if output.exists():
            raise inv.InventoryError("la destination doit être un fichier neuf")
        policy = _load_snapshot(args.private_policy) if args.private_policy is not None else None
        if args.private_policy is not None and not isinstance(policy, dict):
            raise inv.InventoryError("objet JSON de politique privée requis")
        if args.path is None:
            if args.repository is not None:
                raise inv.InventoryError("--repository est réservé à --path")
            result = audit_github(
                args.github, args.commit, args.public_scope, policy=policy,
                expected_inventory=args.inventory_sha256,
            )
        else:
            result = audit_local(
                args.path, args.commit, args.public_scope, policy=policy,
                repository=args.repository, expected_inventory=args.inventory_sha256,
            )
        if len(json.dumps(result, ensure_ascii=False, indent=2).encode()) + 1 > inv.MAX_REPORT_BYTES:
            raise inv.InventoryError("rapport de frontières trop volumineux")
        _write_private_report(output, result)
    except (inv.InventoryError, sources.SourceImportError) as exc:
        print(f"GITHUB_DOCUMENTARY_BOUNDARIES=REFUSED {exc}")
        return 2
    except (OSError, ValueError, RecursionError):
        print("GITHUB_DOCUMENTARY_BOUNDARIES=REFUSED entrée ou destination illisible")
        return 2
    print(f"GITHUB_DOCUMENTARY_BOUNDARIES=REVIEW_REQUIRED findings={len(result['findings'])}")
    return 1 if result["findings"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
