"""A04: backup and repair take the worker lock; a locking parent's descriptor is reused.

Before the fix, a backup archive was created while the lock was held by a generation: the
projects, state and workspaces in it could come from different instants.
"""

from __future__ import annotations

import fcntl
import os
from pathlib import Path

import pytest

from clawfedora.lifecycle import RUNTIME_MARKER, create_backup
from clawfedora.project_worker import maintenance_lock, worker_lock

ROOT = Path(__file__).resolve().parents[1]


def _runtime(tmp_path: Path) -> Path:
    runtime = tmp_path / "runtime"
    (runtime / "projects/demo").mkdir(parents=True)
    (runtime / "projects/demo/project.json").write_text("{}")
    (runtime / RUNTIME_MARKER).write_text("managed")
    return runtime


def test_backup_is_refused_while_a_generation_holds_the_lock(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    with (
        worker_lock(runtime),
        pytest.raises(ValueError, match="déjà actif"),
        maintenance_lock(runtime),
    ):
        create_backup(runtime)
    assert not list(runtime.rglob("*.tar.gz*"))  # nothing archived, not even a partial file


def test_backup_runs_and_releases_the_lock_when_idle(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    with maintenance_lock(runtime):
        archive = create_backup(runtime)
        with pytest.raises(ValueError, match="déjà actif"), worker_lock(runtime):
            pass  # no generation may start during the backup
    assert archive.is_file()
    with worker_lock(runtime):  # released afterwards
        pass


def test_a_child_reuses_the_descriptor_of_its_locking_parent(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    (runtime / "state").mkdir()
    parent = os.open(runtime / "state/worker.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(parent, fcntl.LOCK_EX)  # what claw_lock_worker / 12_upgrade hold
        with maintenance_lock(runtime, inherited_fd=parent):
            create_backup(runtime)  # no deadlock on the parent's own lock
        with pytest.raises(ValueError, match="déjà actif"), worker_lock(runtime):
            pass  # the parent still owns it after the child step
    finally:
        os.close(parent)


def test_an_unrelated_descriptor_is_not_mistaken_for_the_lock(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    other = os.open(tmp_path / "unrelated", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        with (
            worker_lock(runtime),
            pytest.raises(ValueError, match="déjà actif"),
            maintenance_lock(runtime, inherited_fd=other),
        ):
            pass
    finally:
        os.close(other)


def test_backup_and_repair_entrypoints_take_the_lock_first() -> None:
    backup = (ROOT / "scripts/linux/08_backup_restore.sh").read_text(encoding="utf-8")
    branch = backup[backup.index("  backup)"):backup.index("  restore)")]
    assert branch.index("claw_lock_worker") < branch.index("run_ops backup")
    repair = (ROOT / "scripts/linux/09_repair.sh").read_text(encoding="utf-8")
    assert repair.index("claw_lock_worker") < repair.index('08_backup_restore.sh" backup')
    assert repair.index("claw_lock_worker") < repair.index('03_configure_openclaw.sh" --apply')
    cli = (ROOT / "src/clawfedora/ops_cli.py").read_text(encoding="utf-8")
    assert cli.index("with maintenance_lock(runtime_root):") < cli.index(
        "path = create_backup(runtime_root, output)"
    )
