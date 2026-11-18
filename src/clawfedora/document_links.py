"""Check Markdown destinations inside one snapshot, without following network links."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt

from clawfedora.project_common import assert_no_symlinks


def _anchors(markdown: str) -> set[str]:
    tokens = MarkdownIt().parse(markdown)
    anchors: set[str] = set()
    for i, token in enumerate(tokens):
        if token.type != "heading_open":
            continue
        text = "".join(
            t.content for t in tokens[i + 1].children or [] if t.type in {"text", "code_inline"}
        )
        base = re.sub(r"[^\w -]", "", text.lower()).replace(" ", "-")
        slug = base
        n = 0
        while slug in anchors:
            n += 1
            slug = f"{base}-{n}"
        anchors.add(slug)
    return anchors


def check_links(workspace: Path, data: dict[str, Any]) -> dict[str, Any]:
    scope, document, content = data.get("scope"), data.get("document"), data.get("content")
    if not all(
        isinstance(p, str) and p and not Path(p).is_absolute() and ".." not in Path(p).parts
        for p in (scope, document)
    ):
        raise ValueError("scope et document relatifs requis")
    root = workspace / str(scope)
    if not root.resolve().is_relative_to(workspace.resolve()) or not root.is_dir():
        raise ValueError("snapshot inaccessible")
    assert_no_symlinks(root, label="liens")
    source = root / str(document)
    if (
        source.suffix.lower() != ".md"
        or not isinstance(content, str)
        or len(content.encode()) > 12000
    ):
        raise ValueError("source Markdown bornée requise")
    checked = external = 0
    findings: list[dict[str, Any]] = []
    anchors = {source.resolve(): _anchors(content)}
    for token in MarkdownIt().parse(content):
        for child in token.children or []:
            if child.type not in {"link_open", "image"}:
                continue
            href = str(child.attrGet("href" if child.type == "link_open" else "src") or "")
            url = urlsplit(href)
            if url.scheme or url.netloc:
                external += 1
                continue
            checked += 1
            if checked > 80:
                raise ValueError("plus de 80 liens locaux: découper le document")
            target = ((source.parent / unquote(url.path)) if url.path else source).resolve()
            reason = ""
            if not target.is_relative_to(root.resolve()):
                reason = "hors du snapshot"
            elif target != source.resolve() and not target.is_file():
                reason = "fichier absent"
            elif url.fragment and target.suffix.lower() == ".md":
                if target not in anchors and target.stat().st_size <= 128000:
                    anchors[target] = _anchors(target.read_text(encoding="utf-8"))
                if unquote(url.fragment) not in anchors.get(target, set()):
                    reason = "ancre absente ou non vérifiable"
            if reason:
                findings.append(
                    {
                        "line": token.map[0] + 1 if token.map else None,
                        "link": href[:200],
                        "reason": reason,
                    }
                )
    return {
        "local_links": checked,
        "external_unchecked": external,
        "findings": findings,
        "scope": "liens locaux et ancres des titres Markdown; rendu natif non vérifié",
        "status": "FAIL" if findings else "PASS",
    }
