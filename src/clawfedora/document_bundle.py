"""Deterministic, offline export of reviewed Markdown sections.

A human-only CLI: no agent tool, no network, no shell execution. Outputs
remain bounded by the existing Markdown export contract (60,000 bytes).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import tempfile
from pathlib import Path
from typing import Any

from clawfedora.document_exports import export

MAX_PARTS = 16
MAX_PART_BYTES = 12_000
MAX_COMBINED_BYTES = 60_000
_NAME = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}")


def _regular_private_source(path: Path) -> str:
    # Prevent traversing user-supplied symlinks. No referenced files are fetched.
    if path.suffix.lower() != ".md" or not path.is_file():
        raise ValueError("section Markdown .md régulière requise")
    for segment in (path, *path.parents):
        if segment.is_symlink():
            raise ValueError("lien symbolique dans le chemin d'une section")
    mode = path.stat().st_mode
    if not stat.S_ISREG(mode) or path.stat().st_size > MAX_PART_BYTES:
        raise ValueError("section absente, non régulière ou dépassant 12 000 octets")
    try:
        value = path.read_text(encoding="utf-8", errors="strict")
    except UnicodeError as exc:
        raise ValueError("Markdown non UTF-8") from exc
    if not value.strip() or "\x00" in value or len(value.encode()) > MAX_PART_BYTES:
        raise ValueError("section Markdown vide, binaire ou trop grande")
    return value.rstrip()


def assemble(parts: list[Path]) -> tuple[str, list[dict[str, str]]]:
    if not 1 <= len(parts) <= MAX_PARTS:
        raise ValueError("entre 1 et 16 sections Markdown requises")
    if len({str(p.absolute()) for p in parts}) != len(parts):
        raise ValueError("section Markdown répétée")
    chunks: list[str] = []
    sources: list[dict[str, str]] = []
    for part in parts:
        text = _regular_private_source(part)
        chunks.append(text)
        sources.append({
            "name": part.name,
            "sha256": hashlib.sha256(part.read_bytes()).hexdigest(),
        })
    joined = "\n\n---\n\n".join(chunks) + "\n"
    if len(joined.encode()) > MAX_COMBINED_BYTES:
        raise ValueError("document combiné au-delà de 60 000 octets")
    return joined, sources


def _destination(directory: Path, name: str) -> Path:
    if not _NAME.fullmatch(name):
        raise ValueError("nom d'export invalide")
    if not directory.is_dir():
        raise ValueError("dossier de destination existant requis")
    for parent in (directory, *directory.parents):
        if parent.is_symlink():
            raise ValueError("destination liée interdite")
    if not stat.S_ISDIR(directory.stat().st_mode):
        raise ValueError("destination non régulière")
    return directory


def build_bundle(parts: list[Path], dest: Path, name: str, *, apply: bool = False) -> dict[str, Any]:
    destination = _destination(dest, name)
    source, sources = assemble(parts)
    result = {
        f"{name}.md": source.encode("utf-8"),
        f"{name}.pdf": export(source, "pdf"),
        f"{name}.docx": export(source, "docx"),
    }
    hashes = {file: hashlib.sha256(data).hexdigest() for file, data in result.items()}
    manifest: dict[str, Any] = {
        "schema_version": "1.0.0",
        "name": name,
        "sources": sources,
        "exports": hashes,
        "provenance": "offline-reviewed-markdown-sections",
        "scope": "not-proof-of-technical-correctness",
    }
    result[f"{name}.manifest.json"] = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    # Fail before writing a byte if even one target exists or is a link.
    if any((destination / fname).exists() or (destination / fname).is_symlink()
           for fname in result):
        raise ValueError("un fichier de destination existe déjà : export non modifié")
    if not apply:
        return {"dry_run": True, **manifest, "files": sorted(result)}
    staged: list[Path] = []
    written: list[Path] = []
    try:
        for _fname, data in result.items():
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=destination, prefix=".clawfedora-bundle-",
                delete=False,
            ) as handle:
                temp = Path(handle.name)
                staged.append(temp)
                os.fchmod(handle.fileno(), 0o600)
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        for (fname, _data), temp in zip(result.items(), staged, strict=True):
            target = destination / fname
            # Hardlink creation is no-clobber (unlike os.replace).
            os.link(temp, target, follow_symlinks=False)
            written.append(target)
    except OSError:
        for created in written:
            created.unlink(missing_ok=True)
        raise
    finally:
        for temp in staged:
            temp.unlink(missing_ok=True)
    return {"dry_run": False, **manifest, "files": sorted(result)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assembler des sections Markdown validées")
    parser.add_argument("--part", type=Path, action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = build_bundle(args.part, args.output_dir, args.name, apply=args.apply)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"EXPORT_REFUSED: {exc}\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
