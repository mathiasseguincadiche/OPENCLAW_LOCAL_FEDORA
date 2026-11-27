"""Check documentation links against the files and Markdown blobs of one Git commit."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote, unquote, urlsplit

from markdown_it import MarkdownIt
from markdown_it.token import Token

from clawfedora import github_document_inventory as inv
from clawfedora import source_connectors as sources
from clawfedora.notion_inventory_diff import _private_path, _write_private_report
from clawfedora.notion_write import _digest

MAX_BLOBS = 400
MAX_DOCUMENT_BYTES = 256_000
MAX_TOTAL_BYTES = 8_000_000
MAX_LINKS = 16_000
MAX_FINDINGS = 2_000
MARKDOWN = {".md", ".markdown", ".mdown", ".mkd"}
HEX_ESCAPE = re.compile(r"%(?![0-9a-fA-F]{2})")
BROKEN = {"missing_path", "missing_anchor", "path_case_mismatch", "outside_repository"}


@dataclass
class Document:
    anchors: set[str] = field(default_factory=set)
    links: list[tuple[int, str]] = field(default_factory=list)


class Markup(HTMLParser):
    def __init__(self, document: Document, line: int) -> None:
        super().__init__(convert_charrefs=True)
        self.document = document
        self.line = line

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        fields = dict(attrs)
        if tag == "a" and fields.get("name"):
            self.document.anchors.add(fields["name"] or "")
        link = fields.get({"a": "href", "img": "src"}.get(tag, ""))
        if link:
            self.document.links.append((self.line + self.getpos()[0] - 1, link))


def _markup(content: str, document: Document, line: int) -> None:
    parser = Markup(document, line)
    parser.feed(content)
    parser.close()


def _heading(children: list[Token]) -> str:
    text = "".join(t.content for t in children if t.type in {"text", "code_inline", "image"})
    return re.sub(r"[^\w -]", "", text.strip().lower()).replace(" ", "-")


def _document(text: str) -> Document:
    document = Document()
    headings: set[str] = set()
    tokens = MarkdownIt("commonmark", {"html": True}).parse(text)
    for index, token in enumerate(tokens):
        line = token.map[0] + 1 if token.map else 1
        if token.type == "heading_open":
            base = _heading(tokens[index + 1].children or [])
            if base:
                anchor, suffix = base, 0
                while anchor in headings:
                    suffix += 1
                    anchor = f"{base}-{suffix}"
                headings.add(anchor)
        elif token.type == "html_block":
            _markup(token.content, document, line)
        for child in token.children or []:
            if child.type == "html_inline":
                _markup(child.content, document, line)
            elif child.type in {"link_open", "image"}:
                href = child.attrGet("href" if child.type == "link_open" else "src")
                if href:
                    document.links.append((line, str(href)))
    document.anchors.update(headings)
    return document


def _resolve(path: str, source: str) -> str | None:
    if not path:
        return source
    stack = [] if path.startswith("/") else source.split("/")[:-1]
    for part in path.split("/"):
        if part == "..":
            if not stack:
                return None
            stack.pop()
        elif part not in {"", "."}:
            stack.append(part)
    return "/".join(stack)


def _destination(
    href: str, source: str, repository: str | None, commit: str,
) -> tuple[str, str | None, str]:
    if len(href) > 2048 or inv.CONTROL.search(href) or HEX_ESCAPE.search(href):
        return "invalid_destination", None, ""
    try:
        url = urlsplit(href)
        path, anchor = unquote(url.path, errors="strict"), unquote(url.fragment, errors="strict")
        host = url.hostname
    except (ValueError, UnicodeError):
        return "invalid_destination", None, ""
    if inv.CONTROL.search(path + anchor) or "\\" in path:
        return "invalid_destination", None, ""
    if url.scheme or url.netloc:
        parts = path.lstrip("/").split("/", 4)
        if (
            url.scheme != "https" or url.netloc.casefold() != "github.com" or host != "github.com"
            or repository is None or len(parts) < 4
            or "/".join(parts[:2]).casefold() != repository.casefold()
            or parts[2] not in {"blob", "tree"}
        ):
            return "external_not_checked", None, ""
        if parts[3] != commit:
            return "other_revision_not_checked", None, ""
        path = "/" + (parts[4] if len(parts) == 5 else "")
    resolved = _resolve(path, source)
    if resolved is None:
        return "outside_repository", None, ""
    return "internal", resolved, anchor


def _github_blob(repository: str, sha: str) -> bytes | None:
    slug = "/".join(quote(part, safe="") for part in repository.split("/"))
    data = sources._github(f"/repos/{slug}/git/blobs/{sha}")
    if (
        data.get("sha") != sha or data.get("encoding") != "base64"
        or type(data.get("size")) is not int or data["size"] < 0
        or not isinstance(data.get("content"), str)
    ):
        raise inv.InventoryError("identité ou format du blob GitHub invalide")
    if data["size"] > MAX_DOCUMENT_BYTES:
        return None
    try:
        raw = base64.b64decode("".join(data["content"].split()), validate=True)
    except ValueError:
        raise inv.InventoryError("blob GitHub non décodable") from None
    if len(raw) != data["size"]:
        raise inv.InventoryError("taille du blob GitHub divergente")
    return raw


def _check_blob(raw: bytes, sha: str) -> None:
    # The SHA-1 is the Git object identifier, not the integrity seal of the report.
    identity = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw, usedforsecurity=False).hexdigest()
    if identity != sha:
        raise inv.InventoryError("contenu divergent de l'identifiant du blob Git")


def _scope(value: str) -> str:
    value = value.rstrip("/")
    path, reason = inv._path(value)
    if path is None or reason is not None:
        raise inv.InventoryError("périmètre documentaire hors inventaire")
    return path.as_posix()


def _markdown(path: str) -> bool:
    return PurePosixPath(path).suffix.casefold() in MARKDOWN



class LinkAudit:
    def __init__(
        self, inventory: dict[str, Any], entries: list[dict[str, Any]],
        blob: Callable[[str], bytes | None], repository: str | None,
    ) -> None:
        self.inventory = inventory
        self.files = {row["path"]: row["git_blob"] for row in inventory["files"]}
        self.all_paths = {entry["path"]: entry for entry in entries}
        self.directories = {
            path for path, entry in self.all_paths.items()
            if entry["type"] == "tree" and inv._path(path)[0] is not None
        } | {""}
        self.casefolded: dict[str, list[str]] = defaultdict(list)
        for path in sorted(self.files.keys() | self.directories):
            self.casefolded[path.casefold()].append(path)
        self.repository = repository
        self.blob = blob
        self.cache: dict[str, Document | None] = {}
        self.bytes_read = 0

    def _read(self, path: str) -> Document | None:
        identity = self.files[path]
        if identity in self.cache:
            return self.cache[identity]
        if len(self.cache) >= MAX_BLOBS:
            raise inv.InventoryError("budget de blobs Markdown dépassé : réduire le périmètre")
        known_size = self.all_paths[path].get("size")
        raw = (
            None if type(known_size) is int and known_size > MAX_DOCUMENT_BYTES
            else self.blob(identity)
        )
        document = None
        if raw is not None and len(raw) <= MAX_DOCUMENT_BYTES:
            self.bytes_read += len(raw)
            if self.bytes_read > MAX_TOTAL_BYTES:
                raise inv.InventoryError("budget de contenu Markdown dépassé : réduire le périmètre")
            _check_blob(raw, identity)
            try:
                text = raw.decode("utf-8-sig")
            except UnicodeError:
                text = ""
            if "\0" not in text and (text or not raw):
                document = _document(text)
        self.cache[identity] = document
        return document

    def _status(self, source: str, href: str) -> tuple[str, str | None]:
        state, target, anchor = _destination(
            href, source, self.repository, self.inventory["commit"],
        )
        if target is None:
            return state, None
        if target and inv._path(target)[0] is None:
            return "target_excluded", None
        if target not in self.files and target not in self.directories:
            prefixes = target.split("/")
            if any("/".join(prefixes[:i]) in self.all_paths
                   and self.all_paths["/".join(prefixes[:i])]["mode"] in {"120000", "160000"}
                   for i in range(1, len(prefixes) + 1)):
                return "target_excluded", None
            if self.casefolded.get(target.casefold()):
                return "path_case_mismatch", target
            return "missing_path", target
        if not anchor:
            return "valid_path", target
        if target not in self.files or not _markdown(target):
            return "fragment_not_checked", target
        document = self._read(target)
        if document is None:
            return "target_content_not_checked", target
        return ("valid_anchor" if anchor in document.anchors else "missing_anchor"), target

    def report(self, scopes: list[str]) -> dict[str, Any]:
        roots = sorted({_scope(item) for item in scopes})
        if any(scope not in self.files and scope not in self.directories for scope in roots):
            raise inv.InventoryError("périmètre absent du commit")
        selected = sorted(path for path in self.files if _markdown(path) and (
            not roots or any(path == scope or path.startswith(scope + "/") for scope in roots)
        ))
        if not selected:
            raise inv.InventoryError("aucun document Markdown dans le périmètre")
        checked: list[str] = []
        omitted: list[str] = []
        findings: list[dict[str, Any]] = []
        statuses: Counter[str] = Counter()
        checked_links = 0
        for path in selected:
            doc = self._read(path)
            if doc is None:
                omitted.append(path)
                continue
            checked.append(path)
            for line, href in doc.links:
                checked_links += 1
                if checked_links > MAX_LINKS:
                    raise inv.InventoryError("budget de liens dépassé : réduire le périmètre")
                state, target = self._status(path, href)
                statuses[state] += 1
                if state not in {
                    "valid_path", "valid_anchor", "external_not_checked",
                    "other_revision_not_checked",
                }:
                    findings.append({"path": path, "line": line, "status": state, "target": target})
                    if len(findings) > MAX_FINDINGS:
                        raise inv.InventoryError("trop de constats : réduire le périmètre")
        body = {
            "schema": 1, "classification": inv.CLASSIFICATION,
            "assessment": "GIT_DOCUMENTARY_LINKS_REVIEW_REQUIRED",
            "repository": self.repository, "commit": self.inventory["commit"],
            "git_tree": self.inventory["git_tree"],
            "inventory_sha256": self.inventory["inventory_sha256"],
            "scopes": roots, "markdown_inspected": checked, "markdown_not_checked": omitted,
            "counts_by_status": dict(sorted(statuses.items())),
            "broken_count": sum(statuses[state] for state in BROKEN),
            "findings": findings,
            "limits": ["markdown_only", "links_not_followed",
                       "heading_anchors_and_explicit_a_name_only",
                       "code_line_fragments_and_github_render_not_checked"],
        }
        return {**body, "report_sha256": _digest(body)}


def audit_local(
    root: Path, commit: str, scopes: list[str], *, repository: str | None = None,
    expected_inventory: str | None = None,
) -> dict[str, Any]:
    if repository is not None:
        repository = sources._safe_repo(repository)
    tree, entries = inv._local_tree(root, commit)
    manifest = inv._inventory(commit, tree, entries)
    _require_inventory(manifest, expected_inventory)
    def read_blob(sha: str) -> bytes | None:
        size = int(inv._local_git(root, "cat-file", "-s", sha))
        return None if size > MAX_DOCUMENT_BYTES else inv._local_git(root, "cat-file", "blob", sha)

    return LinkAudit(manifest, entries, read_blob, repository).report(scopes)


def audit_github(
    repository: str, commit: str, scopes: list[str], *, expected_inventory: str | None = None,
) -> dict[str, Any]:
    repository = sources._safe_repo(repository)
    tree, data = sources._github_tree(repository, commit)
    if data.get("sha") != tree:
        raise inv.InventoryError("GitHub n'a pas retourné l'arbre demandé")
    entries = data["tree"]
    manifest = inv._inventory(commit, tree, entries, repository)
    _require_inventory(manifest, expected_inventory)
    return LinkAudit(manifest, entries, lambda sha: _github_blob(repository, sha),
                     repository).report(scopes)


def _require_inventory(manifest: dict[str, Any], expected: str | None) -> None:
    if expected is not None and expected != manifest["inventory_sha256"]:
        raise inv.InventoryError("empreinte d'inventaire différente de la révision sélectionnée")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Vérifier les liens Markdown d'un commit Git")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--path", type=Path)
    source.add_argument("--github")
    parser.add_argument("--commit", required=True)
    parser.add_argument("--scope", action="append", default=[])
    parser.add_argument("--repository", help="Slug GitHub pour résoudre les liens absolus du clone")
    parser.add_argument("--inventory-sha256")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        output = _private_path(args.output)
        if output.exists():
            raise inv.InventoryError("la destination doit être un fichier neuf")
        if args.path is None:
            if args.repository is not None:
                raise inv.InventoryError("--repository est réservé à --path")
            report = audit_github(
                args.github, args.commit, args.scope, expected_inventory=args.inventory_sha256,
            )
        else:
            report = audit_local(
                args.path, args.commit, args.scope, repository=args.repository,
                expected_inventory=args.inventory_sha256,
            )
        if len(json.dumps(report, ensure_ascii=False, indent=2).encode()) + 1 > inv.MAX_REPORT_BYTES:
            raise inv.InventoryError("rapport de liens trop volumineux")
        _write_private_report(output, report)
    except (inv.InventoryError, sources.SourceImportError) as exc:
        print(f"GITHUB_DOCUMENTARY_LINKS=REFUSED {exc}")
        return 2
    except (OSError, ValueError, RecursionError):
        print("GITHUB_DOCUMENTARY_LINKS=REFUSED entrée ou destination illisible")
        return 2
    print(f"GITHUB_DOCUMENTARY_LINKS=REVIEW_REQUIRED broken={report['broken_count']}")
    return 1 if report["broken_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
