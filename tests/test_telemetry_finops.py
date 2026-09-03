from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from clawfedora.finops import append_cost_event, summarize
from clawfedora.telemetry import TelemetryEvent, emit_event, read_events

ROOT = Path(__file__).resolve().parents[1]


def _core_sandbox(tmp_path: Path) -> Path:
    (tmp_path / "config/core").mkdir(parents=True)
    for name in ("telemetry_policy.yaml", "budget_policy.yaml"):
        shutil.copy(ROOT / "config/core" / name, tmp_path / "config/core" / name)
    return tmp_path


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


def test_telemetry_reserved_fields_cannot_override_event_or_time() -> None:
    event = TelemetryEvent(
        event="real",
        at="real-time",
        fields={"event": "forged", "at": "forged-time", "status": "PASS"},
    )
    payload = event.payload()
    assert payload["event"] == "real"
    assert payload["at"] == "real-time"


def test_telemetry_path_is_confined_to_runtime(tmp_path: Path) -> None:
    root = _core_sandbox(tmp_path / "repo")
    path = root / "config/core/telemetry_policy.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["retention"]["relative_path"] = "../escape.jsonl"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    with pytest.raises(ValueError, match="relative_path interdit"):
        emit_event(root, tmp_path / "runtime", "x", status="PASS")


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
        "releases_eur": 0.0,
        "net_exposure_eur": 0.35,
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


def test_finops_path_is_confined_to_runtime(tmp_path: Path) -> None:
    root = _core_sandbox(tmp_path / "repo")
    path = root / "config/core/budget_policy.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["ledger"]["relative_path"] = "/tmp/escape.jsonl"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    with pytest.raises(ValueError, match="relative_path interdit"):
        append_cost_event(
            root,
            tmp_path / "runtime",
            event="reservation",
            amount_eur=0.25,
            reason="explicit",
            provider="example",
        )


def test_finops_daily_limit_is_enforced(tmp_path: Path) -> None:
    append_cost_event(
        ROOT,
        tmp_path,
        event="reservation",
        amount_eur=0.75,
        reason="approved",
        provider="example",
    )
    with pytest.raises(ValueError, match="limite daily"):
        append_cost_event(
            ROOT,
            tmp_path,
            event="reservation",
            amount_eur=0.30,
            reason="would exceed",
            provider="example",
        )


def test_empty_finops_summary(tmp_path: Path) -> None:
    assert summarize(ROOT, tmp_path) == {
        "events": 0,
        "charges_eur": 0.0,
        "reservations_eur": 0.0,
        "refunds_eur": 0.0,
        "releases_eur": 0.0,
        "net_exposure_eur": 0.0,
    }
