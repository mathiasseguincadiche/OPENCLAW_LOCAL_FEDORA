from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from clawfedora import hardware_gate, lifecycle, model_identity, ollama_api
from clawfedora.hardware_gate import HardwareGateReport
from clawfedora.project_common import read_json, write_json

ROOT = Path(__file__).resolve().parents[1]
MODEL = "qwen3.5:9b-q4_K_M"


def tags(digest: str = "a" * 64, quant: str = "Q4_K_M") -> dict[str, Any]:
    return {
        "models": [
            {
                "name": MODEL,
                "digest": digest,
                "size": 6_600_000_000,
                "details": {"quantization_level": quant},
            }
        ]
    }


def test_adoption_refuses_a_changed_model_tag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(ollama_api, "request_json", lambda _url: tags())
    path = model_identity.adopt_model_lock(tmp_path, lifecycle.model_plan(ROOT))
    assert "qualification" not in read_json(path)
    monkeypatch.setattr(ollama_api, "request_json", lambda _url: tags("b" * 64))
    with pytest.raises(ValueError, match="divergent"):
        model_identity.adopt_model_lock(tmp_path, lifecycle.model_plan(ROOT))
    assert read_json(path)["models"][MODEL]["digest"] == "a" * 64


def test_wrong_quantization_cannot_pass_inventory() -> None:
    with pytest.raises(ValueError, match="quantization divergente"):
        ollama_api.model_inventory(tags(quant="Q8_0"), lifecycle.model_plan(ROOT))


def test_rebar_capability_and_small_aperture_are_not_proof(monkeypatch: pytest.MonkeyPatch) -> None:
    for output in ("Resizable BAR", "Resizable BAR\n BAR 2: current size: 256MB, supported: 16GB"):

        def run(command: list[str], result: str = output, **_kwargs: object) -> tuple[int, str]:
            if command == ["lspci", "-Dnn"]:
                return 0, "0000:03:00.0 VGA Intel Arc B580"
            assert command == ["lspci", "-s", "0000:03:00.0", "-vv"]
            return 0, result

        monkeypatch.setattr(hardware_gate, "_run", run)
        assert hardware_gate._rebar_enabled()[0] is False
    assert (
        hardware_gate.parse_rebar_current_size("BAR 2: current size: 16GB, supported: 32GB") == 16384
    )


def test_backup_includes_real_gateway_state_and_migration_preserves_source(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    (legacy / "openclaw.json").write_text('{"gateway":{"mode":"local"}}')
    (legacy / "sessions").mkdir()
    (legacy / "sessions/test.jsonl").write_text("session")
    runtime = tmp_path / "runtime"
    lifecycle.migrate_openclaw_state(runtime, legacy)
    assert (legacy / "sessions/test.jsonl").read_text() == "session"
    archive = next((runtime / "backups").glob("*.tar.gz"))
    destination = tmp_path / "restore"
    lifecycle.restore_backup(archive, destination)
    assert (destination / "state/openclaw/sessions/test.jsonl").read_text() == "session"
    assert archive.stat().st_mode & 0o777 == 0o600


def test_health_uses_full_json_inventory_and_reports_no_gpu_offload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(lifecycle.shutil, "which", lambda name: f"/usr/bin/{name}")
    from clawfedora.agents import deploy_workspaces

    deploy_workspaces(ROOT, tmp_path)
    (tmp_path / lifecycle.RUNTIME_MARKER).touch()
    write_json(
        tmp_path / "state/model-identities.json",
        {"models": {MODEL: {"digest": "a" * 64, "quantization_level": "Q4_K_M"}}},
    )
    monkeypatch.setattr(
        lifecycle, "collect_hardware_gate", lambda *_args: HardwareGateReport("gpu", (), "now")
    )
    environment = (
        "OLLAMA_NUM_PARALLEL=1 OLLAMA_MAX_LOADED_MODELS=1 OLLAMA_MAX_QUEUE=4 "
        "OLLAMA_VULKAN=1 OLLAMA_HOST=127.0.0.1:11434 "
        f"OLLAMA_MODELS={tmp_path}/models/ollama"
    )

    def command(args: list[str], _runtime: Path | None = None) -> tuple[bool, str]:
        if args[-1] == "--version":
            return True, "OpenClaw 2026.9.8"
        if "gateway" in args:
            return True, '{"rpc":{"ok":true}}'
        if args == ["getenforce"]:
            return True, "Enforcing"
        if "is-active" in args:
            return True, "active"
        return True, environment

    monkeypatch.setattr(lifecycle, "_command_json", command)

    def request(url: str, **_kwargs: Any) -> dict[str, Any]:
        if url.endswith("/api/version"):
            return {"version": "0.35.1"}
        if url.endswith("/api/tags"):
            inventory = tags()
            inventory["models"].insert(0, {"name": "x" * 1000})
            return inventory
        if url.endswith("/api/generate"):
            return {"done": True, "response": "OK"}
        return {"models": [{"name": MODEL, "size_vram": 0}]}

    monkeypatch.setattr(ollama_api, "request_json", request)
    report = lifecycle.collect_health(ROOT, tmp_path, probe=True)
    checks = {item.id: item.status for item in report.checks}
    assert checks["model-inventory"] == "PASS"
    assert checks["effective-inference-limits"] == "PASS"
    assert checks["model-gpu-probe"] == "FAIL"
    assert report.ok is False


def test_provider_name_in_generated_text_is_not_a_transport_proof() -> None:
    from clawfedora.openclaw_reply import assert_agent_success

    payload = {
        "status": "ok",
        "result": {"meta": {"provider": "cloud-provider"}},
        "payloads": [{"text": '{"provider":"ollama"}'}],
    }
    with pytest.raises(RuntimeError, match="provider=ollama"):
        assert_agent_success(payload, "ollama")


def test_backup_restores_committed_sqlite_wal_without_hot_sidecars(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    database = runtime / "state/openclaw/agents/chef-operations/sessions.db"
    database.parent.mkdir(parents=True)
    connection = sqlite3.connect(database)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE sessions (id TEXT)")
        connection.execute("INSERT INTO sessions VALUES ('committed')")
        connection.commit()
        assert database.with_name(database.name + "-wal").exists()
        archive = lifecycle.create_backup(runtime)
        restored = lifecycle.restore_backup(archive, tmp_path / "restored")
        restored_db = restored / database.relative_to(runtime)
        assert not restored_db.with_name(restored_db.name + "-wal").exists()
        with sqlite3.connect(restored_db) as check:
            assert check.execute("SELECT id FROM sessions").fetchall() == [("committed",)]
            assert check.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        check.close()
    finally:
        connection.close()
