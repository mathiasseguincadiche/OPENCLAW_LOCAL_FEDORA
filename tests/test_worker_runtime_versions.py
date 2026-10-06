from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from clawfedora import project_worker, qualification

ROOT = Path(__file__).resolve().parents[1]


def test_ollama_neighbor_version_stops_before_openclaw_or_inference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def request(url: str) -> dict[str, Any]:
        calls.append(url)
        return {"version": "0.35.10"}

    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("No process should start with an incompatible Ollama")

    monkeypatch.setattr(qualification, "_request_json", request)
    monkeypatch.setattr(project_worker.subprocess, "run", forbidden)
    runner = project_worker.openclaw_runner(tmp_path, ROOT)
    with pytest.raises(ValueError, match="Ollama divergent"):
        runner("expert-recherche", "task", "session")
    assert calls == ["http://127.0.0.1:11434/api/version"]


def test_openclaw_neighbor_version_stops_before_loading_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def request(url: str) -> dict[str, Any]:
        calls.append(url)
        return {"version": "0.35.1"}

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert command == ["openclaw", "--version"]
        return subprocess.CompletedProcess(command, 0, "OpenClaw 2026.9.80", "")

    monkeypatch.setattr(qualification, "_request_json", request)
    monkeypatch.setattr(project_worker.subprocess, "run", run)
    runner = project_worker.openclaw_runner(tmp_path, ROOT)
    with pytest.raises(ValueError, match="OpenClaw divergent"):
        runner("expert-recherche", "task", "session")
    assert calls == ["http://127.0.0.1:11434/api/version"]
