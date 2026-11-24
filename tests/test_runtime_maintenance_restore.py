"""Cross-component regressions: maintenance exclusion and usable restored state."""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest

from clawfedora import atelier_chat, cli, lifecycle, model_identity, ops_cli, performance_reports
from clawfedora.project_worker import worker_lock

ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "scripts/linux/lib/runtime.sh"


def _runtime(tmp_path: Path) -> Path:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / lifecycle.RUNTIME_MARKER).touch(mode=0o600)
    return runtime


def test_restore_keeps_native_chat_and_gpu_report_usable(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    (runtime / "state").mkdir(mode=0o700)
    chat = atelier_chat.create(runtime, None, "chef-operations")
    performance_reports.save(runtime, {
        "qwen-max": {
            "model_alias": "qwen-max", "cloud_used": False, "config_modified": False,
            "near_limit_requested": False,
            "results": [{
                "context_tokens": 8192, "verdict": "FULL_GPU",
                "near_limit_qualified": False, "allocated_context_tokens": 8192,
                "prompt_tokens": 4000, "prompt_fill_pct": 48.8,
                "gpu_share_pct": 100.0, "resident_gib": 8.0, "resident_vram_gib": 8.0,
            }],
        },
    })
    archive = lifecycle.create_backup(runtime)
    target = tmp_path / "restored"
    target.mkdir(mode=0o755)
    lifecycle.restore_backup(archive, target)
    for path in (target, *(p for p in target.rglob("*") if p.is_dir())):
        assert stat.S_IMODE(path.stat().st_mode) == 0o700
    assert atelier_chat.read(target, chat["id"]) == chat
    assert performance_reports.view(target)["status"] == "MEASURED"


def test_shell_and_python_share_nontruncating_worker_lock(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    command = [
        "bash", "-c",
        'source "$1"; claw_runtime_root() { printf "%s\\n" "$2"; }; '
        'root="$2"; claw_runtime_root() { printf "%s\\n" "$root"; }; '
        'claw_require_storage() { :; }; claw_lock_worker; claw_lock_worker; '
        'test "$(stat -c %a "$root/state/worker.lock")" = 600',
        "_", str(SHELL), str(runtime),
    ]
    with worker_lock(runtime):
        lock = runtime / "state/worker.lock"
        lock.write_text("preserved")
        failed = subprocess.run(command, capture_output=True, text=True, timeout=10)
        assert failed.returncode != 0
        assert "active" in failed.stderr
        assert lock.read_text() == "preserved"
    completed = subprocess.run(command, capture_output=True, text=True, timeout=10)
    assert completed.returncode == 0, completed.stderr
    assert lock.read_text() == "preserved"
    lock.unlink()
    os.mkfifo(lock, 0o600)
    refused = subprocess.run(command, capture_output=True, text=True, timeout=10)
    assert refused.returncode != 0 and "non régulier" in refused.stderr
    with pytest.raises(ValueError, match="non régulier"), worker_lock(runtime):
        pytest.fail("special lock accepted")


@pytest.mark.parametrize("action", ["agents", "models", "models-lock"])
def test_mutating_cli_refuses_active_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, action: str,
) -> None:
    runtime = _runtime(tmp_path)

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("maintenance ran while a worker was active")

    monkeypatch.setattr(cli, "require_storage", lambda *_args: None)
    monkeypatch.setattr(ops_cli, "require_storage", lambda *_args: None)
    monkeypatch.setattr(cli, "deploy_workspaces", forbidden)
    monkeypatch.setattr(ops_cli, "_models", forbidden)
    monkeypatch.setattr(model_identity, "adopt_model_lock", forbidden)
    with worker_lock(runtime):
        if action == "agents":
            assert cli.main([
                "--root", str(ROOT), "agents", "deploy", "--runtime-root", str(runtime),
            ]) == 2
        else:
            assert ops_cli.main([
                "--root", str(ROOT), "--runtime-root", str(runtime), action, "--apply",
            ]) == 2


def test_bootstrap_and_maintenance_entrypoints_use_private_shared_state() -> None:
    scripts = ROOT / "scripts/linux"
    bootstrap = (scripts / "00_bootstrap.sh").read_text()
    assert 'as_target install -d -m 0700 "$RUNTIME_ROOT/state"' in bootstrap
    for name in (
        "03_configure_openclaw.sh", "06_install.sh", "11_daily_profile.sh",
        "12_upgrade.sh", "21_atelier.sh",
    ):
        source = (scripts / name).read_text()
        assert "claw_lock_worker" in source, name
