from __future__ import annotations

import hashlib
import io
import json
import shutil
import subprocess
import tarfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from clawfedora.agents import load_agent_specs
from clawfedora.contracts import validate_repository
from clawfedora.core_config import root_contract

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
                "nominal_context_tokens": int(raw.get("nominal_context_tokens", 0)),
            }
        )
    if len(result) != 3 or any(not item["runtime_id"] for item in result):
        raise ValueError("lifecycle: flotte nominale invalide")
    return result


def _command_json(command: list[str]) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    detail = completed.stdout.strip() or completed.stderr.strip()
    return completed.returncode == 0, detail[:500]


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


def collect_health(repo_root: Path, runtime_root: Path) -> HealthReport:
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
    checks.append(
        HealthCheck("ollama", "PASS" if ollama else "FAIL", ollama or "absent")
    )
    if openclaw:
        ok, detail = _command_json([openclaw, "gateway", "status", "--json"])
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
            "8 managed" if not missing else f"missing={missing}",
        )
    )
    if ollama:
        ok, detail = _command_json([ollama, "list"])
        required = [item["runtime_id"] for item in model_plan(repo_root)]
        absent = [model for model in required if model not in detail]
        checks.append(
            HealthCheck(
                "model-inventory",
                "PASS" if ok and not absent else "FAIL",
                "all required present" if ok and not absent else f"missing={absent}",
            )
        )
    else:
        checks.append(HealthCheck("model-inventory", "FAIL", "ollama absent"))
    return HealthReport(tuple(checks))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _backup_sources(runtime_root: Path) -> list[Path]:
    names = ("state", "projects", "proofs", "workspaces")
    return [runtime_root / name for name in names if (runtime_root / name).exists()]


def create_backup(runtime_root: Path, output_dir: Path | None = None) -> Path:
    runtime = runtime_root.resolve()
    backup_dir = (output_dir or runtime / "backups").resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    archive = backup_dir / f"openclaw-local-fedora-{stamp}.tar.gz"
    manifest: dict[str, str] = {}
    with tarfile.open(archive, "w:gz") as tar:
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
                manifest[relative.as_posix()] = _sha256(path)
                tar.add(path, arcname=relative.as_posix(), recursive=False)
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
        for name in ("projects", "proofs", "state", "models", "benchmarks"):
            path = runtime / name
            if path.is_dir():
                shutil.rmtree(path)
                removed.append(path)
    return removed
