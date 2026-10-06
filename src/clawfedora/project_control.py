"""Cooperative pause markers and progress outside the guarded project inputs."""

from __future__ import annotations

import fcntl
import os
from pathlib import Path
from typing import Any

from clawfedora.project_common import (
    assert_no_symlinks,
    now,
    read_json,
    validate_project_id,
    write_json,
)


def _marker(runtime: Path, project: Path) -> Path:
    project_id = validate_project_id(str(read_json(project / "project.json")["project_id"]))
    state = runtime / "state/project-control"
    assert_no_symlinks(state, label="contrôle de projet")
    return state / f"{project_id}.pause"


def is_paused(runtime: Path, project: Path) -> bool:
    return _marker(runtime, project).exists()


def request_pause(runtime: Path, project: Path) -> None:
    if read_json(project / "project.json")["status"] not in {"ASSIGNED", "IN_PROGRESS"}:
        raise ValueError("pause: plan assigné ou travail en cours requis")
    marker = _marker(runtime, project)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch(mode=0o600)


def clear_pause(runtime: Path, project: Path) -> None:
    _marker(runtime, project).unlink(missing_ok=True)


def write_progress(
    runtime: Path,
    project: Path | None,
    phase: str,
    *,
    task: str = "",
    role: str = "",
    session: str = "",
) -> None:
    path = runtime / "state/worker-status.json"
    if path.is_symlink():
        raise ValueError("progression liée interdite")
    previous = read_json(path) if path.is_file() else {}
    write_json(
        path,
        {
            "project_id": read_json(project / "project.json")["project_id"] if project else "",
            "phase": phase,
            "task_id": task,
            "role": role,
            "session_id": session,
            "pid": os.getpid(),
            "updated_at": now(),
            "started_at": previous.get("started_at")
            if previous.get("session_id") == session and session
            else now(),
        },
    )


def worker_active(runtime: Path) -> bool:
    path = runtime / "state/worker.lock"
    if not path.is_file():
        return False
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(handle, fcntl.LOCK_UN)
    return False


def progress(runtime: Path) -> dict[str, Any]:
    path = runtime / "state/worker-status.json"
    value = read_json(path) if path.is_file() and not path.is_symlink() else {}
    value["active"] = worker_active(runtime)
    if not value["active"] and value.get("phase") in {"running", "reviewing", "preparing", "chat"}:
        value["phase"] = "interrupted"
    return value
