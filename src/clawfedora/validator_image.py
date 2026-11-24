"""Operator-only offline validator image build; no automatic approval or publication."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from clawfedora.devops_lab import IMAGE_RE, LabRefusal

BINARIES = {"terraform", "shellcheck", "actionlint", "hadolint", "kubeconform"}
REQUIRED_DIRS = {"bin", "wheels", "terraform-providers", "schemas"}
SHA256 = re.compile(r"[0-9a-f]{64}")
LOCAL_ID = re.compile(r"sha256:[0-9a-f]{64}")


def file_digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_payload(payload: Path) -> dict[str, str]:
    """Verify a complete manifest; reject unlisted files, links and missing inputs."""
    if not payload.is_dir() or payload.is_symlink():
        raise LabRefusal("Répertoire de ressources local requis")
    manifest_file = payload / "manifest.json"
    if manifest_file.is_symlink() or not manifest_file.is_file():
        raise LabRefusal("Manifest SHA-256 requis")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not manifest or any(
        not isinstance(value, str) or not SHA256.fullmatch(value)
        for value in manifest.values()
    ):
        raise LabRefusal("Manifest SHA-256 invalide")
    actual: dict[str, str] = {}
    for path in sorted(payload.rglob("*")):
        relative = path.relative_to(payload).as_posix()
        if path.is_symlink():
            raise LabRefusal("Lien symbolique interdit dans les ressources")
        if path.is_dir():
            continue
        if not path.is_file():
            raise LabRefusal("Ressource non régulière")
        if relative != "manifest.json":
            actual[relative] = file_digest(path)
    if actual != manifest:
        raise LabRefusal("Inventaire ou empreinte des ressources différent du manifest")
    expected = {"requirements.lock", "sources.md"} | {f"bin/{name}" for name in BINARIES}
    if not expected <= actual.keys() or any(
        not any(name.startswith(directory + "/") for name in actual)
        for directory in REQUIRED_DIRS
    ):
        raise LabRefusal("Ressources des validateurs incomplètes")
    if any(
        name not in expected and name.split("/")[0] not in REQUIRED_DIRS
        for name in actual
    ):
        raise LabRefusal("Ressource hors des répertoires autorisés")
    if {name for name in actual if name.startswith("bin/")} != {
        f"bin/{name}" for name in BINARIES
    }:
        raise LabRefusal("Binaire supplémentaire interdit")
    return actual


def build_image(root: Path, base: str, payload: Path, *, apply: bool) -> dict[str, Any]:
    if not IMAGE_RE.fullmatch(base) or ".." in base:
        raise LabRefusal("Base OCI de registre épinglée par digest requise")
    manifest = verify_payload(payload)
    recipe = root / "containers/validators/Containerfile"
    if recipe.is_symlink() or not recipe.is_file():
        raise LabRefusal("Containerfile des validateurs introuvable")
    result: dict[str, Any] = {
        "status": "PLAN_ONLY", "base": base, "files": len(manifest),
        "manifest_sha256": file_digest(payload / "manifest.json"),
        "recipe_sha256": file_digest(recipe), "approved": False,
        "network": "none",
    }
    if not apply:
        return result
    if os.geteuid() == 0 or not shutil.which("podman"):
        raise LabRefusal("Podman rootless et compte non-root requis")
    present = subprocess.run(
        ["podman", "image", "exists", base], timeout=20, check=False,
        capture_output=True,
    )
    if present.returncode:
        raise LabRefusal("Base absente localement : aucun téléchargement automatique")
    with tempfile.TemporaryDirectory(prefix="clawfedora-validator-build-") as scratch:
        context = Path(scratch)
        staged = context / "payload"
        shutil.copytree(payload, staged, symlinks=True)
        if verify_payload(staged) != manifest:
            raise LabRefusal("Ressources modifiées pendant la copie")
        if file_digest(staged / "manifest.json") != result["manifest_sha256"]:
            raise LabRefusal("Manifest modifié pendant la copie")
        shutil.copyfile(recipe, context / "Containerfile")
        if file_digest(context / "Containerfile") != result["recipe_sha256"]:
            raise LabRefusal("Containerfile modifié pendant la copie")
        iid = context / "image-id"
        built = subprocess.run(
            [
                "podman", "build", "--pull=never", "--network=none",
                "--http-proxy=false", "--build-arg", f"VALIDATOR_BASE={base}",
                "--iidfile", str(iid), "--file", str(context / "Containerfile"),
                str(context),
            ],
            check=False, timeout=900, capture_output=True, text=True,
        )
        if built.returncode:
            raise LabRefusal("Construction OCI en échec : " + built.stderr[-1500:])
        identity = iid.read_text(encoding="utf-8").strip()
        if SHA256.fullmatch(identity):
            identity = "sha256:" + identity
        if not LOCAL_ID.fullmatch(identity):
            raise LabRefusal("Identifiant local complet de l'image introuvable")
    result.update({"status": "BUILT_NOT_QUALIFIED", "image": identity})
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--base", required=True)
    parser.add_argument("--payload", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(build_image(args.root, args.base, args.payload, apply=args.apply)))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)[:2000]}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
