from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from test_daily_worker import planned as planned
from test_dashboard import request
from test_dashboard import server as server

from clawfedora.dashboard import DashboardServer
from clawfedora.mentor import context, copy_profile, profile, save_profile
from clawfedora.project_common import read_json
from clawfedora.project_worker import worker_lock
from clawfedora.webui_bridge import MODEL_IDS, chat_prompt


def test_personal_notes_are_bounded_approved_and_shared_with_live_project(
    planned: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    runtime, project = planned
    value = save_profile(
        runtime,
        {
            "human_approved": True,
            "background": "Administration Linux",
            "project_id": project.name,
            "skill_acquired": True,
        },
    )
    assert value["skill_acquired"] is False and value["origin"] == "human"
    assert "Administration Linux" in context(runtime)
    assert '"status": "ASSIGNED"' in context(runtime)
    snapshot = tmp_path / "snapshot"
    copy_profile(runtime, snapshot)
    assert read_json(snapshot / "context/learning/mentor.json") == profile(runtime)
    assert context(tmp_path / "empty") == ""


@pytest.mark.parametrize(
    "patch",
    [
        {"human_approved": False},
        {"background": "x" * 501},
        {"focus": []},
        {"project_id": "../escape"},
        {"project_id": "unknown"},
        {"project_id": 3},
    ],
)
def test_invalid_notes_leave_no_state(tmp_path: Path, patch: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        save_profile(tmp_path, {"human_approved": True, **patch})
    assert not (tmp_path / "state/mentor.json").exists()


def test_profile_rejects_linked_file_and_corrupt_state(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir()
    outside = tmp_path / "outside"
    outside.write_text("{}")
    (state / "mentor.json").symlink_to(outside)
    with pytest.raises(ValueError):
        profile(tmp_path)
    with pytest.raises(ValueError):
        save_profile(tmp_path, {"human_approved": True})
    assert outside.read_text() == "{}"
    (state / "mentor.json").unlink()
    (state / "mentor.json").write_text('{"background": []}')
    with pytest.raises(ValueError, match="invalide"):
        profile(tmp_path)


def test_notes_endpoint_requires_origin_approval_and_worker_lock(server: DashboardServer) -> None:
    data = {"background": "Linux", "human_approved": True}
    assert request(server, "/api/mentor", data, origin=False)[0] == 403
    assert request(server, "/api/mentor", {**data, "human_approved": False})[0] == 400
    with worker_lock(server.runtime):
        assert request(server, "/api/mentor", data)[0] == 400
    assert request(server, "/api/mentor", data)[0] == 200
    assert request(server, "/api/status")[1]["mentor"]["background"] == "Linux"


def test_long_history_keeps_recent_context_and_declares_omissions() -> None:
    messages = [
        {"role": "user", "content": "OLD-MESSAGE" + "é" * 1500},
        {"role": "assistant", "content": "SECOND" + "é" * 1500},
        {"role": "user", "content": "LATEST-QUESTION"},
    ]
    _role, prompt = chat_prompt({"model": MODEL_IDS[0], "messages": messages})
    assert "OLD-MESSAGE" not in prompt and "LATEST-QUESTION" in prompt
    assert "1 anciens messages" in prompt
    with pytest.raises(ValueError):
        chat_prompt({"model": MODEL_IDS[0], "messages": messages * 100})
