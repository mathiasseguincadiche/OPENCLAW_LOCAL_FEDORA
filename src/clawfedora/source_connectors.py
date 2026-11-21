"""Opt-in read-only GitHub/Notion snapshots for the existing immutable project intake.

Credentials remain process environment variables. Remote content is treated as untrusted
project data; importing never grants cloud consent or remote write permissions.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any, cast

from clawfedora.core_config import resolve_runtime_root
from clawfedora.project_common import now, project_path, read_json, write_json
from clawfedora.project_intake import append_intake_items
from clawfedora.project_worker import worker_lock

GITHUB_HOST = "https://api.github.com"
NOTION_HOST = "https://api.notion.com"
GITHUB_SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}\Z")
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
NOTION_ID = re.compile(r"[0-9a-f]{32}\Z")
TEXT_EXTENSIONS = frozenset({
    ".md", ".txt", ".py", ".sh", ".bash", ".tf", ".tf.json", ".yml", ".yaml",
    ".json", ".toml", ".ini", ".cfg", ".conf", ".html", ".css", ".js", ".mjs",
    ".ts", ".tsx", ".jsx", ".svg", ".drawio", ".sql", ".xml", ".j2",
})
TEXT_NAMES = frozenset({
    "dockerfile", "makefile", "jenkinsfile", "vagrantfile", "requirements.txt",
    ".gitignore", ".dockerignore", ".editorconfig", ".gitattributes",
})
FORBIDDEN = frozenset({
    ".env", ".env.local", ".env.production", ".env.development", "id_rsa",
    "id_ed25519", ".terraform", ".git", ".venv", "node_modules", "__pycache__",
})
FORBIDDEN_SUFFIX = frozenset({".key", ".pem", ".p12", ".pfx", ".jks", ".tfstate", ".tfvars"})
MAX_FILES = 240
MAX_FILE_BYTES = 1_000_000
MAX_TOTAL_BYTES = 6_000_000
MAX_PAGES = 20
MAX_DEPTH = 6
MAX_RESPONSE_BYTES = 3_000_000


class SourceImportError(ValueError):
    """A source was refused without exposing response bodies or tokens."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: urllib.request.Request, fp: Any, code: int,
        msg: str, headers: Any, newurl: str,
    ) -> None:
        raise SourceImportError("redirection distante refusée")


def _get_json(host: str, path: str, headers: dict[str, str]) -> dict[str, Any]:
    """Only caller-chosen fixed API hosts, no redirects or unbounded responses."""
    if host not in (GITHUB_HOST, NOTION_HOST) or not path.startswith("/") or "//" in path:
        raise SourceImportError("endpoint non autorisé")
    request = urllib.request.Request(host + path, headers=headers, method="GET")
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=20) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SourceImportError("API distante indisponible ou accès refusé") from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise SourceImportError("réponse API trop volumineuse")
    try:
        payload: object = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise SourceImportError("réponse JSON distante invalide") from exc
    if not isinstance(payload, dict):
        raise SourceImportError("réponse API non structurée")
    return cast(dict[str, Any], payload)


def _github(path: str) -> dict[str, Any]:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "clawfedora-sources/0.2",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return _get_json(GITHUB_HOST, path, headers)


def _notion(path: str) -> dict[str, Any]:
    token = os.environ.get("NOTION_API_TOKEN", "").strip()
    if not token:
        raise SourceImportError("NOTION_API_TOKEN absent (ne pas placer le token dans la CLI)")
    return _get_json(NOTION_HOST, path, {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Accept": "application/json",
        "User-Agent": "clawfedora-sources/0.2",
    })


def _safe_repo(value: str) -> str:
    if not GITHUB_SLUG.fullmatch(value) or ".." in value or value.endswith("."):
        raise SourceImportError("dépôt GitHub attendu : propriétaire/nom")
    return value


def _safe_sha(value: str) -> str:
    if not SHA40.fullmatch(value):
        raise SourceImportError("SHA Git complet de 40 caractères hexadécimaux requis")
    return value


def _safe_page(value: str) -> str:
    candidate = value.strip().lower().replace("-", "")
    if not NOTION_ID.fullmatch(candidate):
        raise SourceImportError("identifiant Notion de 32 chiffres hexadécimaux requis")
    return candidate


def _safe_path(value: str) -> PurePosixPath:
    if (
        not value or value.startswith("/") or "\\" in value
        or any(part in ("", ".", "..") for part in value.split("/"))
    ):
        raise SourceImportError("chemin GitHub non sûr")
    rel = PurePosixPath(value)
    if len(rel.parts) > 15 or any(
        part.casefold() in FORBIDDEN or part.startswith(".env")
        or part.casefold().endswith((".tfstate", ".tfvars"))
        or part.casefold() == ".ssh"
        for part in rel.parts
    ):
        raise SourceImportError("fichier ou dossier confidentiel exclu")
    if rel.suffix.casefold() in FORBIDDEN_SUFFIX:
        raise SourceImportError("fichier sensible exclu")
    return rel


def _is_text(rel: PurePosixPath) -> bool:
    name = rel.name.casefold()
    if name in TEXT_NAMES or name.startswith("dockerfile."):
        return True
    return rel.suffix.casefold() in TEXT_EXTENSIONS or name.endswith(".tf.json")


def _write_text(dest: Path, relative: PurePosixPath, content: bytes) -> None:
    if len(content) > MAX_FILE_BYTES or b"\x00" in content:
        raise SourceImportError("fichier distant trop volumineux ou non textuel")
    try:
        content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SourceImportError("fichier distant non UTF-8") from exc
    target = dest.joinpath(*relative.parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)


def _github_snapshot(dest: Path, repo: str, commit: str) -> dict[str, Any]:
    repo, commit = _safe_repo(repo), _safe_sha(commit)
    quoted = "/".join(urllib.parse.quote(part, safe="") for part in repo.split("/"))
    record = _github(f"/repos/{quoted}/commits/{commit}")
    if record.get("sha") != commit:
        raise SourceImportError("GitHub n'a pas retourné le commit exact demandé")
    tree = record.get("commit", {}).get("tree", {}).get("sha")
    if not isinstance(tree, str) or not SHA40.fullmatch(tree):
        raise SourceImportError("arbre Git introuvable")
    data = _github(f"/repos/{quoted}/git/trees/{tree}?recursive=1")
    if data.get("truncated") is not False:
        raise SourceImportError("arbre incomplet : importation refusée")
    entries = data.get("tree")
    if not isinstance(entries, list):
        raise SourceImportError("inventaire GitHub invalide")
    selected: list[tuple[PurePosixPath, str, int]] = []
    skipped = 0
    total = 0
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("type") != "blob":
            continue
        path = entry.get("path")
        if not isinstance(path, str):
            raise SourceImportError("chemin GitHub manquant")
        try:
            rel = _safe_path(path)
        except SourceImportError:
            skipped += 1
            continue
        if not _is_text(rel):
            skipped += 1
            continue
        if entry.get("mode") not in ("100644", "100755"):
            raise SourceImportError("lien ou type Git non supporté")
        sha, size = entry.get("sha"), entry.get("size")
        if not isinstance(sha, str) or not SHA40.fullmatch(sha) or type(size) is not int:
            raise SourceImportError("métadonnées blob invalides")
        if size > MAX_FILE_BYTES:
            skipped += 1
            continue
        total += size
        selected.append((rel, sha, size))
        if len(selected) > MAX_FILES or total > MAX_TOTAL_BYTES:
            raise SourceImportError("dépôt trop volumineux : réduire le périmètre")
    if not selected:
        raise SourceImportError("aucun fichier texte admissible")
    for rel, sha, expected_size in selected:
        blob = _github(f"/repos/{quoted}/git/blobs/{sha}")
        if blob.get("encoding") != "base64" or not isinstance(blob.get("content"), str):
            raise SourceImportError("blob GitHub non décodable")
        try:
            raw = base64.b64decode("".join(blob["content"].split()), validate=True)
        except (ValueError, binascii.Error) as exc:
            raise SourceImportError("blob GitHub encodé invalide") from exc
        if len(raw) != expected_size:
            raise SourceImportError("taille du blob différente de l'inventaire")
        _write_text(dest, rel, raw)
    return {
        "provider": "github", "repository": repo, "commit": commit, "tree": tree,
        "file_count": len(selected), "skipped": skipped, "captured_at": now(),
        "read_only": True,
    }


def _rich(block: dict[str, Any]) -> str:
    raw = block.get("rich_text", [])
    if not isinstance(raw, list):
        return ""
    return "".join(
        str(item.get("plain_text", ""))
        for item in raw if isinstance(item, dict)
    )


def _notion_title(page: dict[str, Any]) -> str:
    props = page.get("properties")
    if isinstance(props, dict):
        for item in props.values():
            if isinstance(item, dict) and item.get("type") == "title":
                return _rich({"rich_text": item.get("title", [])})
    return "Page Notion sans titre"


def _notion_children(identifier: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    cursor: str | None = None
    for _ in range(10):
        query = "?page_size=100" + (
            "&start_cursor=" + urllib.parse.quote(cursor, safe="") if cursor else ""
        )
        data = _notion(f"/v1/blocks/{identifier}/children{query}")
        entries = data.get("results")
        if not isinstance(entries, list):
            raise SourceImportError("blocs Notion invalides")
        result.extend(item for item in entries if isinstance(item, dict))
        if not data.get("has_more"):
            return result
        cursor = data.get("next_cursor")
        if not isinstance(cursor, str) or not cursor or len(cursor) > 200:
            raise SourceImportError("pagination Notion invalide")
    raise SourceImportError("pagination Notion trop longue")


def _notion_lines(
    identifier: str, *, depth: int, include_pages: bool, todo: list[str],
    seen_blocks: set[str],
) -> list[str]:
    if depth > MAX_DEPTH:
        raise SourceImportError("imbrication des blocs Notion trop profonde")
    result: list[str] = []
    for block in _notion_children(identifier):
        block_id, kind = block.get("id"), block.get("type")
        if not isinstance(block_id, str) or not isinstance(kind, str):
            raise SourceImportError("identifiant bloc Notion manquant")
        if block_id in seen_blocks:
            raise SourceImportError("bloc Notion répété")
        seen_blocks.add(block_id)
        payload = block.get(kind, {})
        if not isinstance(payload, dict):
            payload = {}
        label = _rich(payload).replace("\r", "")
        if kind == "child_page":
            title = str(payload.get("title", "Page"))
            result.append(f"Page fille : {title} (ID {block_id})")
            if include_pages:
                todo.append(_safe_page(block_id))
        elif kind.startswith("heading_"):
            level = int(kind[-1])
            result.append("#" * level + " " + label)
        elif kind == "code":
            language = re.sub(r"[^a-z0-9_+-]", "", str(payload.get("language", "text")).lower())
            result.extend([f"```{language}", label, "```"])
        elif kind in ("bulleted_list_item", "numbered_list_item"):
            result.append(("- " if kind.startswith("bulleted") else "1. ") + label)
        elif kind == "quote":
            result.append("> " + label)
        elif kind == "table_row":
            cells = payload.get("cells", [])
            if isinstance(cells, list):
                result.append(" | ".join(
                    _rich({"rich_text": cell}) for cell in cells if isinstance(cell, list)
                ))
        elif kind in ("paragraph", "callout", "toggle", "to_do"):
            result.append(label)
        elif kind in ("image", "file", "pdf", "video", "embed"):
            result.append(f"[{kind} : pièce jointe non importée]")
        if block.get("has_children") and kind != "child_page":
            result.extend(_notion_lines(
                block_id, depth=depth + 1, include_pages=include_pages,
                todo=todo, seen_blocks=seen_blocks,
            ))
    return [line for line in result if line.strip()]


def _notion_snapshot(dest: Path, page_id: str, include_children: bool) -> dict[str, Any]:
    page_id = _safe_page(page_id)
    todo = [page_id]
    done: set[str] = set()
    pages: list[dict[str, str]] = []
    total_bytes = 0
    while todo:
        identifier = todo.pop(0)
        if identifier in done:
            continue
        if len(done) >= MAX_PAGES:
            raise SourceImportError("trop de pages Notion : limiter l'importation")
        done.add(identifier)
        page = _notion(f"/v1/pages/{identifier}")
        returned = _safe_page(str(page.get("id", "")))
        if returned != identifier:
            raise SourceImportError("Notion n'a pas retourné la page demandée")
        lines = _notion_lines(
            identifier, depth=0, include_pages=include_children, todo=todo,
            seen_blocks=set(),
        )
        title = _notion_title(page)
        body = (
            "# " + title + "\n\n" + f"Page : {identifier}\n"
            + "Source externe non fiable, à vérifier avant toute décision.\n\n"
            + "\n\n".join(lines) + "\n"
        ).encode("utf-8")
        total_bytes += len(body)
        if total_bytes > MAX_TOTAL_BYTES:
            raise SourceImportError("contenu Notion trop volumineux")
        _write_text(dest, PurePosixPath(f"page-{identifier}.md"), body)
        pages.append({"id": identifier, "title": title})
    return {
        "provider": "notion", "root_page": page_id, "page_count": len(pages),
        "pages": pages, "captured_at": now(), "read_only": True,
        "classification": "private_local_only",
        "attachments": "excluded",
    }


def _local_only(project: Path) -> bool:
    path = project / "context" / "connected_sources.json"
    if path.is_symlink():
        raise SourceImportError("politique de sources liée interdite")
    if path.is_file() and read_json(path).get("local_only") is True:
        return True
    return any((project / folder).glob("Notion-*") for folder in ("intake", "sources"))


def import_snapshot(
    repo_root: Path, runtime: Path, project_id: str, *,
    github: str | None = None, commit: str | None = None,
    notion_page: str | None = None, include_children: bool = False,
) -> dict[str, Any]:
    """Download one explicitly chosen immutable snapshot into an INTAKE_READY project."""
    if (github is None) == (notion_page is None):
        raise SourceImportError("choisir exactement GitHub ou Notion")
    if github is not None:
        _safe_repo(github)
        if commit is None:
            raise SourceImportError("--commit requis pour un dépôt GitHub")
        _safe_sha(commit)
    if notion_page is not None:
        _safe_page(notion_page)
        if commit is not None:
            raise SourceImportError("--commit réservé à GitHub")
    from clawfedora.project_cloud import consent_path

    with worker_lock(runtime, allow_gaming=True):
        project = project_path(runtime, project_id)
        if read_json(project / "project.json").get("status") != "INTAKE_READY":
            raise SourceImportError("sources figées : créer un nouveau projet ou repartir du début")
        if consent_path(runtime, project).exists():
            raise SourceImportError("révoquer l'accord cloud avant d'importer de nouvelles sources")
        slug = "GitHub-" + github.replace("/", "-") + "-" + commit[:12] if github else (
            "Notion-" + _safe_page(notion_page or "")
        )
        if (project / "intake" / slug).exists():
            raise SourceImportError("snapshot déjà présent dans le projet")
        with tempfile.TemporaryDirectory(prefix="clawfedora-source-") as folder:
            snapshot = Path(folder) / slug
            snapshot.mkdir()
            if github is not None and commit is not None:
                manifest = _github_snapshot(snapshot, github, commit)
            else:
                manifest = _notion_snapshot(snapshot, notion_page or "", include_children)
            write_json(snapshot / ".source-provenance.json", manifest)
            if notion_page is not None:
                # Fail closed BEFORE intake changes: no approval can enable cloud
                # for a project containing private training notes.
                policy_path = project / "context" / "connected_sources.json"
                old = read_json(policy_path) if policy_path.is_file() else {}
                old["local_only"] = True
                old["reason"] = "notes Notion personnelles : cloud interdit"
                write_json(policy_path, old)
                policy_path.chmod(0o600)
            append_intake_items(repo_root, runtime, project, [snapshot])
            return {"status": "IMPORTED", "source": manifest, "local_only": _local_only(project)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clawfedora-sources",
        description="Importer des snapshots GitHub/Notion vérifiables, sans écriture distante",
    )
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--project-id", required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--github", help="propriétaire/dépôt")
    source.add_argument("--notion-page", help="ID hexadécimal 32 caractères de la page Notion")
    parser.add_argument("--commit", help="SHA GitHub complet et immuable")
    parser.add_argument("--include-children", action="store_true")
    parser.add_argument("--apply", action="store_true", help="lancer la lecture distante")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.github:
            _safe_repo(args.github)
            if args.commit is None:
                raise SourceImportError("--commit requis")
            _safe_sha(args.commit)
            if args.include_children:
                raise SourceImportError("--include-children réservé à Notion")
        elif args.notion_page:
            _safe_page(args.notion_page)
            if args.commit:
                raise SourceImportError("--commit réservé à GitHub")
        if not args.apply:
            print(json.dumps({
                "status": "PLAN_ONLY", "project_id": args.project_id,
                "github": args.github, "commit": args.commit,
                "notion_page": args.notion_page,
                "include_children": args.include_children,
                "remote_writes": False, "notion_local_only": bool(args.notion_page),
            }, ensure_ascii=False))
            return 0
        runtime = resolve_runtime_root(str(args.runtime_root) if args.runtime_root else None)
        result = import_snapshot(
            args.root, runtime, args.project_id, github=args.github, commit=args.commit,
            notion_page=args.notion_page, include_children=bool(args.include_children),
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (SourceImportError, ValueError, OSError) as exc:
        # Never print remote response bodies, URLs with secrets or local token values.
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
