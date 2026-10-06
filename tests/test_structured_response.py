from __future__ import annotations

import io
import json
from typing import Any

import pytest

from clawfedora import structured_response
from clawfedora.structured_response import parse_response, repair_response, response_schema


def task_schema() -> dict[str, Any]:
    return response_schema('task\n{"expected_outputs":["deliverables/task-one/file.md"]}')


@pytest.mark.parametrize(
    "value",
    [
        {"files": {}},
        {"files": {"../escape": "text"}, "summary": "ok"},
        {"files": {"deliverables/task-one/file.md": ""}, "summary": "ok"},
    ],
)
def test_task_schema_rejects_missing_wrong_or_empty_outputs(value: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        parse_response(json.dumps(value), task_schema())


def test_local_repair_uses_schema_same_model_and_no_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    value = {"files": {"deliverables/task-one/file.md": "Repaired original content"}, "summary": "ok"}
    calls = []

    def request(req: Any, **kwargs: Any) -> io.BytesIO:
        calls.append(req.full_url)
        payload = json.loads(req.data)
        assert req.full_url == "http://127.0.0.1:11434/api/chat"
        assert payload["format"] == task_schema() and payload["model"] == "qwen3.5:9b-q4_K_M"
        assert payload["think"] is False and "tools" not in payload and kwargs["timeout"] == 120
        return io.BytesIO(
            json.dumps(
                {"done": True, "done_reason": "stop", "message": {"content": json.dumps(value)}}
            ).encode()
        )

    monkeypatch.setattr(structured_response, "urlopen", request)
    assert repair_response("bad JSON", task_schema()) == value and len(calls) == 1


def test_auditor_schema_requires_every_criterion() -> None:
    schema = response_schema('Session indépendante\n{"task-one":["a","b"]}')
    value = {
        "verdict": "PASS",
        "findings": [],
        "criteria": {"task-one": [{"passed": True, "evidence": "x"}]},
    }
    with pytest.raises(ValueError):
        parse_response(json.dumps(value), schema)


def test_overlong_repair_is_rejected_without_inference() -> None:
    with pytest.raises(ValueError, match="trop longue"):
        repair_response("x" * 24001, task_schema())
