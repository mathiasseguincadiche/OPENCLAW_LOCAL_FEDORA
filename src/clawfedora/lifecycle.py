from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from clawfedora import ollama_api
from clawfedora.agents import load_agent_specs
from clawfedora.contracts import validate_repository
from clawfedora.core_config import daily_limits, openclaw_environment, root_contract
from clawfedora.hardware_gate import collect_hardware_gate
from clawfedora.version_lock import extract_openclaw_version

MANAGED_MARKER = ".openclaw-fedora-managed"
RUNTIME_MARKER = ".openclaw-fedora-runtime"


@dataclass(frozen=True)
class HealthCheck:
    id: str
    status: str
    detail: str


@dataclass(frozen=True)
class HealthReport:
    checks: tuple[HealthCheck, ...]

    @property
    def ok(self) -> bool:
        return all(check.status == "PASS" for check in self.checks)

    def payload(self) -> dict[str, Any]:
        return {
            "verdict": "PASS" if self.ok else "FAIL",
            "checks": [check.__dict__ for check in self.checks],
        }


def model_plan(repo_root: Path) -> list[dict[str, Any]]:
    catalog = root_contract(repo_root, "model_catalog.yaml")
    models = catalog.get("models", {})
    if not isinstance(models, dict):
        raise ValueError("model_catalog.yaml: models invalide")
    result: list[dict[str, Any]] = []
    for alias, raw in models.items():
        if not isinstance(raw, dict) or raw.get("required") is not True:
            continue
        result.append(
            {
                "alias": str(alias),
                "runtime_id": str(raw.get("runtime_id", "")),
                "approximate_weight_gib": float(raw.get("approximate_weight_gib", 0.0)),
            }
        )
    if len(result) != 1 or any(not item["runtime_id"] for item in result):
        raise ValueError("lifecycle: flotte nominale invalide")
    return result


def _command_json(command: list[str], runtime_root: Path | None = None) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
            env=openclaw_environment(runtime_root) if runtime_root is not None else None,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    detail = completed.stdout.strip() or completed.stderr.strip()
    return completed.returncode == 0, detail[:100_000]


def _runtime_is_managed(runtime_root: Path) -> bool:
    runtime = runtime_root.resolve()
    return runtime != Path("/") and (runtime / RUNTIME_MARKER).is_file()


def _require_managed_runtime(runtime_root: Path) -> Path:
    runtime = runtime_root.resolve()
    if runtime == Path("/"):
        raise ValueError("lifecycle: runtime root / interdit")
    marker = runtime / RUNTIME_MARKER
    if not marker.is_file():
        raise ValueError(f"lifecycle: marqueur runtime géré absent: {marker}")
    return runtime


def collect_health(repo_root: Path, runtime_root: Path, *, probe: bool = False) -> HealthReport:
    checks: list[HealthCheck] = []
    contracts = validate_repository(repo_root)
    checks.append(
        HealthCheck(
            "repository-contracts",
            "PASS" if contracts.ok else "FAIL",
            "ok" if contracts.ok else "; ".join(contracts.failures[:3]),
        )
    )
    runtime_ok = runtime_root.is_dir() and _runtime_is_managed(runtime_root)
    checks.append(
        HealthCheck(
            "runtime-root",
            "PASS" if runtime_ok else "FAIL",
            str(runtime_root),
        )
    )
    openclaw = shutil.which("openclaw")
    checks.append(
        HealthCheck(
            "openclaw-cli",
            "PASS" if openclaw else "FAIL",
            openclaw or "absent",
        )
    )
    ollama = shutil.which("ollama")
    checks.append(HealthCheck("ollama", "PASS" if ollama else "FAIL", ollama or "absent"))
    if openclaw:
        ok, detail = _command_json([openclaw, "gateway", "status", "--json"], runtime_root)
        try:
            status = json.loads(detail)
            rpc = status.get("rpc", {})
            ok = ok and isinstance(rpc, dict) and rpc.get("ok") is True
        except (ValueError, AttributeError):
            ok = False
        checks.append(
            HealthCheck(
                "openclaw-gateway",
                "PASS" if ok else "FAIL",
                detail or "no output",
            )
        )
    else:
        checks.append(HealthCheck("openclaw-gateway", "FAIL", "openclaw absent"))
    workspaces = runtime_root / "workspaces"
    expected = load_agent_specs(repo_root)
    missing = [
        spec.agent_id
        for spec in expected
        if not (workspaces / spec.agent_id / MANAGED_MARKER).is_file()
    ]
    checks.append(
        HealthCheck(
            "agent-workspaces",
            "PASS" if not missing else "FAIL",
            "6 managed" if not missing else f"missing={missing}",
        )
    )
    versions: dict[str, Any] = {}
    try:
        versions = root_contract(repo_root, "runtime_versions.yaml")
        ok, output = _command_json([openclaw or "openclaw", "--version"], runtime_root)
        detected = extract_openclaw_version(output)
        match = ok and detected == str(versions["openclaw"]["version"])
        checks.append(HealthCheck("openclaw-version", "PASS" if match else "FAIL", detected))
    except (OSError, ValueError):
        checks.append(HealthCheck("openclaw-version", "FAIL", "version non confirmée"))
    endpoint = "http://127.0.0.1:11434"
    try:
        version = ollama_api.request_json(endpoint + "/api/version")
        expected_version = str(versions["ollama"]["version"])
        version_ok = version.get("version") == expected_version
        checks.append(
            HealthCheck(
                "ollama-version", "PASS" if version_ok else "FAIL", str(version.get("version"))
            )
        )
        tags = ollama_api.request_json(endpoint + "/api/tags")
        identities = ollama_api.model_inventory(tags, model_plan(repo_root))
        from clawfedora.model_identity import verify_model_lock

        verify_model_lock(runtime_root, identities)
        checks.append(
            HealthCheck("model-inventory", "PASS", "digests et Q4_K_M conformes au verrou local")
        )
        if probe:
            model = str(model_plan(repo_root)[0]["runtime_id"])
            answer = ollama_api.request_json(
                endpoint + "/api/generate",
                payload={
                    "model": model,
                    "prompt": "Réponds OK",
                    "stream": False,
                    "think": False,
                    "options": {
                        "num_ctx": int(daily_limits(repo_root)["context_tokens"]),
                        "num_predict": 8,
                    },
                    "keep_alive": "3m",
                },
                timeout=60,
            )
            runners = ollama_api.request_json(endpoint + "/api/ps").get("models", [])
            offloaded = any(
                isinstance(item, dict)
                and item.get("name") == model
                and int(item.get("size_vram", 0)) > 0
                for item in runners
            )
            ok = answer.get("done") is True and bool(answer.get("response")) and offloaded
            checks.append(
                HealthCheck(
                    "model-gpu-probe",
                    "PASS" if ok else "FAIL",
                    "inférence courte et VRAM observées",
                )
            )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        checks.append(HealthCheck("model-inventory", "FAIL", str(exc)))
    for command, check_id, expected_value in (
        (["getenforce"], "selinux-enforcing", "Enforcing"),
        (["systemctl", "is-active", "firewalld.service"], "firewalld", "active"),
    ):
        ok, output = _command_json(command)
        checks.append(
            HealthCheck(check_id, "PASS" if ok and output == expected_value else "FAIL", output)
        )
    gpu = collect_hardware_gate(repo_root, "gpu")
    checks.append(
        HealthCheck(
            "b580-vulkan",
            "PASS" if gpu.ok else "FAIL",
            "; ".join(item.detail for item in gpu.checks if item.status != "PASS")
            or "xe/Mesa/Vulkan observés",
        )
    )
    # Read the effective systemd environment, not the contents of a desired config file.
    ok, environment = _command_json(
        ["systemctl", "show", "ollama.service", "--property=Environment", "--value"]
    )
    required_env = {
        "OLLAMA_NUM_PARALLEL": "1",
        "OLLAMA_MAX_LOADED_MODELS": "1",
        "OLLAMA_MAX_QUEUE": "4",
        "OLLAMA_VULKAN": "1",
        "OLLAMA_HOST": "127.0.0.1:11434",
        "OLLAMA_MODELS": str(runtime_root / "models/ollama"),
    }
    limits_ok = ok and all(
        re.search(rf"(?:^|[\s\"]){key}={re.escape(value)}(?:$|[\s\"])", environment)
        for key, value in required_env.items()
    )
    checks.append(
        HealthCheck(
            "effective-inference-limits",
            "PASS" if limits_ok else "FAIL",
            "one model/one inference/queue=4/loopback"
            if limits_ok
            else "environnement service divergent",
        )
    )
    return HealthReport(tuple(checks))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _backup_sources(runtime_root: Path) -> list[Path]:
    names = ("state", "projects", "proofs", "workspaces", "runtime/generated")
    return [runtime_root / name for name in names if (runtime_root / name).exists()]


def _is_sqlite(path: Path) -> bool:
    if not path.is_file() or path.is_symlink():
        return False
    with path.open("rb") as stream:
        return stream.read(16) == b"SQLite format 3\0"


def _add_backup_file(tar: tarfile.TarFile, path: Path, name: str) -> str | None:
    # SQLite's backup API includes committed WAL rows in a consistent database.
    for suffix in ("-wal", "-shm", "-journal"):
        if path.name.endswith(suffix) and _is_sqlite(path.with_name(path.name[: -len(suffix)])):
            return None
    with tempfile.TemporaryDirectory(prefix="clawfedora-backup-") as directory:
        snapshot = Path(directory) / "file"
        if _is_sqlite(path):
            source = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
            destination = sqlite3.connect(snapshot)
            try:
                source.backup(destination)
            finally:
                destination.close()
                source.close()
            snapshot.chmod(0o600)
        else:
            shutil.copyfile(path, snapshot)
            snapshot.chmod(path.stat().st_mode & 0o777)
        digest = _sha256(snapshot)
        tar.add(snapshot, arcname=name, recursive=False)
        return digest


def create_backup(runtime_root: Path, output_dir: Path | None = None) -> Path:
    runtime = runtime_root.resolve()
    backup_dir = (output_dir or runtime / "backups").resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    archive = backup_dir / f"openclaw-local-fedora-{stamp}.tar.gz"
    manifest: dict[str, str] = {}
    pending = archive.with_suffix(archive.suffix + ".partial")
    pending.touch(mode=0o600, exist_ok=False)
    with tarfile.open(pending, "w:gz") as tar:
        marker = runtime / RUNTIME_MARKER
        if marker.is_file():
            manifest[RUNTIME_MARKER] = _sha256(marker)
            tar.add(marker, arcname=RUNTIME_MARKER, recursive=False)
        for source in _backup_sources(runtime):
            for path in sorted(source.rglob("*")):
                if path.is_symlink():
                    raise ValueError(f"backup: symlink interdit: {path}")
                if not path.is_file():
                    continue
                relative = path.relative_to(runtime)
                digest = _add_backup_file(tar, path, relative.as_posix())
                if digest is not None:
                    manifest[relative.as_posix()] = digest
        data = json.dumps(
            {
                "schema_version": "1.0.0",
                "created_at": datetime.now(UTC).isoformat(),
                "files": manifest,
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        ).encode("utf-8")
        info = tarfile.TarInfo("BACKUP_MANIFEST.json")
        info.size = len(data)
        info.mtime = int(datetime.now(UTC).timestamp())
        tar.addfile(info, io.BytesIO(data))
    pending.replace(archive)
    return archive


def _safe_member(name: str) -> Path:
    value = Path(name)
    if value.is_absolute() or ".." in value.parts:
        raise ValueError(f"restore: chemin archive interdit: {name}")
    return value


def _manifest_from_archive(tar: tarfile.TarFile) -> dict[str, Any]:
    try:
        member = tar.getmember("BACKUP_MANIFEST.json")
    except KeyError as exc:
        raise ValueError("restore: manifest absent") from exc
    if not member.isfile():
        raise ValueError("restore: manifest invalide")
    stream = tar.extractfile(member)
    if stream is None:
        raise ValueError("restore: manifest illisible")
    value = json.loads(stream.read().decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("restore: manifest invalide")
    return value


def restore_backup(archive: Path, destination: Path) -> Path:
    target = destination.resolve()
    if target.exists() and any(target.iterdir()):
        raise ValueError("restore: destination doit être vide")
    target.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive.resolve(), "r:gz") as tar:
        members = tar.getmembers()
        for member in members:
            _safe_member(member.name)
            if member.issym() or member.islnk() or member.isdev():
                raise ValueError(f"restore: type archive interdit: {member.name}")
        manifest = _manifest_from_archive(tar)
        files = manifest.get("files", {})
        if not isinstance(files, dict):
            raise ValueError("restore: manifest invalide")
        expected_files = {str(name) for name in files} | {"BACKUP_MANIFEST.json"}
        archive_files = {member.name for member in members if member.isfile()}
        if archive_files != expected_files:
            extras = sorted(archive_files - expected_files)
            missing = sorted(expected_files - archive_files)
            raise ValueError(
                f"restore: contenu archive non déclaré extras={extras} missing={missing}"
            )
        tar.extractall(target, members=members, filter="data")
    for relative, expected in files.items():
        path = target / _safe_member(str(relative))
        if not path.is_file() or _sha256(path) != str(expected):
            raise ValueError(f"restore: intégrité invalide: {relative}")
    return target


def cleanup_managed(runtime_root: Path, *, purge_data: bool = False) -> list[Path]:
    runtime = _require_managed_runtime(runtime_root)
    removed: list[Path] = []
    workspaces = runtime / "workspaces"
    if workspaces.is_dir():
        for child in workspaces.iterdir():
            if child.is_dir() and (child / MANAGED_MARKER).is_file():
                shutil.rmtree(child)
                removed.append(child)
    venv = runtime / "runtime" / "venv"
    if venv.is_dir():
        shutil.rmtree(venv)
        removed.append(venv)
    if purge_data:
        for name in ("projects", "proofs", "state", "models"):
            path = runtime / name
            if path.is_dir():
                shutil.rmtree(path)
                removed.append(path)
    return removed


def migrate_openclaw_state(runtime: Path, source: Path) -> Path:
    """Keep the legacy state intact and copy it into the backed-up managed root."""
    from clawfedora.project_common import assert_no_symlinks

    source = source.expanduser()
    assert_no_symlinks(source, label="état historique")
    if not (source / "openclaw.json").is_file():
        raise ValueError("état historique sans openclaw.json")
    target = runtime / "state/openclaw"
    if target.exists():
        raise ValueError("destination état déjà existante; aucun écrasement")
    if source.resolve() in target.resolve().parents:
        raise ValueError("migration récursive interdite")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name("openclaw-migration")
    if temporary.exists():
        raise ValueError("migration précédente incomplète: vérifier openclaw-migration")
    shutil.copytree(source, temporary)
    for path in temporary.rglob("*"):
        if path.is_file():
            relative = path.relative_to(temporary)
            if _sha256(path) != _sha256(source / relative):
                raise ValueError(f"migration: intégrité invalide: {relative}")
            path.chmod(0o600)
        elif path.is_dir():
            path.chmod(0o700)
    temporary.chmod(0o700)
    temporary.rename(target)
    create_backup(runtime)
    return target
