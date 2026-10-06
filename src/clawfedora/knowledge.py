"""Bounded project retrieval on the CPU; no embeddings or external service."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
import uuid
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from clawfedora.core_config import core_contract
from clawfedora.project_common import assert_no_symlinks, now, read_json, sha256_file, write_json
from clawfedora.project_intake import _format_kind, validate_input_integrity


def _policy(repo_root: Path) -> dict[str, Any]:
    return core_contract(repo_root, "knowledge_policy.yaml")


def _database(project: Path) -> Path:
    path = project / "context/knowledge/search.sqlite"
    assert_no_symlinks(project / "context/knowledge", label="index documentaire")
    return path


def store_note(
    repo_root: Path,
    project: Path,
    title: str,
    text: str,
    *,
    kind: str = "decision",
    sources: list[dict[str, str]] | None = None,
) -> Path:
    policy = _policy(repo_root)
    sources = sources or []
    if kind not in {"decision", "research"} or not title.strip() or len(title) > 200:
        raise ValueError("note: titre ou type invalide")
    if not text.strip() or len(text) > int(policy["notes"]["max_chars"]):
        raise ValueError("note: texte vide ou trop long")
    if len(sources) > int(policy["notes"]["max_sources"]):
        raise ValueError("note: trop de sources")
    if kind == "research" and not sources:
        raise ValueError("recherche: sources datées requises")
    for source in sources:
        if set(source) != {"url", "accessed_at"}:
            raise ValueError("source: url et accessed_at requis")
        url = urlsplit(source["url"])
        if url.scheme not in {"https", "http"} or not url.hostname or url.username:
            raise ValueError("source: URL invalide")
        stamp = datetime.fromisoformat(source["accessed_at"])
        if stamp.tzinfo is None or stamp > datetime.now(UTC):
            raise ValueError("source: date passée avec fuseau requise")
    _database(project)
    expiry = None
    if kind == "research":
        oldest = min(datetime.fromisoformat(s["accessed_at"]) for s in sources)
        expiry = (oldest + timedelta(hours=int(policy["notes"]["research_ttl_hours"]))).isoformat()
    path = project / "context/knowledge/notes" / f"{uuid.uuid4()}.json"
    write_json(
        path,
        {
            "title": title.strip(),
            "text": text.strip(),
            "kind": kind,
            "origin": "human" if kind == "decision" else "untrusted",
            "observed_at": now(),
            "expires_at": expiry,
            "sources": sources,
        },
    )
    return path


def _extract(source: Path, kind: str, limits: dict[str, Any]) -> str:
    if kind == "text":
        return source.read_text(encoding="utf-8", errors="replace")[: int(limits["max_text_chars"])]
    if kind == "pdf":
        converter = shutil.which("pdftotext")
        if not converter:
            raise ValueError("PDF: installer poppler-utils pour la recherche textuelle")
        result = subprocess.run(
            [converter, "-f", "1", "-l", str(limits["pdf_max_pages"]), "-layout", str(source), "-"],
            capture_output=True,
            text=True,
            check=False,
            timeout=int(limits["pdf_timeout_seconds"]),
        )
        if result.returncode or not result.stdout.strip():
            raise ValueError("PDF: texte indisponible; lecture visuelle/OCR nécessaire")
        return result.stdout[: int(limits["max_text_chars"])]
    raise ValueError("format sans représentation textuelle")


def _documents(project: Path, repo_root: Path) -> list[tuple[Path, str, dict[str, Any]]]:
    documents: list[tuple[Path, str, dict[str, Any]]] = []
    formats = core_contract(repo_root, "document_ingestion_policy.yaml")
    index = project / "context/ingestion/index.json"
    for entry in read_json(index).get("documents", []) if index.is_file() else []:
        relative = Path(str(entry["path"]))
        if relative.is_absolute() or ".." in relative.parts or relative.parts[0] != "intake":
            raise ValueError("index: source hors intake")
        source = project / relative
        if sha256_file(source) != entry["sha256"]:
            raise ValueError("index: identité documentaire divergente")
        if not re.fullmatch(r"doc-\d+-[a-f0-9]{12}", str(entry["document_id"])):
            raise ValueError("index: identifiant documentaire invalide")
        representation = project / "context/ingestion" / str(entry["document_id"]) / "extracted.txt"
        if representation.is_file():
            documents.append(
                (representation, "text", {"path": relative.as_posix(), "kind": entry["kind"]})
            )
        else:
            documents.append(
                (source, str(entry["kind"]), {"path": relative.as_posix(), "kind": entry["kind"]})
            )
    for source in sorted((project / "sources").rglob("*")):
        if source.is_file():
            kind, _ = _format_kind(source, formats)
            documents.append((source, kind, {"path": source.relative_to(project).as_posix()}))
    for source in sorted((project / "context/knowledge/notes").glob("*.json")):
        note = read_json(source)
        documents.append((source, "note", {**note, "path": source.relative_to(project).as_posix()}))
    return documents


def build_index(repo_root: Path, project: Path) -> dict[str, Any]:
    if validate_input_integrity(project):
        raise ValueError("index: intégrité des entrées invalide")
    assert_no_symlinks(project, label="projet à indexer")
    limits = dict(_policy(repo_root)["limits"])
    path = _database(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    skipped: list[dict[str, str]] = []
    changed, total, chunks = 0, 0, 0
    with closing(sqlite3.connect(path, timeout=5)) as db, db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS documents "
            "(path TEXT PRIMARY KEY, digest TEXT, chars INTEGER DEFAULT 0)"
        )
        if "chars" not in {row[1] for row in db.execute("PRAGMA table_info(documents)")}:
            db.execute("ALTER TABLE documents ADD COLUMN chars INTEGER DEFAULT 0")
        db.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5("
            "text, path UNINDEXED, page UNINDEXED, line UNINDEXED, metadata UNINDEXED)"
        )
        seen: set[str] = set()
        for number, (source, kind, metadata) in enumerate(_documents(project, repo_root)):
            relative = str(metadata["path"])
            if number >= int(limits["max_documents"]) or source.stat().st_size > int(
                limits["max_file_bytes"]
            ):
                skipped.append({"path": relative, "reason": "limite documentaire"})
                continue
            digest = hashlib.sha256(
                (
                    sha256_file(source)
                    + json.dumps(limits, sort_keys=True)
                    + json.dumps(metadata, sort_keys=True)
                    + "fts-v2"
                ).encode()
            ).hexdigest()
            previous = db.execute(
                "SELECT digest,chars FROM documents WHERE path=?", (relative,)
            ).fetchone()
            if previous and previous[0] == digest and previous[1] > 0:
                count = db.execute(
                    "SELECT count(*) FROM chunks WHERE path=?", (relative,)
                ).fetchone()[0]
                size = previous[1]
                if chunks + count <= int(limits["max_chunks"]) and total + size <= int(
                    limits["max_total_chars"]
                ):
                    chunks += count
                    total += size
                    seen.add(relative)
                    continue
            try:
                text = (
                    (str(metadata["title"]) + "\n" + str(metadata["text"]))
                    if kind == "note"
                    else _extract(source, kind, limits)
                )
            except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
                skipped.append({"path": relative, "reason": str(exc)})
                continue
            if not text.strip() or total + len(text) > int(limits["max_total_chars"]):
                skipped.append({"path": relative, "reason": "texte vide ou budget total atteint"})
                continue
            total += len(text)
            citation = {key: value for key, value in metadata.items() if key != "text"}
            rows: list[tuple[str, str, int, int, str]] = []
            chunk_size, overlap = int(limits["chunk_chars"]), int(limits["overlap_chars"])
            for page, content in enumerate(text.split("\f"), 1):
                line, previous_start = 1, 0
                for start in range(0, len(content), chunk_size - overlap):
                    line += content.count("\n", previous_start, start)
                    previous_start = start
                    rows.append(
                        (
                            content[start : start + chunk_size],
                            relative,
                            page,
                            line,
                            json.dumps(citation),
                        )
                    )
            if chunks + len(rows) > int(limits["max_chunks"]):
                skipped.append({"path": relative, "reason": "budget de passages atteint"})
                continue
            chunks += len(rows)
            seen.add(relative)
            db.execute("DELETE FROM chunks WHERE path=?", (relative,))
            db.executemany("INSERT INTO chunks(text,path,page,line,metadata) VALUES(?,?,?,?,?)", rows)
            db.execute(
                "INSERT OR REPLACE INTO documents VALUES(?,?,?)", (relative, digest, len(text))
            )
            changed += 1
        for (relative,) in db.execute("SELECT path FROM documents").fetchall():
            if relative not in seen:
                db.execute("DELETE FROM chunks WHERE path=?", (relative,))
                db.execute("DELETE FROM documents WHERE path=?", (relative,))
    report = {
        "indexed_at": now(),
        "documents": len(seen),
        "chunks": chunks,
        "changed": changed,
        "skipped": skipped,
        "backend": "sqlite-fts5",
        "limitations": "Recherche textuelle; PDF limité à 20 pages, sans OCR. "
        "Ne remplace pas la couverture d’analyse.",
    }
    write_json(path.parent / "index-status.json", report)
    return report


def search(repo_root: Path, project: Path, query: str) -> list[dict[str, Any]]:
    path = _database(project)
    if not path.is_file():
        return []
    limits = _policy(repo_root)["limits"]
    # Treat query syntax as words, never as SQL or FTS operators.
    stop = {"les", "des", "une", "pour", "dans", "avec", "sur", "que", "qui", "the", "and"}
    terms = [
        word
        for word in re.findall(r"[^\W_]+", query[:2000].casefold())
        if len(word) > 2 and word not in stop
    ][:12]
    if not terms:
        return []
    match = " OR ".join('"' + term + '"' for term in terms)
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2)) as db:
        rows = db.execute(
            "SELECT text,path,page,line,metadata FROM chunks WHERE chunks MATCH ? "
            "ORDER BY bm25(chunks), path, page, line LIMIT ?",
            (match, int(limits["max_results"])),
        ).fetchall()
    hits: list[dict[str, Any]] = []
    remaining = int(limits["max_result_chars"])
    for text, relative, page, line, raw in rows:
        metadata = json.loads(raw)
        expiry = metadata.get("expires_at")
        stale = bool(expiry and datetime.fromisoformat(expiry) < datetime.now(UTC))
        excerpt = str(text)[:remaining]
        if not excerpt:
            break
        remaining -= len(excerpt)
        hits.append(
            {
                "path": relative,
                "page": page,
                "line": line,
                "text": excerpt,
                "kind": metadata.get("kind", "source"),
                "title": metadata.get("title", ""),
                "stale": stale,
                "sources": metadata.get("sources", []),
            }
        )
    return hits
