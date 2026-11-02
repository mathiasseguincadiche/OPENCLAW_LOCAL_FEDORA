from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

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
    ]


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


def test_restore_rejects_unmanifested_extra_file(tmp_path: Path) -> None:
    archive = tmp_path / "extra.tar.gz"
    manifest = json.dumps({"schema_version": "1.0.0", "files": {}}).encode()
    extra = b"unexpected"
    with tarfile.open(archive, "w:gz") as tar:
        manifest_info = tarfile.TarInfo("BACKUP_MANIFEST.json")
        manifest_info.size = len(manifest)
        tar.addfile(manifest_info, io.BytesIO(manifest))
        extra_info = tarfile.TarInfo("state/extra.txt")
        extra_info.size = len(extra)
        tar.addfile(extra_info, io.BytesIO(extra))
    with pytest.raises(ValueError, match="contenu archive non déclaré"):
        lifecycle.restore_backup(archive, tmp_path / "restore-extra")


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
    for name in ("projects", "proofs", "state", "models"):
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
    for name in ("projects", "proofs", "state", "models"):
        path = runtime / name
        path.mkdir(parents=True)
        (path / "x").write_text("x", encoding="utf-8")
    lifecycle.cleanup_managed(runtime, purge_data=True)
    for name in ("projects", "proofs", "state", "models"):
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
    from clawfedora.core_config import AGENT_IDS

    for agent_id in AGENT_IDS:
        workspace = runtime / "workspaces" / agent_id
        workspace.mkdir(parents=True)
        (workspace / lifecycle.MANAGED_MARKER).write_text("managed", encoding="utf-8")

    monkeypatch.setattr(lifecycle.shutil, "which", lambda name, path=None: f"/usr/bin/{name}")

    from clawfedora.hardware_gate import HardwareGateReport
    from clawfedora.project_common import write_json

    model = str(lifecycle.model_plan(ROOT)[0]["runtime_id"])
    write_json(
        runtime / "state/model-identities.json",
        {"models": {model: {"digest": "a" * 64, "quantization_level": "Q4_K_M"}}},
    )

    def request(url: str, **_kwargs: object) -> dict[str, object]:
        if url.endswith("/api/version"):
            return {"version": "0.40.6"}
        return {
            "models": [
                {"name": model, "digest": "a" * 64, "details": {"quantization_level": "Q4_K_M"}}
            ]
        }

    monkeypatch.setattr(lifecycle.ollama_api, "request_json", request)
    monkeypatch.setattr(
        lifecycle, "collect_hardware_gate", lambda *_args: HardwareGateReport("gpu", (), "now")
    )

    def run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        if command[-1] == "--version":
            output = "OpenClaw 2026.10.5"
        elif command[0] == "getenforce":
            output = "Enforcing"
        elif "is-active" in command:
            output = "active"
        elif "show" in command:
            output = (
                "OLLAMA_NUM_PARALLEL=1 OLLAMA_MAX_LOADED_MODELS=1 "
                "OLLAMA_MAX_QUEUE=4 OLLAMA_VULKAN=1 OLLAMA_HOST=127.0.0.1:11434 "
                f"OLLAMA_MODELS={runtime}/models/ollama"
            )
        else:
            output = '{"rpc":{"ok":true}}'
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
        "openclaw-version",
        "ollama-version",
        "selinux-enforcing",
        "firewalld",
        "b580-vulkan",
        "effective-inference-limits",
    }


def test_backup_never_contains_the_cloud_provider_key_or_gateway_token(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    _mark_runtime(runtime)
    secrets = {
        "state/cloud/upstream.key": "sk-or-v1-" + "ab12" * 8,
        "state/cloud/gateway.token": "t" * 43,
        "state/cloud/upstream.tmp": "sk-or-v1-" + "cd34" * 8,
        "state/webui/bridge.token": "bridge-secret-token-" + "a" * 32,
        "state/webui/speech.token": "speech-secret-token-" + "b" * 32,
        "state/webui/session.key": "webui-session-secret-" + "c" * 32,
        "state/webui/webui.env": "WEBUI_SECRET_KEY=do-not-back-up\n",
        "state/chat-approvals/projet.json": "one-time-approval-should-not-survive",
    }
    kept = {
        "state/cloud/ledger-2026-10.jsonl": '{"k": "invoice", "eur": 1.0}',
        "state/cloud/activation.json": "{}",
        "state/cloud/denylist.txt": "mon-employeur",
        "state/a.json": "state",
    }
    for relative, content in {**secrets, **kept}.items():
        path = runtime / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    archive = lifecycle.create_backup(runtime)
    with tarfile.open(archive) as tar:
        names = set(tar.getnames())
        blob = b"".join(
            tar.extractfile(member).read()  # type: ignore[union-attr]
            for member in tar.getmembers()
            if member.isfile()
        )
    assert names.isdisjoint(secrets) and set(kept) <= names
    assert b"sk-or-v1-" not in blob
    assert b"bridge-secret-token" not in blob
    assert b"speech-secret-token" not in blob
    assert b"webui-session-secret" not in blob
    assert b"WEBUI_SECRET_KEY" not in blob
    assert b"one-time-approval-should-not-survive" not in blob
    restored = tmp_path / "restored"
    lifecycle.restore_backup(archive, restored)
    assert not (restored / "state/cloud/upstream.key").exists()
    assert (restored / "state/cloud/ledger-2026-10.jsonl").is_file()
    assert not (restored / "state/webui/bridge.token").exists()
    assert not (restored / "state/webui/webui.env").exists()


def _purge_layout(tmp_path: Path) -> Path:
    runtime = tmp_path / "runtime"
    _mark_runtime(runtime)
    for name in ("projects", "proofs", "state", "models/ollama/blobs"):
        path = runtime / name
        path.mkdir(parents=True)
        (path / "x").write_text("x", encoding="utf-8")
    return runtime


def _ollama_owned_models(runtime: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate models/ollama owned by the ollama account (0750), even when run as root."""
    models = runtime / "models/ollama"
    real = lifecycle.os.access

    def access(path: Any, mode: int, *args: Any, **kwargs: Any) -> bool:
        target = Path(path)
        if target == models or models in target.parents:
            return False
        return real(path, mode, *args, **kwargs)

    monkeypatch.setattr(lifecycle.os, "access", access)


def test_purge_checks_every_permission_before_the_first_removal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A07: projects and state used to be gone before rmtree(models) failed."""
    runtime = _purge_layout(tmp_path)
    _ollama_owned_models(runtime, monkeypatch)
    with pytest.raises(ValueError, match="rien n'a été supprimé.*10_uninstall.sh"):
        lifecycle.cleanup_managed(runtime, purge_data=True)
    for name in ("projects", "proofs", "state", "models/ollama/blobs"):
        assert (runtime / name / "x").exists()


def test_purge_check_leaves_models_to_the_bounded_privileged_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _purge_layout(tmp_path)
    _ollama_owned_models(runtime, monkeypatch)
    planned = lifecycle.cleanup_managed(
        runtime, purge_data=True, check_only=True, models_by_root=True
    )
    assert runtime / "projects" in planned
    assert all((runtime / name / "x").exists() for name in ("projects", "state"))  # nothing removed
    with pytest.raises(ValueError, match="rien n'a été supprimé"):
        lifecycle.cleanup_managed(runtime, purge_data=True, check_only=True)


def test_uninstall_purge_checks_then_stops_ollama_then_purges() -> None:
    text = (ROOT / "scripts/linux/10_uninstall.sh").read_text(encoding="utf-8")
    check = text.index("ops cleanup --check --purge-data --models-by-root")
    stop = text.index("sudo systemctl stop ollama.service")
    remove = text.index('sudo rm -rf --one-file-system -- "$MODELS"')
    purge = text.index("ops cleanup --apply --purge-data")
    assert check < stop < remove < purge
    assert 'MODELS="$RUNTIME_ROOT/models/ollama"' in text
    assert "systemctl is-active --quiet ollama.service" in text
    assert "CLEANUP_KEEPS" in (ROOT / "src/clawfedora/ops_cli.py").read_text(encoding="utf-8")
