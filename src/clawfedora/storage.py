"""Shared storage contract and read-only guards, usable before installing dependencies."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SENSITIVE_DIRECTORIES = (
    "models", "models/ollama", "models/whisper", "projects", "workspaces",
    "state", "state/openclaw", "state/webui", "state/webui/data", "state/cloud",
    "state/web-access", "runtime", "runtime/venv", "runtime/generated",
    "runtime/extensions", "runtime/downloads", "runtime/podman", "runtime/podman/storage",
    "runtime/podman/tmp", "proofs", "backups",
)


def _path(value: str | Path) -> Path:
    text = str(value)
    path = Path(text)
    if (not path.is_absolute() or not re.fullmatch(r"/[A-Za-z0-9_./-]+", text)
            or str(path) != text or ".." in path.parts):
        raise ValueError("chemin runtime non canonique ou lié: chemin absolu simple requis")
    return path


@dataclass(frozen=True)
class StorageSettings:
    mountpoint: Path
    runtime_root: Path
    filesystem: str
    volume_uuid: str
    minimum_data_gib: int
    minimum_system_gib: int


def load_settings(repo: Path = REPO_ROOT, *, use_environment: bool = True) -> StorageSettings:
    raw: Any = json.loads((repo / "config/storage.json").read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ValueError("contrat de stockage invalide")
    env = os.environ if use_environment else {}
    mount = _path(env.get("OPENCLAW_LOCAL_FEDORA_MOUNT") or str(raw["mountpoint"]))
    runtime = _path(env.get("OPENCLAW_LOCAL_FEDORA_ROOT") or str(raw["runtime_root"]))
    if mount == Path("/"):
        raise ValueError("le volume de données doit être distinct de /")
    if raw.get("filesystem") != "ext4":
        raise ValueError("le contrat de cette installation exige EXT4")
    data_gib, system_gib = raw["minimum_data_gib"], raw["minimum_system_gib"]
    if (type(data_gib) is not int or data_gib < 15
            or type(system_gib) is not int or system_gib < 1):
        raise ValueError("minimums d’espace libre invalides")
    uuid = raw.get("volume_uuid", "")
    if not isinstance(uuid, str) or (uuid and not re.fullmatch(r"[A-Fa-f0-9-]+", uuid)):
        raise ValueError("UUID de volume invalide")
    return StorageSettings(mount, runtime, "ext4", uuid, data_gib, system_gib)


def validate_layout(runtime: Path, settings: StorageSettings) -> None:
    root, mount = _path(runtime), _path(settings.mountpoint)
    if mount not in root.parents:
        raise ValueError("racine runtime hors du volume de données déclaré")
    # Check every ancestor, including /data/IA: checking only the leaf misses redirects.
    for path in (root, *root.parents):
        if path.is_symlink():
            raise ValueError("chemin runtime non canonique ou lié")
        if path.exists() and not path.is_dir():
            raise ValueError("chemin de données non répertoire")
    for name in SENSITIVE_DIRECTORIES:
        target = root / name
        if target.is_symlink():
            raise ValueError(f"répertoire runtime lié interdit: {name}")
        if target.exists() and not target.is_dir():
            raise ValueError(f"répertoire runtime invalide: {name}")


def mount_details(mount: Path) -> tuple[str, set[str], str]:
    result = subprocess.run(
        ["findmnt", "--json", "--mountpoint", str(mount), "--output", "FSTYPE,OPTIONS,UUID"],
        capture_output=True, text=True, timeout=10, check=False,
    )
    if result.returncode:
        raise ValueError(f"disque secondaire non monté sur {mount}")
    value = json.loads(result.stdout)["filesystems"]
    if not isinstance(value, list) or len(value) != 1:
        raise ValueError("montage de données ambigu")
    record = value[0]
    return str(record["fstype"]), set(str(record["options"]).split(",")), str(
        record.get("uuid") or ""
    )


def require_storage(runtime: Path, settings: StorageSettings | None = None) -> None:
    settings = settings or load_settings()
    validate_layout(runtime, settings)
    mount = settings.mountpoint
    if not mount.is_mount() or mount.stat().st_dev == Path("/").stat().st_dev:
        raise ValueError(f"disque secondaire distinct non monté sur {mount}")
    filesystem, options, uuid = mount_details(mount)
    if filesystem != settings.filesystem:
        raise ValueError(f"{mount}: EXT4 requis, détecté {filesystem}")
    if "ro" in options or "noexec" in options:
        raise ValueError(f"{mount}: montage en lecture/écriture et exécution requis")
    if settings.volume_uuid and uuid.lower() != settings.volume_uuid.lower():
        raise ValueError("UUID du volume de données différent du contrat")
    # Existing nested mounts may also redirect writes to a different device.
    for path in (runtime, *(runtime / name for name in SENSITIVE_DIRECTORIES)):
        if path.exists() and path.stat().st_dev != mount.stat().st_dev:
            raise ValueError(f"répertoire runtime sur un autre volume: {path}")


def free_bytes(path: Path) -> int:
    value = os.statvfs(path)
    return value.f_bavail * value.f_frsize


def mount_unit_lines(runtime: Path, repo: Path = REPO_ROOT) -> str:
    mount = load_settings(repo).mountpoint
    return (
        f"RequiresMountsFor={mount}\nConditionPathIsMountPoint={mount}\n"
    )


def service_storage_check(runtime: Path, repo: Path = REPO_ROOT) -> str:
    # Only user services run editable repository code. The system Ollama unit
    # uses mount conditions; it never executes user-owned scripts as root.
    helper = repo / "src/clawfedora/storage.py"
    mount = load_settings(repo).mountpoint
    return (
        f"Environment=OPENCLAW_LOCAL_FEDORA_MOUNT={mount}\n"
        f"Environment=OPENCLAW_LOCAL_FEDORA_ROOT={runtime}\n"
        f"ExecStartPre=/usr/bin/python3 -I -S {helper} "
        f"--repo-root {repo} check --runtime-root {runtime}\n"
    )


def podman_config(runtime: Path) -> Path:
    return runtime / "runtime/generated/webui-storage.conf"


def render_podman_storage(runtime: Path) -> Path:
    """Only the managed WebUI process receives this config; personal Podman is unchanged."""
    graph = runtime / "runtime/podman/storage"
    for path in (graph, *graph.parents):
        if path.is_symlink():
            raise ValueError("stockage Podman lié interdit")
    graph.mkdir(parents=True, exist_ok=True, mode=0o700)
    (graph.parent / "tmp").mkdir(exist_ok=True, mode=0o700)
    config = podman_config(runtime)
    config.parent.mkdir(parents=True, exist_ok=True)
    if config.is_symlink():
        raise ValueError("configuration Podman liée interdite")
    config.write_text(
        '[storage]\ndriver = "overlay"\n'
        f'graphroot = "{graph}"\nrootless_storage_path = "{graph}"\n'
        f'runroot = "/run/user/{os.getuid()}/clawfedora-webui-storage"\n',
        encoding="utf-8",
    )
    config.chmod(0o600)
    return config


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("action", choices=("root", "mount", "check", "units", "service", "podman"))
    parser.add_argument("--runtime-root", type=Path)
    args = parser.parse_args()
    try:
        settings = load_settings(args.repo_root)
        runtime = args.runtime_root or settings.runtime_root
        if args.action == "root":
            print(runtime)
        elif args.action == "mount":
            print(settings.mountpoint)
        elif args.action == "units":
            print(mount_unit_lines(runtime, args.repo_root), end="")
        elif args.action == "service":
            print(service_storage_check(runtime, args.repo_root), end="")
        else:
            require_storage(runtime, settings)
            if args.action == "podman":
                print(render_podman_storage(runtime))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(f"STORAGE_RESULT=REFUSED: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
