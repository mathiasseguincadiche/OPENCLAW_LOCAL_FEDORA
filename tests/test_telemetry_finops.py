from __future__ import annotations

from pathlib import Path

import pytest

from clawfedora.finops import append_cost_event, summarize
from clawfedora.telemetry import emit_event, read_events

ROOT = Path(__file__).resolve().parents[1]


def test_telemetry_is_local_append_only_and_filtered(tmp_path: Path) -> None:
    path = emit_event(
        ROOT,
        tmp_path,
        "task.completed",
        project_id="project-1",
        task_id="task-1",
        agent_id="ingenieur-devops",
        phase="EXECUTE",
        status="PASS",
        duration_ms=123,
        model_alias="devstral-devops",
        backend_id="ollama-vulkan",
    )
    assert path == tmp_path / "state/telemetry/events.jsonl"
    rows = read_events(ROOT, tmp_path)
    assert len(rows) == 1
    assert rows[0]["event"] == "task.completed"
    assert "prompt" not in rows[0]


def test_telemetry_rejects_unknown_or_sensitive_fields(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="champs non autorisés"):
        emit_event(ROOT, tmp_path, "x", arbitrary="value")
    with pytest.raises(ValueError, match="contenu sensible"):
        emit_event(ROOT, tmp_path, "x", status="password=secret")
    with pytest.raises(ValueError, match="event vide"):
        emit_event(ROOT, tmp_path, "   ", status="PASS")


def test_telemetry_limit_is_validated(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="limit"):
        read_events(ROOT, tmp_path, limit=0)


def test_finops_append_and_summary(tmp_path: Path) -> None:
    reservation = append_cost_event(
        ROOT,
        tmp_path,
        event="reservation",
        amount_eur=0.25,
        reason="explicit research escalation",
        provider="example-cloud",
        project_id="project-1",
    )
    assert reservation["amount_eur"] == 0.25
    append_cost_event(
        ROOT,
        tmp_path,
        event="charge",
        amount_eur=0.12,
        reason="approved research request",
        provider="example-cloud",
    )
    append_cost_event(
        ROOT,
        tmp_path,
        event="refund",
        amount_eur=0.02,
        reason="provider correction",
        provider="example-cloud",
    )
    summary = summarize(ROOT, tmp_path)
    assert summary == {
        "events": 3,
        "charges_eur": 0.12,
        "reservations_eur": 0.25,
        "refunds_eur": 0.02,
    }


def test_finops_is_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="montant négatif"):
        append_cost_event(
            ROOT,
            tmp_path,
            event="charge",
            amount_eur=-1,
            reason="invalid",
            provider="provider",
        )
    with pytest.raises(ValueError, match="raison obligatoire"):
        append_cost_event(
            ROOT,
            tmp_path,
            event="charge",
            amount_eur=1,
            reason="",
            provider="provider",
        )
    with pytest.raises(ValueError, match="événement inconnu"):
        append_cost_event(
            ROOT,
            tmp_path,
            event="invalid",
            amount_eur=1,
            reason="x",
            provider="provider",
        )


def test_empty_finops_summary(tmp_path: Path) -> None:
    assert summarize(ROOT, tmp_path) == {
        "events": 0,
        "charges_eur": 0.0,
        "reservations_eur": 0.0,
        "refunds_eur": 0.0,
    }
