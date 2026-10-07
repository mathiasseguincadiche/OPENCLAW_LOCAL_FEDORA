from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

import pytest

from clawfedora import gpu_telemetry, hardware_gate, lifecycle, model_identity, qualification
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


def test_adoption_does_not_qualify_or_accept_changed_tag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(model_identity, "_request_json", lambda _url: tags())
    path = model_identity.adopt_model_lock(tmp_path, lifecycle.model_plan(ROOT))
    assert read_json(path)["qualification"] == "PENDING"
    monkeypatch.setattr(model_identity, "_request_json", lambda _url: tags("b" * 64))
    with pytest.raises(ValueError, match="divergent"):
        model_identity.adopt_model_lock(tmp_path, lifecycle.model_plan(ROOT))
    assert read_json(path)["models"][MODEL]["digest"] == "a" * 64


def test_wrong_quantization_cannot_pass_inventory() -> None:
    with pytest.raises(ValueError, match="quantization divergente"):
        qualification._model_inventory(tags(quant="Q8_0"), lifecycle.model_plan(ROOT))


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


def test_xe_memory_selects_b580_and_deduplicates_shared_fd(tmp_path: Path) -> None:
    def fd(pid: int, number: int, driver: str, slot: str, client: str, memory: str) -> None:
        path = tmp_path / str(pid) / "fdinfo" / str(number)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"drm-driver: {driver}\ndrm-pdev: {slot}\n"
            f"drm-client-id: {client}\ndrm-memory-vram0: {memory}\n"
        )

    fd(1, 3, "amdgpu", "0000:10:00.0", "1", "8000 MiB")
    fd(2, 3, "xe", "0000:03:00.0", "9", "1048576 KiB")
    fd(2, 4, "xe", "0000:03:00.0", "9", "1048576 KiB")
    fd(3, 3, "xe", "0000:03:00.0", "10", "512 MiB")
    assert gpu_telemetry.xe_vram_mib("0000:03:00.0", tmp_path) == 1536
    with pytest.raises(ValueError, match="non observable"):
        gpu_telemetry.xe_vram_mib("0000:99:00.0", tmp_path)


def test_sampler_preserves_peak_during_inference() -> None:
    values = [100.0, 900.0, 200.0]
    observed = threading.Event()

    def sample() -> float:
        value = values.pop(0) if values else 200.0
        if value == 900:
            observed.set()
        return value

    with gpu_telemetry.PeakSampler(sample, interval=0.001) as sampler:
        assert observed.wait(1)
    assert sampler.value() == 900
    assert sampler.samples >= 3


def test_model_json_checks_reject_empty_or_misleading_answers() -> None:
    checks = [
        {"type": "json_equals", "expected": {"tool": "read_file", "arguments": {"path": "README.md"}}}
    ]
    assert (
        qualification.run_checks('{"tool":"exec","arguments":{"path":"README.md"}}', checks)[0]
        is False
    )
    checks = [{"type": "json_nonempty_lists", "keys": ["objectives"]}]
    assert qualification.run_checks('{"objectives":[]}', checks)[0] is False


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
        lifecycle, "collect_hardware_gate", lambda *_args: HardwareGateReport("L3", (), "now")
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

    monkeypatch.setattr(lifecycle, "_request_json", request)
    report = lifecycle.collect_health(ROOT, tmp_path, probe=True)
    checks = {item.id: item.status for item in report.checks}
    assert checks["model-inventory"] == "PASS"
    assert checks["effective-inference-limits"] == "PASS"
    assert checks["model-gpu-probe"] == "FAIL"
    assert report.ok is False


def test_synthetic_golden_report_cannot_authorize_release() -> None:
    from clawfedora.release_readiness import _validate_l7

    cfg = {
        "required_verdict": "PASS",
        "required_golden_projects": 5,
        "required_representative_projects": 1,
    }
    payload = {
        "schema_version": "1.0.0",
        "gate": "L7",
        "verdict": "PASS",
        "execution_mode": "synthetic",
        "ai_runtime_exercised": False,
        "golden_projects_pass": 5,
        "representative_projects_pass": 1,
        "telemetry": {"local_only": True, "events": 6},
    }
    assert any("synthétique" in failure for failure in _validate_l7(payload, cfg))


def test_provider_name_in_generated_text_is_not_a_transport_proof() -> None:
    from clawfedora.openclaw_e2e import _assert_agent_success

    payload = {
        "status": "ok",
        "result": {"meta": {"provider": "cloud-provider"}},
        "payloads": [{"text": '{"provider":"ollama"}'}],
    }
    with pytest.raises(RuntimeError, match="provider=ollama"):
        _assert_agent_success(payload, "ollama")


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
