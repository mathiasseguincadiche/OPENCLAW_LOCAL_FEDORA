"""Cooperative pause markers and progress outside the guarded project inputs."""

from __future__ import annotations

import fcntl
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any

from clawfedora.project_common import (
    assert_no_symlinks,
    now,
    read_json,
    validate_project_id,
)


def _marker(runtime: Path, project: Path) -> Path:
    project_id = validate_project_id(str(read_json(project / "project.json")["project_id"]))
    state = runtime / "state/project-control"
    assert_no_symlinks(state, label="contrôle de projet")
    return state / f"{project_id}.pause"


def cloud_pause_path(runtime: Path, project: Path) -> Path:
    """Why the cloud paused this project (content-free), next to the pause marker."""
    return _marker(runtime, project).with_suffix(".cloud-pause.json")


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
    cloud_pause_path(runtime, project).unlink(missing_ok=True)


MAX_WORKER_STATUS_BYTES = 8192


def _read_worker_status(path: Path) -> dict[str, Any]:
    """Read optional display state without turning corruption into a lock decision."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                return {"phase": "unverified"}
            raw = handle.read(MAX_WORKER_STATUS_BYTES + 1)
        if len(raw) > MAX_WORKER_STATUS_BYTES:
            return {"phase": "unverified"}
        value = json.loads(raw.decode("utf-8"))
        if isinstance(value, dict) and isinstance(value.get("phase"), str):
            return value
    except FileNotFoundError:
        return {}
    except (OSError, ValueError, RecursionError):
        pass
    return {"phase": "unverified"}


def _save_worker_status(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".worker-status-", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


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
    if path.parent.is_symlink() or path.is_symlink():
        raise ValueError("progression liée interdite")
    previous = _read_worker_status(path)
    _save_worker_status(
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
    value: dict[str, Any] = (
        {"phase": "unverified"} if path.parent.is_symlink() else _read_worker_status(path)
    )
    value["active"] = worker_active(runtime)
    if not value["active"] and value.get("phase") in {"running", "reviewing", "preparing", "chat"}:
        value["phase"] = "interrupted"
    return value
