"""Read-only Notion snapshot inventory and offline Premium studio preflight.

No credential, API call, remote change, semantic verdict or progression update.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from clawfedora import editorial_notion as en

SPACES = ("comprendre", "préparer", "pratiquer", "suivre", "ressources")
ID = re.compile(r"[0-9a-f]{32}\Z")
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
MAX_PAGES = 20
MAX_BYTES = 6_000_000
MAX_FINDINGS = 40


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _headings(text: str) -> list[tuple[int, int, str]]:
    headings: list[tuple[int, int, str]] = []
    fence: str | None = None
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        marker = re.match(r"^(`{3,}|~{3,})", stripped)
        if marker:
            token = marker[1]
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            continue
        match = HEADING.fullmatch(line) if fence is None else None
        if match:
            headings.append((number, len(match[1]), _normalized(match[2])))
    return headings


def _file(path: Path, limit: int) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError("fichier snapshot absent, lié ou trop volumineux")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("budget snapshot dépassé")
    return raw


def inventory(workspace: Path, scope: object) -> dict[str, Any]:
    if not isinstance(scope, str) or not 1 <= len(scope) <= 280:
        raise ValueError("scope Notion relatif requis")
    rel = Path(scope)
    if rel.is_absolute() or ".." in rel.parts or not rel.parts:
        raise ValueError("scope hors workspace")
    current = workspace
    for part in rel.parts:
        current = current / part
        if current.is_symlink() or not current.is_dir():
            raise ValueError("scope Notion lié ou absent")
    if not current.resolve().is_relative_to(workspace.resolve()):
        raise ValueError("scope hors workspace")
    manifest = current / ".source-provenance.json"
    manifest_bytes = _file(manifest, 64_000)
    provenance = json.loads(manifest_bytes)
    if not isinstance(provenance, dict):
        raise ValueError("provenance invalide")
    if (
        provenance.get("provider") != "notion"
        or provenance.get("classification") != "private_local_only"
        or provenance.get("read_only") is not True
        or provenance.get("attachments") != "excluded"
    ):
        raise ValueError("snapshot Notion privé importé requis")
    pages = provenance.get("pages")
    if (
        not isinstance(pages, list) or not 1 <= len(pages) <= MAX_PAGES
        or provenance.get("page_count") != len(pages)
    ):
        raise ValueError("inventaire de pages invalide")
    ids: set[str] = set()
    titles: dict[str, list[str]] = defaultdict(list)
    rows: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    heading_locations: dict[str, list[dict[str, Any]]] = defaultdict(list)
    install_locations: list[dict[str, Any]] = []
    budget = MAX_BYTES
    for page in pages:
        if not isinstance(page, dict):
            raise ValueError("page invalide")
        ident, title = page.get("id"), page.get("title")
        if (
            not isinstance(ident, str) or not ID.fullmatch(ident) or ident in ids
            or not isinstance(title, str) or not title.strip()
        ):
            raise ValueError("identifiant ou titre de page invalide")
        ids.add(ident)
        titles[_normalized(title)].append(ident)
        raw = _file(current / f"page-{ident}.md", min(budget, 1_000_000))
        budget -= len(raw)
        headings = _headings(raw.decode("utf-8"))
        if not headings or headings[0] != (1, 1, _normalized(title)):
            raise ValueError("titre de snapshot divergent")
        local: dict[str, list[int]] = defaultdict(list)
        for number, _, heading in headings[1:]:
            loc = {"page_id": ident, "line": number}
            local[heading].append(number)
            heading_locations[heading].append(loc)
            if heading == "installation des outils":
                install_locations.append(loc)
        for lines in local.values():
            if len(lines) > 1:
                findings.append({"kind": "REPEATED_HEADING", "page_id": ident,
                                 "lines": lines[:20]})
        rows.append({"page_id": ident, "sha256": hashlib.sha256(raw).hexdigest(),
                     "bytes": len(raw), "headings": len(headings) - 1})
    if provenance.get("root_page") not in ids:
        raise ValueError("racine de snapshot absente")
    for group in titles.values():
        if len(group) > 1:
            findings.append({"kind": "REPEATED_PAGE_TITLE", "page_ids": group})
    for locations in heading_locations.values():
        if len({loc["page_id"] for loc in locations}) > 1:
            findings.append({"kind": "CROSS_PAGE_HEADING", "locations": locations[:10]})
    return {
        "assessment": "INVENTORY_REVIEW_REQUIRED",
        "snapshot_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "pages": rows,
        "spaces_title_present": {space: space in titles for space in SPACES},
        "installation_locations": install_locations[:20],
        "findings": findings[:MAX_FINDINGS],
        "finding_count": len(findings),
        "truncated": len(findings) > MAX_FINDINGS,
        "scope": "snapshot Markdown importé, pas le wiki vivant",
        "limitations": [
            "Titres identiques = pistes de revue, pas doublons sémantiques prouvés.",
            "Bases, vues, propriétés, médias et hiérarchie native non contrôlés.",
            "Ne jamais archiver, déplacer, supprimer ou valider sur ce seul rapport.",
        ],
        "remote_read": False,
        "remote_write": False,
        "native_render_verified": False,
    }


def studio_check(content: object) -> dict[str, Any]:
    if not isinstance(content, str):
        raise ValueError("spécification Notion JSON texte requise")
    spec = en.parse(content)
    issues = en.inspect(content, preserve_installation=True)
    titles = [_normalized(page["title"]) for page in spec["pages"]]
    missing = [space for space in SPACES if space not in titles]
    if missing:
        issues.append("Espaces de référence absents : " + ", ".join(missing))
    if spec["tracker"] is None and "curriculum" not in spec:
        issues.append("Prévoir un suivi unique ; ne pas inventer de progression.")
    return {
        "assessment": "REVISE_STRUCTURE" if issues else "STRUCTURE_REVIEW_REQUIRED",
        "spec_sha256": hashlib.sha256(content.encode()).hexdigest(),
        "pages": len(spec["pages"]) + 1,
        "issues": issues,
        "compiler_valid": True,
        "remote_write": False,
        "native_render_verified": False,
        "note": "Prévalidation du studio ; ni plan approuvé, ni wiki créé, ni qualité certifiée.",
    }
