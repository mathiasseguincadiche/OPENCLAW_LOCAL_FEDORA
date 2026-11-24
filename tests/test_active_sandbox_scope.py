"""Executable agent tools are confined to the active DevOps task."""
from __future__ import annotations

from pathlib import Path

import pytest

from clawfedora import project_control
from clawfedora.agent_tools import _require_active_sandbox_scope


def test_only_current_devops_worker_scope_is_allowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = {
        "active": True, "phase": "running", "role": "ingenieur-devops",
        "project_id": "p", "task_id": "t", "session_id": "s",
    }
    monkeypatch.setattr(project_control, "progress", lambda _: state)
    _require_active_sandbox_scope(tmp_path, "projects/p/t/s")
    with pytest.raises(ValueError, match="tâche DevOps active"):
        _require_active_sandbox_scope(tmp_path, "projects/p/t/old")
    for key, invalid in (("active", False), ("phase", "chat"), ("role", "chef-operations")):
        original = state[key]
        state[key] = invalid
        with pytest.raises(ValueError, match="tâche DevOps active"):
            _require_active_sandbox_scope(tmp_path, "projects/p/t/s")
        state[key] = original
