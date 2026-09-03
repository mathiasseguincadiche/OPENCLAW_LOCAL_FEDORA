from __future__ import annotations

import io
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from clawfedora import lifecycle

ROOT = Path(__file__).resolve().parents[1]


def _mark_runtime(runtime: Path) -> None:
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / lifecycle.RUNTIME_MARKER).write_text("managed\n", encoding="utf-8")


def test_model_plan_is_exact_rightsized_fleet() -> None:
    plan = lifecycle.model_plan(ROOT)
    assert [item["runtime_id"] for item in plan] == [
        "qwen3.5:9b-q4_K_M",
        "gemma3:12b-it-q4_K_M",
        "qwen2.5-coder:14b-instruct-q4_K_M",
    ]
    assert all(item["nominal_context_tokens"] == 8192 for item in plan)


def test_backup_restore_roundtrip_excludes_models_and_venv(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime-root"
    _mark_runtime(runtime)
    for relative, content in {
        "state/a.json": "state",
        "projects/p/README.md": "project",
        "proofs/p.json": "proof",
        "workspaces/a/file.txt": "workspace",
        "models/model.gguf": "model",
        "runtime/venv/bin/python": "venv",
    }.items():
        path = runtime / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    archive = lifecycle.create_backup(runtime)
    assert archive.is_file()
    restored = tmp_path / "restored"
    lifecycle.restore_backup(archive, restored)
    assert (restored / "state/a.json").read_text(encoding="utf-8") == "state"
    assert (restored / "projects/p/README.md").is_file()
    assert not (restored / "models/model.gguf").exists()
    assert not (restored / "runtime/venv/bin/python").exists()
    assert (restored / lifecycle.RUNTIME_MARKER).is_file()
    assert (restored / "BACKUP_MANIFEST.json").is_file()


def test_restore_rejects_nonempty_destination(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    (runtime / "state").mkdir(parents=True)
    (runtime / "state/a").write_text("x", encoding="utf-8")
    archive = lifecycle.create_backup(runtime)
    destination = tmp_path / "destination"
    destination.mkdir()
    (destination / "keep").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="destination doit être vide"):
        lifecycle.restore_backup(archive, destination)


def test_restore_rejects_archive_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "bad.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        data = b"bad"
        info = tarfile.TarInfo("../escape")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    with pytest.raises(ValueError, match="chemin archive interdit"):
        lifecycle.restore_backup(archive, tmp_path / "restore")


def test_cleanup_only_removes_managed_by_default(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    _mark_runtime(runtime)
    managed = runtime / "workspaces/managed"
    managed.mkdir(parents=True)
    (managed / lifecycle.MANAGED_MARKER).write_text("managed", encoding="utf-8")
    foreign = runtime / "workspaces/foreign"
    foreign.mkdir(parents=True)
    (foreign / "keep").write_text("yes", encoding="utf-8")
    (runtime / "runtime/venv").mkdir(parents=True)
    for name in ("projects", "proofs", "state", "models", "benchmarks"):
        (runtime / name).mkdir(parents=True)
    removed = lifecycle.cleanup_managed(runtime)
    assert managed in removed
    assert not managed.exists()
    assert foreign.exists()
    assert (runtime / "projects").exists()
    assert (runtime / "models").exists()


def test_cleanup_purge_is_explicit(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    _mark_runtime(runtime)
    for name in ("projects", "proofs", "state", "models", "benchmarks"):
        path = runtime / name
        path.mkdir(parents=True)
        (path / "x").write_text("x", encoding="utf-8")
    lifecycle.cleanup_managed(runtime, purge_data=True)
    for name in ("projects", "proofs", "state", "models", "benchmarks"):
        assert not (runtime / name).exists()


def test_cleanup_refuses_unmanaged_runtime(tmp_path: Path) -> None:
    runtime = tmp_path / "unmanaged"
    (runtime / "projects").mkdir(parents=True)
    with pytest.raises(ValueError, match="marqueur runtime géré absent"):
        lifecycle.cleanup_managed(runtime, purge_data=True)
    assert (runtime / "projects").exists()


def test_cleanup_refuses_filesystem_root() -> None:
    with pytest.raises(ValueError, match="runtime root / interdit"):
        lifecycle.cleanup_managed(Path("/"), purge_data=True)


def test_health_reports_all_components(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    _mark_runtime(runtime)
    for agent_id in (
        "chef-operations",
        "expert-recherche",
        "architecte-solutions",
        "ingenieur-devops",
        "ingenieur-securite",
        "ingenieur-release-forges",
        "redacteur-technique",
        "auditeur-qualite",
    ):
        workspace = runtime / "workspaces" / agent_id
        workspace.mkdir(parents=True)
        (workspace / lifecycle.MANAGED_MARKER).write_text("managed", encoding="utf-8")

    monkeypatch.setattr(lifecycle.shutil, "which", lambda name: f"/usr/bin/{name}")

    def run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        if command[-1] == "list":
            output = "\n".join(item["runtime_id"] for item in lifecycle.model_plan(ROOT))
        else:
            output = '{"runtime":"running","rpc":"ok"}'
        return SimpleNamespace(returncode=0, stdout=output, stderr="")

    monkeypatch.setattr(lifecycle.subprocess, "run", run)
    report = lifecycle.collect_health(ROOT, runtime)
    assert report.ok
    assert {check.id for check in report.checks} == {
        "repository-contracts",
        "runtime-root",
        "openclaw-cli",
        "ollama",
        "openclaw-gateway",
        "agent-workspaces",
        "model-inventory",
    }
