from __future__ import annotations

import os
import re
import shutil
import stat
import zipfile
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import Any
from xml.etree import ElementTree

from clawfedora.core_config import core_contract
from clawfedora.project_common import (
    aggregate_records,
    assert_no_symlinks,
    chmod_read_only_files,
    mime_type,
    now,
    project_path,
    read_json,
    sha256_file,
    validate_project_id,
    write_json,
)

PROJECT_DIRS = (
    "intake",
    "sources",
    "context",
    "work",
    "deliverables",
    "evidence",
    "diagrams",
)
_BLOCKED_NAMES = {".env", ".env.local", ".env.production", "id_rsa", "id_ed25519"}
_BLOCKED_SUFFIXES = {".key", ".p12", ".pfx", ".jks"}
_SPECIAL_TEXT_NAMES = {"dockerfile", "makefile", "jenkinsfile", "vagrantfile"}
_SECRET_PATTERNS = (
    re.compile(r"sk-or-(?:v1-)?[A-Za-z0-9_-]{12,}"),
    re.compile(r"(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})"),
    re.compile(r"glpat-[A-Za-z0-9_-]{12,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"),
)


def _files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    return sorted(path for path in root.rglob("*") if path.is_file())


def _validate_source(path: Path, *, label: str) -> Path:
    raw = path.expanduser()
    if raw.is_symlink():
        raise ValueError(f"{label}: lien symbolique racine interdit: {path}")
    source = raw.resolve(strict=True)
    if not source.is_file() and not source.is_dir():
        raise ValueError(f"{label}: type de source non supporté: {source}")
    assert_no_symlinks(source, label=label)
    for item in _files(source):
        if item.name.casefold() in _BLOCKED_NAMES or item.suffix.casefold() in _BLOCKED_SUFFIXES:
            raise ValueError(f"{label}: fichier secret potentiel interdit: {item.name}")
        with item.open("rb") as handle:
            head = handle.read(4096)
        if b"\x00" in head:
            continue
        with item.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if any(pattern.search(line) for pattern in _SECRET_PATTERNS):
                    raise ValueError(f"{label}: secret potentiel détecté: {item.name}")
    return source


def _size(source: Path) -> int:
    return sum(path.stat().st_size for path in _files(source))


def _copy(source: Path, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError(destination)
    if source.is_dir():
        shutil.copytree(source, destination, symlinks=False)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def _copy_inputs(
    items: Iterable[Path],
    destination: Path,
    *,
    label: str,
    max_file: int,
    max_total: int,
) -> list[str]:
    copied: list[str] = []
    total = 0
    seen: set[str] = set()
    for item in items:
        source = _validate_source(item, label=label)
        if source.name in seen:
            raise ValueError(f"{label}: nom dupliqué: {source.name}")
        seen.add(source.name)
        source_size = _size(source)
        total += source_size
        if any(path.stat().st_size > max_file for path in _files(source)):
            raise ValueError(f"{label}: fichier supérieur à la limite: {source.name}")
        if total > max_total:
            raise ValueError(f"{label}: taille totale supérieure à la limite")
        _copy(source, destination / source.name)
        copied.append(source.name)
    return copied


def _inventory(root: Path) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    if root.exists():
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            relative = path.relative_to(root).as_posix()
            records.append(
                {
                    "path": relative,
                    "sha256": sha256_file(path),
                    "size": path.stat().st_size,
                    "mime": mime_type(path),
                }
            )
    return {
        "schema_version": "1.0.0",
        "generated_at": now(),
        "file_count": len(records),
        "aggregate_sha256": aggregate_records(records),
        "files": records,
    }


def validate_input_integrity(project: Path) -> list[str]:
    failures: list[str] = []
    for label in ("intake", "sources"):
        root = project / label
        try:
            assert_no_symlinks(root, label=label)
        except ValueError as exc:
            failures.append(str(exc))
            continue
        inventory_path = project / "evidence" / label / "inventory.json"
        if not inventory_path.is_file():
            failures.append(f"{label}: inventaire absent")
            continue
        expected = read_json(inventory_path)
        observed = _inventory(root)
        if expected.get("file_count") != observed.get("file_count"):
            failures.append(f"{label}: nombre de fichiers modifié")
        if expected.get("aggregate_sha256") != observed.get("aggregate_sha256"):
            failures.append(f"{label}: digest agrégé modifié")
        expected_files = expected.get("files", [])
        observed_files = observed.get("files", [])
        if expected_files != observed_files:
            failures.append(f"{label}: inventaire de fichiers modifié")
    return failures


def _text_extract(path: Path, output: Path, limit: int) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    truncated = len(text) > limit
    output.write_text(text[:limit], encoding="utf-8")
    return {"representation": output.name, "truncated": truncated}


def _safe_zip_member(info: zipfile.ZipInfo) -> PurePosixPath:
    name = PurePosixPath(info.filename.replace("\\", "/"))
    if name.is_absolute() or not name.parts or ".." in name.parts:
        raise ValueError(f"archive: chemin membre interdit: {info.filename}")
    mode = (info.external_attr >> 16) & 0o170000
    if mode and mode not in {stat.S_IFREG, stat.S_IFDIR}:
        raise ValueError(f"archive: lien/fichier spécial interdit: {info.filename}")
    if info.flag_bits & 0x1:
        raise ValueError(f"archive: membre chiffré interdit: {info.filename}")
    return name


def _checked_zip_members(
    archive: zipfile.ZipFile,
    limits: dict[str, Any],
) -> list[tuple[zipfile.ZipInfo, PurePosixPath]]:
    max_members = int(limits["archive_max_members"])
    max_total = int(limits["archive_max_total_uncompressed_bytes"])
    max_single = int(limits["archive_max_single_member_bytes"])
    max_ratio = float(limits["archive_max_compression_ratio"])
    infos = archive.infolist()
    if len(infos) > max_members:
        raise ValueError("archive: trop de membres")
    checked: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
    seen: set[str] = set()
    total = 0
    for info in infos:
        member = _safe_zip_member(info)
        if info.is_dir():
            continue
        folded = member.as_posix().casefold()
        if folded in seen:
            raise ValueError(f"archive: membre dupliqué ambigu: {info.filename}")
        seen.add(folded)
        total += info.file_size
        if info.file_size > max_single or total > max_total:
            raise ValueError("archive: limites de taille dépassées")
        denominator = max(info.compress_size, 1)
        if info.file_size / denominator > max_ratio:
            raise ValueError(f"archive: ratio de compression excessif: {info.filename}")
        checked.append((info, member))
    return checked


def _office_extract(
    path: Path,
    output: Path,
    limit: int,
    limits: dict[str, Any],
) -> dict[str, Any]:
    chunks: list[str] = []
    chars = 0
    with zipfile.ZipFile(path) as archive:
        for info, _ in _checked_zip_members(archive, limits):
            if not info.filename.lower().endswith(".xml"):
                continue
            data = archive.read(info)
            try:
                root = ElementTree.fromstring(data)
            except ElementTree.ParseError:
                continue
            for value in root.itertext():
                text = value.strip()
                if not text:
                    continue
                chunks.append(text)
                chars += len(text)
                if chars >= limit:
                    break
            if chars >= limit:
                break
    text = "\n".join(chunks)
    output.write_text(text[:limit], encoding="utf-8")
    return {"representation": output.name, "truncated": len(text) > limit}


def _archive_extract(
    path: Path,
    output_root: Path,
    limits: dict[str, Any],
) -> dict[str, Any]:
    members: list[dict[str, Any]] = []
    with zipfile.ZipFile(path) as archive:
        for info, member in _checked_zip_members(archive, limits):
            target = output_root.joinpath(*member.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open("wb") as destination:
                shutil.copyfileobj(source, destination)
            members.append(
                {
                    "path": member.as_posix(),
                    "sha256": sha256_file(target),
                    "size": target.stat().st_size,
                }
            )
    write_json(output_root.parent / "archive_index.json", {"members": members})
    return {
        "representation": output_root.name,
        "members": len(members),
        "truncated": False,
    }


def _format_kind(path: Path, policy: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    formats = policy["formats"]
    if path.name.casefold() in _SPECIAL_TEXT_NAMES:
        return "text", dict(formats["text"])
    suffix = path.suffix.casefold()
    for kind, raw in formats.items():
        if suffix in {str(value).casefold() for value in raw.get("extensions", [])}:
            return str(kind), dict(raw)
    return "unknown", {"method": "raw_file", "initial_status": "UNREADABLE"}


def build_ingestion_index(project: Path, repo_root: Path) -> Path:
    policy = core_contract(repo_root, "document_ingestion_policy.yaml")
    limits = dict(policy["limits"])
    text_limit = int(limits["max_text_characters_per_file"])
    entries: list[dict[str, Any]] = []
    intake = project / "intake"
    for source in sorted(path for path in intake.rglob("*") if path.is_file()):
        relative = source.relative_to(intake).as_posix()
        digest = sha256_file(source)
        document_id = f"doc-{len(entries) + 1:04d}-{digest[:12]}"
        artifact_root = project / "context" / "ingestion" / document_id
        artifact_root.mkdir(parents=True, exist_ok=False)
        kind, contract = _format_kind(source, policy)
        method = str(contract.get("method", "raw_file"))
        status = str(contract.get("initial_status", "UNREADABLE"))
        detail: dict[str, Any] = {}
        try:
            if kind == "text":
                detail = _text_extract(
                    source,
                    artifact_root / "extracted.txt",
                    text_limit,
                )
            elif kind == "office":
                detail = _office_extract(
                    source,
                    artifact_root / "extracted.txt",
                    text_limit,
                    limits,
                )
            elif kind == "archive":
                detail = _archive_extract(
                    source,
                    artifact_root / "archive_members",
                    limits,
                )
            elif kind in {"pdf", "image"}:
                detail = {"required_tool": method}
            else:
                detail = {"reason": "format non pris en charge automatiquement"}
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            status = "UNREADABLE"
            detail = {"reason": str(exc)}
        entry = {
            "document_id": document_id,
            "path": f"intake/{relative}",
            "sha256": digest,
            "mime": mime_type(source),
            "size": source.stat().st_size,
            "kind": kind,
            "method": method,
            "status": status,
            **detail,
        }
        write_json(artifact_root / "metadata.json", entry)
        entries.append(entry)
    index = {
        "schema_version": "1.0.0",
        "generated_at": now(),
        "documents": entries,
        "source_count": len(entries),
    }
    path = project / "context" / "ingestion" / "index.json"
    write_json(path, index)
    return path



def append_intake_items(
    repo_root: Path,
    platform_root: Path,
    project: Path,
    items: Iterable[Path],
) -> list[str]:
    """Add sources only inside a validated project rooted in the platform workspace.

    The project path is reconstructed from its allow-listed ID rather than trusting the
    caller's path. Normalization and containment precede *every* project file operation.
    """
    # Check containment at the string level before any filesystem operation on the
    # caller's path. realpath resolves symlinks; equality with normpath rejects them.
    root = os.path.realpath(os.fspath(platform_root / "projects"))
    supplied = os.path.normpath(os.fspath(project))
    candidate = os.path.realpath(supplied)
    # CodeQL recognizes normalization followed by a checked directory prefix as
    # a path-safety barrier. The separator prevents sibling prefix collisions.
    if not candidate.startswith(root + os.sep):
        raise ValueError("projet hors de la racine autorisée")
    if (
        os.path.commonpath((root, candidate)) != root
        or os.path.dirname(candidate) != root
        or supplied != candidate
    ):
        raise ValueError("projet hors de la racine autorisée")
    if validate_project_id(os.path.basename(candidate)) != os.path.basename(candidate):
        raise ValueError("identifiant du projet invalide")
    project = Path(candidate)
    assert_no_symlinks(project, label="projet d'ingestion")

    manifest_path = project / "project.json"
    payload = read_json(manifest_path)
    if payload.get("status") != "INTAKE_READY":
        raise ValueError(
            "les sources sont figées après le début de l'analyse; créer un nouveau projet "
            "ou réviser le périmètre avant d'ajouter des fichiers"
        )
    failures = validate_input_integrity(project)
    if failures:
        raise ValueError("intégrité des sources invalide: " + "; ".join(failures))

    policy = core_contract(repo_root, "intake_policy.yaml")
    limits = dict(policy["limits"])
    max_file = int(limits["max_single_file_bytes"])
    max_total = int(limits["max_total_input_bytes"])
    current_total = _size(project / "intake")
    if current_total >= max_total:
        raise ValueError("intake: limite totale déjà atteinte")

    staging = project / "context" / ".chat-intake-staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    copied: list[str] = []
    moved: list[Path] = []
    ingestion = project / "context" / "ingestion"
    ingestion_old = project / "context" / ".ingestion-before-chat"
    inventory_path = project / "evidence/intake/inventory.json"
    old_inventory = inventory_path.read_bytes()
    old_manifest = manifest_path.read_bytes()
    try:
        copied = _copy_inputs(
            items,
            staging,
            label="pièce jointe",
            max_file=max_file,
            max_total=max_total - current_total,
        )
        for name in copied:
            target = project / "intake" / name
            if target.exists():
                raise ValueError(f"pièce jointe: nom déjà présent: {name}")
            shutil.move(str(staging / name), str(target))
            moved.append(target)
        if ingestion_old.exists():
            shutil.rmtree(ingestion_old)
        if ingestion.exists():
            ingestion.rename(ingestion_old)
        write_json(inventory_path, _inventory(project / "intake"))
        build_ingestion_index(project, repo_root)
        existing = payload.get("intake_items", [])
        if not isinstance(existing, list):
            raise ValueError("project.json: intake_items invalide")
        payload["intake_items"] = [*existing, *copied]
        payload["updated_at"] = now()
        write_json(manifest_path, payload)
        chmod_read_only_files(project / "intake")
        if ingestion_old.exists():
            shutil.rmtree(ingestion_old)
        return copied
    except Exception:
        for path in moved:
            try:
                path.chmod(0o600)
                path.unlink()
            except OSError:
                pass
        inventory_path.write_bytes(old_inventory)
        manifest_path.write_bytes(old_manifest)
        if ingestion.exists():
            shutil.rmtree(ingestion, ignore_errors=True)
        if ingestion_old.exists():
            ingestion_old.rename(ingestion)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def create_project(
    repo_root: Path,
    platform_root: Path,
    project_id: str,
    title: str,
    *,
    intake_items: Iterable[Path] = (),
    source_items: Iterable[Path] = (),
    expected_deliverables: Iterable[str] = (),
    learning_mode: str = "direct",
    learning_goals: list[str] | None = None,
) -> Path:
    policy = core_contract(repo_root, "intake_policy.yaml")
    limits = dict(policy["limits"])
    max_file = int(limits["max_single_file_bytes"])
    max_total = int(limits["max_total_input_bytes"])
    project = project_path(platform_root, project_id, require=False)
    if project.exists():
        raise FileExistsError(project)
    try:
        for name in PROJECT_DIRS:
            (project / name).mkdir(
                parents=True,
                exist_ok=name != "intake",
            )
        intake_names = _copy_inputs(
            intake_items,
            project / "intake",
            label="intake",
            max_file=max_file,
            max_total=max_total,
        )
        source_names = _copy_inputs(
            source_items,
            project / "sources",
            label="sources",
            max_file=max_file,
            max_total=max_total,
        )
        intake_inventory = _inventory(project / "intake")
        sources_inventory = _inventory(project / "sources")
        write_json(
            project / "evidence" / "intake" / "inventory.json",
            intake_inventory,
        )
        write_json(
            project / "evidence" / "sources" / "inventory.json",
            sources_inventory,
        )
        build_ingestion_index(project, repo_root)
        deliverables = [item.strip() for item in expected_deliverables if item.strip()]
        manifest = {
            "schema_version": "1.0.0",
            "project_id": project.name,
            "title": title.strip() or project.name,
            "status": "INTAKE_READY",
            "created_at": now(),
            "updated_at": now(),
            "expected_deliverables": deliverables,
            "intake_items": intake_names,
            "source_items": source_names,
            "orchestration": {"history": []},
        }
        write_json(project / "project.json", manifest)
        from clawfedora.learning import initialize

        initialize(project, learning_mode, learning_goals)
        chmod_read_only_files(project / "intake")
        chmod_read_only_files(project / "sources")
        return project
    except Exception:
        if project.exists():
            shutil.rmtree(project, ignore_errors=True)
        raise
