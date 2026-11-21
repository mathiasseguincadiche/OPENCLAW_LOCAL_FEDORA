"""Read-only structural audit of a local GitHub checkout or imported source snapshot.

Does not contact GitHub, execute project code, inspect secrets, assess cloud
entitlement, claim a successful CI run or authorize changes to repositories.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from defusedxml import ElementTree as DefusedET
from defusedxml.common import DefusedXmlException

MARKDOWN_REF = re.compile(r"!?\[[^\]\n]*\]\(([^)\n]+)\)")
HTML_REF = re.compile(r'(?:src|srcset|href)="([^"]+)"')
MAX_TEXT_BYTES = 1_000_000
MAX_GRAPHICS = 250
MAX_REPORT_LINKS = 60
DOC_PAGES = (
    "README.md", "docs/README.md", "CONTRIBUTING.md",
    "SECURITY.md", "STATUS.md", "ROADMAP.md",
)
SIGNALS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("readme", ("README.md",)),
    ("documentation_index", ("docs/README.md", "docs/index.md")),
    ("architecture_reference", ("docs/architecture.md", "docs/architecture/README.md")),
    ("installation_guide", ("docs/demarrage.md", "docs/installation.md", "INSTALL.md")),
    ("project_status", ("STATUS.md",)),
    ("roadmap", ("ROADMAP.md",)),
    ("contribution_policy", ("CONTRIBUTING.md",)),
    ("security_policy", ("SECURITY.md",)),
    ("license", ("LICENSE", "LICENSE.md", "COPYING")),
    ("changelog", ("CHANGELOG.md",)),
    ("pull_request_template", (
        ".github/pull_request_template.md", ".github/PULL_REQUEST_TEMPLATE.md",
        "docs/pull_request_template.md",
    )),
    ("issue_templates", (".github/ISSUE_TEMPLATE",)),
    ("workflow_definitions", (".github/workflows",)),
    ("evidence_directory", ("evidence",)),
    ("diagrams_directory", ("docs/diagrams",)),
)
FORBIDDEN_FILES = {".env", "id_rsa", "id_ed25519"}
FORBIDDEN_SUFFIXES = (".pem", ".key", ".tfstate", ".p12", ".pfx")


class AuditError(ValueError):
    """Refusal of an unsafe or invalid local audit input."""


def _safe_path(root: Path, relative: str) -> Path | None:
    candidate = root / relative
    if candidate.is_symlink():
        return None
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        return None
    for parent in candidate.parents:
        if parent == root:
            break
        if parent.is_symlink():
            return None
    return candidate


def _read_text(root: Path, name: str) -> str | None:
    candidate = _safe_path(root, name)
    if candidate is None or not candidate.is_file():
        return None
    try:
        if candidate.stat().st_size > MAX_TEXT_BYTES:
            return None
        return candidate.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


def _source(root: Path) -> dict[str, Any]:
    manifest = _read_text(root, ".source-provenance.json")
    if manifest is None:
        return {"kind": "LOCAL_DIRECTORY", "commit": None, "coverage": "NOT_ASSESSED"}
    try:
        value: object = json.loads(manifest)
    except ValueError:
        return {"kind": "UNKNOWN_IMPORT", "commit": None, "coverage": "NOT_ASSESSED"}
    if not isinstance(value, dict) or value.get("provider") != "github":
        return {"kind": "UNKNOWN_IMPORT", "commit": None, "coverage": "NOT_ASSESSED"}
    commit = value.get("commit")
    if not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        commit = None
    return {
        "kind": "GITHUB_SOURCE_SNAPSHOT",
        "commit": commit,
        "coverage": "PARTIAL_ALLOWED_FILES_ONLY",
        "skipped_files_reported": value.get("skipped"),
        "file_count_reported": value.get("file_count"),
    }


def _references(body: str) -> list[str]:
    return (
        [match.group(1) for match in MARKDOWN_REF.finditer(body)]
        + [match.group(1) for match in HTML_REF.finditer(body)]
    )


def _local_target(value: str) -> str | None:
    item = value.strip().split(" ", 1)[0].strip("<>")
    if not item or item.startswith(("#", "mailto:", "data:", "//")):
        return None
    uri = urlsplit(item)
    if uri.scheme or uri.netloc:
        return None
    result = unquote(uri.path)
    return result or None


def audit_links(root: Path, *, snapshot: bool) -> dict[str, Any]:
    checked = 0
    missing: list[str] = []
    not_checked: list[str] = []
    inspected_pages: list[str] = []
    for name in DOC_PAGES:
        page = _read_text(root, name)
        if page is None:
            continue
        inspected_pages.append(name)
        for raw in _references(page):
            link = _local_target(raw)
            if link is None:
                continue
            checked += 1
            if checked > 4000:
                not_checked.append("link_limit_reached")
                break
            if link.startswith("/"):
                target = _safe_path(root, link.lstrip("/"))
            else:
                target = _safe_path(root, str((Path(name).parent / link)))
            label = f"{name} -> {link}"
            if target is None:
                missing.append(label)
            elif not target.exists():
                # Image assets and oversized documents are excluded from source snapshots.
                if snapshot:
                    not_checked.append(label)
                else:
                    missing.append(label)
    return {
        "pages_inspected": inspected_pages,
        "references_checked": checked,
        "missing": missing[:MAX_REPORT_LINKS],
        "missing_total": len(missing),
        "not_checked": not_checked[:MAX_REPORT_LINKS],
        "not_checked_total": len(not_checked),
        "note": "Only file existence, not anchors, live URLs or GitHub rendering",
    }


def audit_graphics(root: Path, *, snapshot: bool) -> dict[str, Any]:
    folder = _safe_path(root, "docs/diagrams")
    if folder is None or not folder.is_dir():
        return {"state": "NOT_FOUND", "svg_checked": 0, "missing_sources": [],
                "invalid_xml": [], "limits": "Directory not present in imported material"}
    svgs = sorted(folder.glob("*.svg"))
    if len(svgs) > MAX_GRAPHICS:
        return {"state": "NOT_CHECKED", "svg_checked": 0, "missing_sources": [],
                "invalid_xml": [], "limits": "Too many SVG assets for this static audit"}
    absent: list[str] = []
    invalid: list[str] = []
    verified = 0
    for svg in svgs:
        if svg.is_symlink():
            invalid.append(svg.name + ": symlink")
            continue
        source = _safe_path(root, str(svg.relative_to(root).with_suffix(".drawio")))
        if source is None or not source.is_file():
            if not snapshot:
                absent.append(svg.name + ": draw.io source missing")
        xml = _read_text(root, str(svg.relative_to(root)))
        if xml is None:
            invalid.append(svg.name + ": unreadable or oversized SVG")
            continue
        try:
            result = DefusedET.fromstring(xml)
            if result.tag != "{http://www.w3.org/2000/svg}svg":
                invalid.append(svg.name + ": incorrect root element")
            else:
                verified += 1
        except (DefusedET.ParseError, DefusedXmlException, ValueError):
            invalid.append(svg.name + ": XML invalid or unsafe")
    return {
        "state": "SOURCE_ONLY",
        "svg_checked": verified,
        "missing_sources": absent,
        "invalid_xml": invalid,
        "limits": (
            "Snapshot may exclude assets; graphic rendering is never checked"
            if snapshot else "XML validity and pairs only; no rendered visual review"
        ),
    }


def audit_repository(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_dir():
        raise AuditError("Le chemin doit être un dossier local non lié")
    root = path.resolve(strict=True)
    source = _source(root)
    snapshot = source["kind"] != "LOCAL_DIRECTORY"
    signals: list[dict[str, Any]] = []
    for key, choices in SIGNALS:
        candidates = [_safe_path(root, name) for name in choices]
        found = [
            name for name, candidate in zip(choices, candidates, strict=True)
            if candidate is not None and candidate.exists()
        ]
        signals.append({
            "id": key,
            "state": "FOUND" if found else "NOT_FOUND",
            "paths": found,
            "note": "Presence only, not a statement of technical compliance",
        })
    readme = _read_text(root, "README.md") or ""
    words = readme.casefold()
    orientation = {
        "readme_has_architecture_section": "architecture" in words,
        "readme_mentions_verification": "preuve" in words or "test" in words,
        "readme_mentions_quick_start": any(
            item in words for item in ("démarrage", "demarrage", "quick start", "getting started")
        ),
    }
    # Only names are checked. Never open the contents of potentially private files.
    sensitive: list[str] = []
    for candidate in root.iterdir():
        if candidate.is_symlink():
            continue
        name = candidate.name.casefold()
        if candidate.is_file() and (
            name in FORBIDDEN_FILES or name.endswith(FORBIDDEN_SUFFIXES)
        ):
            sensitive.append(candidate.name)
    return {
        "assessment": "READ_ONLY_DOCUMENTARY_INVENTORY_NOT_A_RUNTIME_PROOF",
        "source": source,
        "structure": signals,
        "readme_signals": orientation,
        "links": audit_links(root, snapshot=snapshot),
        "graphics": audit_graphics(root, snapshot=snapshot),
        "potentially_sensitive_root_filenames": sensitive,
        "limitations": [
            "No network access, PR publication, code execution, cloud consent or repo modification",
            "No CI status, secret content, dependency vulnerabilities or runtime deployment verified",
            "No visual browser/mobile audit; source snapshots can exclude binary images",
            "A structural document is not evidence of personal InfraOps mastery",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clawfedora-github-audit",
        description="Audit local des signaux documentaires d'un dépôt sans réseau ni écriture",
    )
    parser.add_argument(
        "--path", type=Path, required=True,
        help="Répertoire local complet ou snapshot GitHub créé par clawfedora-sources",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = audit_repository(args.path)
    except (AuditError, OSError, ValueError) as exc:
        print(json.dumps({"assessment": "REFUSED", "reason": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
