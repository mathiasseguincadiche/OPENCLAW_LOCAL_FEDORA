"""Operator-approved, rootless and offline validation of proposed DevOps edits.

The LLM submits proposed file contents; only an isolated COPY is modified.
The original workspace, central project, host and GitHub are never modified.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import tempfile
from contextlib import redirect_stdout
from pathlib import Path, PurePosixPath
from typing import Any

from clawfedora.devops_lab import (
    LabRefusal, SAFE_SUFFIXES, SENSITIVE_NAMES, SENSITIVE_SUFFIXES,
    TOOLS, image_is_pinned, run_lab, snapshot_manifest,
)
from clawfedora.project_common import assert_no_symlinks
from clawfedora.specialist_tools import receipt

POLICY_PATH = Path("state/lab/validator-image.json")
MAX_PATCH_FILES = 5
MAX_PATCH_BYTES = 16000


def _policy_file(runtime: Path) -> Path:
    if runtime.is_symlink() or not (runtime / ".openclaw-fedora-runtime").is_file():
        raise LabRefusal("Runtime OpenClaw géré requis")
    base = runtime / "state/lab"
    if base.is_symlink():
        raise LabRefusal("Répertoire de politique lié interdit")
    return runtime / POLICY_PATH


def approve_image(runtime: Path, image: str, *, apply: bool) -> dict[str, Any]:
    """Explicit human-only, local CLI operation; never exposed as an agent tool."""
    target = _policy_file(runtime)
    if os.geteuid() == 0:
        raise LabRefusal("Accord utilisateur refusé sous root")
    if not image_is_pinned(image):
        raise LabRefusal("Image OCI avec digest SHA-256 requise")
    if not apply:
        return {"status": "DRY_RUN", "image": image, "applied": False}
    if shutil.which("podman") is None:
        raise LabRefusal("Podman rootless requis")
    probe = subprocess.run(
        ["podman", "image", "exists", image], timeout=20,
        capture_output=True, check=False,
    )
    if probe.returncode:
        raise LabRefusal("Image immuable absente localement")
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if target.is_symlink():
        raise LabRefusal("Fichier de politique lié interdit")
    descriptor = os.open(
        target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        json.dump({"image": image, "approved_by_operator": True}, output)
    target.chmod(0o600)
    return {"status": "PASS", "image": image, "applied": True}


def _approved_image(runtime: Path) -> str:
    target = _policy_file(runtime)
    if target.is_symlink() or not target.is_file():
        raise LabRefusal("Aucune image validée par l'opérateur")
    stat = target.stat()
    if stat.st_uid != os.geteuid() or stat.st_mode & 0o077:
        raise LabRefusal("Politique de validation accessible à un tiers")
    payload = json.loads(target.read_text(encoding="utf-8"))
    if payload.get("approved_by_operator") is not True:
        raise LabRefusal("Accord opérateur absent")
    image = payload.get("image")
    if not isinstance(image, str) or not image_is_pinned(image):
        raise LabRefusal("Identité de l'image invalide")
    return image


def _validated_scope(workspace: Path, scope: str) -> Path:
    relative = PurePosixPath(scope)
    if (
        relative.is_absolute() or ".." in relative.parts
        or len(relative.parts) != 4 or relative.parts[0] != "projects"
        or any(not part or part.startswith(".") for part in relative.parts)
    ):
        raise LabRefusal("Scope de tâche courant projects/<id>/<tâche>/<session> requis")
    source = workspace.joinpath(*relative.parts)
    if not source.is_dir() or not source.resolve().is_relative_to(workspace.resolve()):
        raise LabRefusal("Snapshot de tâche hors du workspace")
    assert_no_symlinks(source, label="snapshot DevOps")
    if not (source / ".openclaw-fedora-input-guard.json").is_file():
        raise LabRefusal("Snapshot de tâche non scellé")
    return source


def _overlay(target: Path, changes: dict[str, str]) -> dict[str, str]:
    if not changes or len(changes) > MAX_PATCH_FILES:
        raise LabRefusal("Un à cinq fichiers de correction requis")
    if sum(len(v.encode("utf-8")) for v in changes.values()) > MAX_PATCH_BYTES:
        raise LabRefusal("Corrections supérieures au budget")
    hashes: dict[str, str] = {}
    for name, content in changes.items():
        relative = PurePosixPath(name)
        if (
            relative.is_absolute() or ".." in relative.parts or not relative.parts
            or any(p.startswith(".") and p != ".github" for p in relative.parts)
            or relative.name in SENSITIVE_NAMES
            or relative.suffix in SENSITIVE_SUFFIXES
            or (relative.suffix not in SAFE_SUFFIXES and relative.name != "Dockerfile")
            or not isinstance(content, str)
        ):
            raise LabRefusal("Chemin ou contenu interdit dans la proposition")
        path = target.joinpath(*relative.parts)
        if path.exists() and (path.is_symlink() or not path.is_file()):
            raise LabRefusal("Destination irrégulière interdite")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        hashes[name] = hashlib.sha256(content.encode()).hexdigest()
    snapshot_manifest(target)
    return hashes


def validate_proposal(
    runtime: Path, workspace: Path, scope: str, tool: str, changes: dict[str, str]
) -> dict[str, Any]:
    """Validate a proposed edit through offline Podman; no host/project writes."""
    if tool not in TOOLS:
        raise LabRefusal("Validateur non autorisé")
    image = _approved_image(runtime)
    source = _validated_scope(workspace, scope)
    manifest = snapshot_manifest(source)
    with tempfile.TemporaryDirectory(prefix="clawfedora-proposed-") as directory:
        isolated = Path(directory) / "source"
        isolated.mkdir(mode=0o700)
        for name in manifest:
            from_path = source / name
            if from_path.is_symlink() or not from_path.is_file():
                raise LabRefusal("Source modifiée pendant la copie")
            destination = isolated / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(from_path, destination, follow_symlinks=False)
        hashes = _overlay(isolated, changes)
        stream = io.StringIO()
        with redirect_stdout(stream):
            code = run_lab(isolated, tool, image, apply=True)
        log = stream.getvalue()[-7500:]
    result: dict[str, Any] = {
        "status": "PASS" if code == 0 else "FAIL",
        "exit_code": code,
        "validator": tool,
        "files_sha256": hashes,
        "log": log,
        "executed": True,
        "network": "none",
        "workspace_modified": False,
        "note": "Les contrôles sont limités au conteneur et ne certifient pas un déploiement.",
    }
    result["receipt"] = receipt(workspace, "clawfedora_sandbox_validate", {
        key: value for key, value in result.items() if key != "log"
    })
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Approuver une image locale de validation")
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(approve_image(args.runtime, args.image, apply=args.apply)))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)[:200]}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
