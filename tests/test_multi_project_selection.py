"""Regression: independent multi-project selection with one shared inference worker."""

from __future__ import annotations

from pathlib import Path

import pytest

from clawfedora import chat_projects
from clawfedora.project_intake import create_project
from clawfedora.project_worker import worker_lock

ROOT = Path(__file__).resolve().parents[1]


def test_four_projects_are_separately_stored_and_selected_per_chat(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    request = tmp_path / "request.md"
    request.write_text("Étudier une infrastructure DevOps.", encoding="utf-8")
    identifiers = [f"atelier-{n}" for n in range(1, 5)]
    for index, identifier in enumerate(identifiers, start=1):
        path = create_project(
            ROOT, runtime, identifier, f"Projet {index}", intake_items=[request],
        )
        assert path.name == identifier
        assert (path / "project.json").is_file()

    listed = chat_projects.list_projects(ROOT, runtime)
    assert {entry["id"] for entry in listed} == set(identifiers)
    for identifier in identifiers:
        selected, seen = chat_projects.thread_state([
            {"role": "assistant",
             "content": chat_projects.model_marker(identifier) + "\n\nProjet sélectionné"},
        ])
        assert selected == identifier and seen == {identifier}
        assert chat_projects.open_project(runtime, identifier) is not None


def test_switching_projects_in_one_thread_keeps_selection_and_history_distinct() -> None:
    first = "atelier-1"
    second = "atelier-2"
    messages = [
        {"role": "assistant", "content": chat_projects.model_marker(first) + "\n\nRéponse"},
        {"role": "assistant", "content": chat_projects.model_marker(second) + "\n\nRéponse"},
    ]
    assert chat_projects.thread_state(messages) == (second, {first, second})
    messages.append({
        "role": "assistant", "content": chat_projects.NO_PROJECT + chat_projects.BRIDGE_SUFFIX +
        "\n\nProjet désélectionné",
    })
    assert chat_projects.thread_state(messages) == (None, {first, second})


def test_worker_lock_stays_exclusive_for_all_projects(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    with (
        worker_lock(runtime),
        pytest.raises(ValueError, match="déjà actif"),
        worker_lock(runtime),
    ):
        pytest.fail("A second inference must not run in parallel on the B580")
