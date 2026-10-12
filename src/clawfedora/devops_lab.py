"""Opt-in, offline and rootless DevOps validation in a disposable container.

This is deliberately *not* an OpenClaw agent tool: an LLM cannot invoke it.
The user must specify a local, immutable, pre-installed validator image and
approve --apply. Nothing is mounted from the original project directory.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import stat
import subprocess
import tempfile
import uuid
from pathlib import Path

IMAGE_RE = re.compile(
    r"^[a-z0-9][a-z0-9.:-]*/[a-z0-9][a-z0-9./_-]*@sha256:[0-9a-f]{64}$"
)
TOOLS = {
    "terraform-fmt",
    "terraform-validate",
    "ansible-lint",
    "actionlint",
    "shellcheck",
    "hadolint",
}
IGNORED_DIRS = {
    ".git", ".terraform", ".venv", "venv", "node_modules", "__pycache__",
    ".mypy_cache", ".pytest_cache", "dist", "build",
}
SAFE_SUFFIXES = {".tf", ".yaml", ".yml", ".json", ".sh", ".py", ".md", ".ini", ".j2", ".toml", ".cfg"}
SENSITIVE_NAMES = {".env", ".env.local", ".npmrc", ".pypirc", "credentials", "id_rsa", "id_ed25519"}
SENSITIVE_SUFFIXES = {".tfvars", ".tfstate", ".key", ".pem", ".p12", ".pfx"}
MAX_FILES = 300
MAX_BYTES = 12 * 1024 * 1024


class LabRefusal(ValueError):
    """Fail-closed refusal before any container starts."""


def image_is_pinned(image: str) -> bool:
    return bool(IMAGE_RE.fullmatch(image)) and ".." not in image


def snapshot_manifest(source: Path) -> tuple[Path, ...]:
    """Find a bounded, non-sensitive snapshot; refuse symlinks anywhere in scope."""
    if not source.is_dir() or source.is_symlink():
        raise LabRefusal("Le projet doit être un vrai répertoire, pas un lien symbolique")
    files: list[Path] = []
    total_bytes = 0
    for current, dirs, names in os.walk(source, followlinks=False):
        root = Path(current)
        for name in list(dirs):
            if name in IGNORED_DIRS:
                dirs.remove(name)
            elif (root / name).is_symlink():
                raise LabRefusal(f"Répertoire lié refusé: {(root / name).relative_to(source)}")
        dirs.sort()
        for name in sorted(names):
            path = root / name
            relative = path.relative_to(source)
            if path.is_symlink():
                raise LabRefusal(f"Fichier lié refusé: {relative}")
            if name in SENSITIVE_NAMES or path.suffix in SENSITIVE_SUFFIXES or name.endswith(".tfstate.backup"):
                raise LabRefusal(f"Fichier sensible détecté, copie refusée: {relative}")
            # Hidden files other than the tracked GitHub workflows are not needed.
            if any(part.startswith(".") and part != ".github" for part in relative.parts):
                continue
            if path.suffix not in SAFE_SUFFIXES and name != "Dockerfile":
                continue
            mode = path.stat(follow_symlinks=False)
            if not stat.S_ISREG(mode.st_mode):
                raise LabRefusal(f"Fichier non régulier refusé: {relative}")
            total_bytes += mode.st_size
            files.append(relative)
            if len(files) > MAX_FILES or total_bytes > MAX_BYTES:
                raise LabRefusal("Instantané trop volumineux : réduire le projet")
    if not files:
        raise LabRefusal("Aucun fichier de configuration ou de code compatible")
    return tuple(files)


def command_for(tool: str, snapshot: Path, manifest: tuple[Path, ...]) -> list[str]:
    """Fixed argv only; no shell, project-supplied command, or executable scripts."""
    if tool == "terraform-fmt":
        return ["terraform", "-chdir=/workspace", "fmt", "-check", "-recursive", "-no-color"]
    if tool == "terraform-validate":
        return ["terraform", "-chdir=/workspace", "validate", "-no-color"]
    if tool == "ansible-lint":
        return ["ansible-lint", "--offline", "/workspace"]
    if tool == "actionlint":
        if not any(p.parts[:2] == (".github", "workflows") for p in manifest):
            raise LabRefusal("Aucun workflow GitHub dans le projet")
        return ["actionlint", "-no-color"]
    if tool == "shellcheck":
        scripts = ["/workspace/" + str(p) for p in manifest if p.suffix == ".sh"]
        if not scripts:
            raise LabRefusal("Aucun script .sh dans le projet")
        return ["shellcheck", "--", *scripts]
    if tool == "hadolint":
        dockerfiles = ["/workspace/" + str(p) for p in manifest if p.name == "Dockerfile"]
        if not dockerfiles:
            raise LabRefusal("Aucun Dockerfile dans le projet")
        return ["hadolint", *dockerfiles]
    raise LabRefusal(f"Outil non autorisé: {tool}")


def isolated_argv(image: str, snapshot: Path, tool_argv: list[str], name: str) -> list[str]:
    return [
        "podman", "run", "--rm", "--name", name, "--pull=never",
        "--network=none", "--http-proxy=false", "--read-only",
        "--userns=keep-id", "--cap-drop=ALL", "--security-opt=no-new-privileges",
        "--pids-limit=128", "--memory=2g", "--cpus=2",
        "--tmpfs=/tmp:rw,nosuid,nodev,size=256m",
        "--env=HOME=/tmp", "--env=TF_DATA_DIR=/tmp/terraform",
        "--volume", f"{snapshot}:/workspace:ro,Z", "--workdir=/workspace",
        image, *tool_argv,
    ]


def run_lab(source: Path, tool: str, image: str | None, apply: bool) -> int:
    if tool not in TOOLS:
        raise LabRefusal("Outil inconnu")
    if os.geteuid() == 0 and apply:
        raise LabRefusal("Exécution root interdite")
    source = source.absolute()
    manifest = snapshot_manifest(source)
    command = command_for(tool, source, manifest)
    if not apply:
        print(f"DRY_RUN=PASS tool={tool} files={len(manifest)} network=none readonly=true")
        print("Aucune image ni commande lancée. --apply + --image avec digest sont requis.")
        return 0
    if not image or not image_is_pinned(image):
        raise LabRefusal("Image locale épinglée par @sha256:64-hexdigits obligatoire")
    if not shutil.which("podman"):
        raise LabRefusal("Podman introuvable")
    present = subprocess.run(
        ["podman", "image", "exists", image], check=False, capture_output=True, timeout=20
    )
    if present.returncode:
        raise LabRefusal("Image immuable absente localement : aucun téléchargement automatique")
    with tempfile.TemporaryDirectory(prefix="clawfedora-lab-") as staging:
        work = Path(staging) / "workspace"
        work.mkdir(mode=0o700)
        for relative in manifest:
            src = source / relative
            # Recheck at copy time: do not follow links introduced after the manifest.
            if src.is_symlink() or not src.is_file():
                raise LabRefusal(f"Source modifiée pendant la copie: {relative}")
            dest = work / relative
            dest.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with src.open("rb") as reader, dest.open("xb") as writer:
                shutil.copyfileobj(reader, writer)
            dest.chmod(0o600)
        name = "clawfedora-lab-" + uuid.uuid4().hex[:16]
        argv = isolated_argv(image, work, command, name)
        print(f"LAB tool={tool} files={len(manifest)} network=none image={image}")
        try:
            result = subprocess.run(argv, check=False, timeout=180)
            print(f"LAB_RESULT={'PASS' if result.returncode == 0 else 'FAIL'} exit={result.returncode}")
            return result.returncode
        except subprocess.TimeoutExpired:
            print("LAB_RESULT=FAIL timeout=180s")
            return 124
        finally:
            # A timed-out Podman client may have left a container behind.
            subprocess.run(
                ["podman", "rm", "-f", "--ignore", name],
                check=False, capture_output=True, timeout=20,
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Laboratoire DevOps isolé, hors des agents IA")
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--tool", required=True, choices=sorted(TOOLS))
    parser.add_argument("--image", help="image OCI déjà installée, référencée par @sha256")
    parser.add_argument("--apply", action="store_true", help="autorise l'exécution offline")
    args = parser.parse_args(argv)
    try:
        return run_lab(args.project, args.tool, args.image, args.apply)
    except (LabRefusal, OSError, subprocess.SubprocessError) as exc:
        print(f"LAB_RESULT=REFUSED reason={exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
