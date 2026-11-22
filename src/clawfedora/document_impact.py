"""Read-only impact hints when code or diagrams change.

This is a review queue, not an automatic GitHub/Notion synchronization:
only links in documents that were actually read count as observations.
"""
from __future__ import annotations

import argparse
import json
import posixpath
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

LINK = re.compile(r"!?\[[^\]\n]*\]\(([^)\n]+)\)")
MAX_DOCS = 350
MAX_DOC_BYTES = 160_000
MAX_SCAN_BYTES = 3_000_000
MAX_CHANGES = 25


def _relative(value: str) -> str:
    if not isinstance(value, str) or len(value) > 240 or not value.strip():
        raise ValueError("chemin relatif non vide requis")
    if "\\" in value or "\x00" in value or Path(value).is_absolute():
        raise ValueError("chemin de source invalide")
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts) or value.startswith("-"):
        raise ValueError("chemin de source hors périmètre")
    return value


def _safe(root: Path, relative: str) -> Path | None:
    try:
        parts = Path(relative).parts
        if any(part in (".", "..") for part in parts):
            return None
        target = root / relative
        if not target.resolve().is_relative_to(root):
            return None
        if any(path.is_symlink() for path in (target, *target.parents) if path != root):
            return None
        return target
    except (OSError, ValueError):
        return None


def _links(doc: str, text: str) -> set[str]:
    linked: set[str] = set()
    for item in LINK.findall(text):
        raw = item.split(" ", 1)[0].strip("<>")
        if raw.startswith(("#", "/", "//")):
            continue
        parsed = urlsplit(raw)
        if parsed.scheme or parsed.netloc or not parsed.path:
            continue
        target = posixpath.normpath(posixpath.join(posixpath.dirname(doc),
                                                   unquote(parsed.path)))
        if target != ".." and not target.startswith("../"):
            linked.add(target)
    return linked


def inspect(root: Path, changed: list[str]) -> dict[str, Any]:
    if not root.is_dir() or root.is_symlink():
        raise ValueError("dossier de projet non lié requis")
    root = root.resolve(strict=True)
    if (not isinstance(changed, list) or not 1 <= len(changed) <= MAX_CHANGES
            or any(not isinstance(path, str) for path in changed)
            or len(changed) != len(set(changed))):
        raise ValueError("1 à 25 chemins différents requis")
    changed = [_relative(path) for path in changed]
    candidates = sorted(root.rglob("*.md"))
    if len(candidates) > MAX_DOCS:
        raise ValueError("trop de documents : limiter le snapshot")
    docs: dict[str, tuple[str, set[str]]] = {}
    budget = MAX_SCAN_BYTES
    for file in candidates:
        relative = file.relative_to(root).as_posix()
        if "/.git/" in "/" + relative or not file.is_file() or _safe(root, relative) is None:
            continue
        size = file.stat().st_size
        if size > MAX_DOC_BYTES or size > budget:
            continue
        try:
            content = file.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        budget -= size
        docs[relative] = (content, _links(relative, content))

    findings: list[dict[str, Any]] = []
    for path in changed:
        source = _safe(root, path)
        exact: list[str] = []
        for document, (content, links) in docs.items():
            if path in links or path in content:
                exact.append(document)
        likely: list[str] = []
        lower = path.lower()
        if lower.endswith(".drawio"):
            candidate = path[:-7] + ".svg"
            if _safe(root, candidate) is not None:
                likely.append(candidate)
        elif (lower.endswith(("compose.yml", "compose.yaml", "docker-compose.yml",
                              ".tf", ".tfvars", ".j2"))
              or lower.startswith("ansible/")):
            likely.extend(["README.md", "STATUS.md", "docs/architecture.md",
                           "docs/installation.md"])
        elif lower.startswith(".github/workflows/"):
            likely.extend(["README.md", "STATUS.md", "docs/ci-cd.md"])
        likely = [p for p in dict.fromkeys(likely) if p not in exact]
        findings.append({
            "changed": path,
            "source_state": ("FOUND" if source is not None and source.is_file()
                             else "NOT_CHECKED"),
            "direct_references": exact[:70],
            "potential_review": [
                {"path": doc, "state": "FOUND" if (_safe(root, doc) or Path()).is_file()
                 else "NOT_CHECKED"}
                for doc in likely[:10]
            ],
            "notion": "NOT_CHECKED_EXPLICIT_EXPORT_REQUIRED",
        })
    return {
        "assessment": "REVIEW_QUEUE_NOT_SYNCHRONIZATION",
        "documents_scanned": len(docs),
        "changes": findings,
        "limitations": [
            "Text occurrence or Markdown link does not prove a factual inconsistency",
            "Missing source or document can be excluded from an imported snapshot",
            "Notion live pages, their images and access rights were not inspected",
            "No publishing, Git mutations or cloud access",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Préparer une revue d'impact documentaire locale")
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--changed", action="append", required=True)
    args = parser.parse_args(argv)
    try:
        result = inspect(args.path, args.changed)
    except (OSError, ValueError) as error:
        print(json.dumps({"assessment": "REFUSED", "reason": str(error)},
                         ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
