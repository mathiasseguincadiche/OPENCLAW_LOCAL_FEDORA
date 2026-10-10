"""The workshop uses the cloud only for approved projects and pauses visibly, never silently."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest
from test_daily_worker import planned as planned

from clawfedora import project_cloud
from clawfedora.cloud_budget import load_ledger
from clawfedora.cloud_state import CLOUD_STATE, write_activation
from clawfedora.project_cloud import CloudPause, project_runner
from clawfedora.project_common import write_json
from clawfedora.project_control import is_paused, progress
from clawfedora.project_worker import review_project, run_project_tasks

ROOT = Path(__file__).resolve().parents[1]
BOTH = {"privacy_filter": "2026-10-09T10:00:00Z", "budget_guard": "2026-10-09T10:00:00Z"}


class Base:
    """The OpenClaw runner stand-in: records the route and imitates the gateway log."""

    def __init__(self, runtime: Path) -> None:
        self.runtime = runtime
        self.routes: list[str] = []
        self.cloud_events: list[dict[str, Any]] = [
            {"decision": "forwarded"}, {"decision": "completed"}]
        self.cloud_error: Exception | None = None
        self.spend_usd = 0.0004

    def event(self, **record: Any) -> None:
        directory = self.runtime / CLOUD_STATE
        directory.mkdir(parents=True, exist_ok=True)
        record.setdefault("at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        with (directory / "events.jsonl").open("a") as handle:
            handle.write(json.dumps(record) + "\n")

    def __call__(
        self, role: str, prompt: str, session: str, *, route: str = "local"
    ) -> dict[str, Any]:
        self.routes.append(route)
        model = "deepseek/deepseek-v4.1-flash" if route == "cloud" else "qwen3.5:9b"
        write_json(
            self.runtime / "state/model-runs" / f"{session}.json",
            {"session_id": session, "route": route, "provider": "x", "model": model},
        )
        if route == "cloud":
            for record in self.cloud_events:
                self.event(**record)
            if self.cloud_error:
                raise self.cloud_error
            ledger = load_ledger(self.runtime, ROOT)
            reservation = ledger.reserve(input_tokens=100, max_output_tokens=100)
            reservation.settle({"cost": self.spend_usd}, "ok")
        task = json.loads(prompt.split("\n", 1)[1])
        return {"files": {task["expected_outputs"][0]: f"Livrable {route}"}, "summary": route}


@pytest.fixture
def workshop(planned: tuple[Path, Path]) -> tuple[Path, Path, Base]:
    runtime, project = planned
    (runtime / "state").mkdir(exist_ok=True)
    return runtime, project, Base(runtime)


def activate(runtime: Path) -> None:
    write_activation(runtime, BOTH)


def approve(runtime: Path, project: Path) -> None:
    activate(runtime)
    project_cloud.grant(ROOT, runtime, project, acknowledged=True)


def run(runtime: Path, project: Path, base: Base, **options: Any) -> list[dict[str, Any]]:
    runner = project_runner(ROOT, runtime, project, base=base)
    return run_project_tasks(ROOT, runtime, project, runner=runner, **options)


# -- consent ------------------------------------------------------------------------
def test_without_an_approval_the_project_stays_local_and_nothing_changes(
    workshop: tuple[Path, Path, Base],
) -> None:
    runtime, project, base = workshop
    activate(runtime)  # an activated cloud is not an approved project
    results = run(runtime, project, base)
    assert [r["status"] for r in results] == ["PASS", "PASS"] and base.routes == ["local", "local"]
    assert project_cloud.consent_state(ROOT, runtime, project)["state"] == "none"


def test_approval_needs_the_activated_cloud_and_an_explicit_acknowledgement(
    workshop: tuple[Path, Path, Base],
) -> None:
    runtime, project, _ = workshop
    with pytest.raises(ValueError, match="cloud indisponible"):
        project_cloud.grant(ROOT, runtime, project, acknowledged=True)
    activate(runtime)
    for refused in (False, None, "oui", 1):
        with pytest.raises(ValueError, match="accord explicite"):
            project_cloud.grant(ROOT, runtime, project, acknowledged=refused)  # type: ignore[arg-type]
    assert not project_cloud.consent_path(runtime, project).exists()


def test_the_approval_is_private_content_free_and_bound_to_this_project(
    workshop: tuple[Path, Path, Base],
) -> None:
    runtime, project, _ = workshop
    approve(runtime, project)
    path = project_cloud.consent_path(runtime, project)
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    record = json.loads(path.read_text())
    assert record["project_id"] == "daily-project" and record["scope"] == "cloud-deepseek"
    assert "Comparer deux architectures" not in path.read_text()
    assert project_cloud.consent_state(ROOT, runtime, project)["state"] == "granted"


def test_an_approved_project_runs_in_the_cloud_with_model_and_cost_recorded(
    workshop: tuple[Path, Path, Base],
) -> None:
    runtime, project, base = workshop
    approve(runtime, project)
    results = run(runtime, project, base)
    assert [r["status"] for r in results] == ["PASS", "PASS"] and base.routes == ["cloud", "cloud"]
    view = project_cloud.view(ROOT, runtime, project)
    assert view["calls_cloud"] == 2 and view["calls_local"] == 0
    assert view["models"] == {"cloud · deepseek/deepseek-v4.1-flash": 2}
    expected = 2 * 0.0004 * load_ledger(runtime, ROOT).eur_per_usd
    assert view["cost_eur"] == pytest.approx(expected, abs=1e-5)
    assert view["last"]["model"] == "deepseek/deepseek-v4.1-flash" and view["pause"] is None
    assert [r["task"] for r in project_cloud.runs(runtime, project)] == [
        "design-choice", "research-check"]


def test_revoking_sends_the_rest_of_the_project_back_to_local_by_explicit_decision(
    workshop: tuple[Path, Path, Base],
) -> None:
    runtime, project, base = workshop
    approve(runtime, project)
    assert project_cloud.revoke(runtime, project) is True
    assert project_cloud.revoke(runtime, project) is False
    run(runtime, project, base)
    assert base.routes == ["local", "local"]


# -- visible pause ------------------------------------------------------------------
@pytest.mark.parametrize(
    ("events", "code"),
    [
        ([{"decision": "blocked", "categories": ["token"]}], "privacy_blocked"),
        ([{"decision": "forwarded"}, {"decision": "completed"},
          {"decision": "blocked", "categories": ["secret_assignment"]}], "privacy_blocked"),
        ([{"decision": "budget_refused"}], "budget_refused"),
        ([{"decision": "forwarded"}, {"decision": "upstream_error", "status": 500}],
         "provider_unavailable"),
        ([{"decision": "upstream_unreachable"}], "provider_unavailable"),
        ([{"decision": "forwarded"}, {"decision": "interrupted"}], "provider_unavailable"),
        ([], "gateway_unreachable"),
    ],
)
def test_a_cloud_step_that_cannot_run_pauses_visibly_and_never_falls_back_to_local(
    workshop: tuple[Path, Path, Base], events: list[dict[str, Any]], code: str
) -> None:
    runtime, project, base = workshop
    approve(runtime, project)
    base.cloud_events = events
    base.cloud_error = RuntimeError("openclaw: échec")
    results = run(runtime, project, base)
    assert [(r["task_id"], r["status"], r["code"]) for r in results] == [
        ("design-choice", "PAUSED", code)]
    assert base.routes == ["cloud"]  # no local attempt, no second try
    assert is_paused(runtime, project) and progress(runtime)["phase"] == "paused"
    pause = project_cloud.read_pause(runtime, project)
    assert pause is not None and pause["code"] == code and pause["task"] == "design-choice"
    assert "local" in pause["message"]
    # The task is neither failed nor recorded as done: it is still waiting.
    assert (project / "deliverables/design-choice").exists() is False


def test_the_pause_names_the_category_never_the_secret(
    workshop: tuple[Path, Path, Base],
) -> None:
    runtime, project, base = workshop
    approve(runtime, project)
    base.cloud_events = [{"decision": "blocked", "categories": ["token", "denylist"]}]
    base.cloud_error = RuntimeError("451")
    run(runtime, project, base)
    pause = project_cloud.read_pause(runtime, project)
    assert pause is not None
    assert "jeton d'accès" in pause["message"] and "liste personnelle" in pause["message"]


def test_resuming_after_the_cause_is_fixed_continues_in_the_cloud(
    workshop: tuple[Path, Path, Base],
) -> None:
    runtime, project, base = workshop
    approve(runtime, project)
    base.cloud_events = [{"decision": "upstream_unreachable"}]
    base.cloud_error = RuntimeError("down")
    assert run(runtime, project, base)[0]["status"] == "PAUSED"
    base.cloud_error, base.cloud_events = None, [{"decision": "forwarded"}, {"decision": "completed"}]
    results = run(runtime, project, base, resume=True)
    assert [r["status"] for r in results] == ["PASS", "PASS"]
    assert base.routes == ["cloud", "cloud", "cloud"]
    assert project_cloud.read_pause(runtime, project) is None and not is_paused(runtime, project)


def test_still_broken_after_resume_pauses_again_instead_of_looping(
    workshop: tuple[Path, Path, Base],
) -> None:
    runtime, project, base = workshop
    approve(runtime, project)
    base.cloud_events, base.cloud_error = [], RuntimeError("down")
    run(runtime, project, base)
    assert run(runtime, project, base, resume=True)[0]["status"] == "PAUSED"
    assert base.routes == ["cloud", "cloud"]


def test_a_content_error_from_the_cloud_is_a_normal_failure_not_a_pause(
    workshop: tuple[Path, Path, Base],
) -> None:
    runtime, project, base = workshop
    approve(runtime, project)

    class BadAnswer(Base):
        def __call__(self, role: str, prompt: str, session: str, *, route: str = "local") -> Any:
            super().__call__(role, prompt, session, route=route)
            return {"files": {}, "summary": ""}

    bad = BadAnswer(runtime)
    results = run(runtime, project, bad)  # type: ignore[arg-type]
    assert results[0]["status"] == "FAIL" and project_cloud.read_pause(runtime, project) is None


def test_exhausted_budget_pauses_before_calling_anything(
    workshop: tuple[Path, Path, Base],
) -> None:
    runtime, project, base = workshop
    approve(runtime, project)
    load_ledger(runtime, ROOT).record_invoice(25.0)
    results = run(runtime, project, base)
    assert results[0]["code"] == "budget_refused" and base.routes == []


def test_changed_sources_invalidate_the_approval_until_it_is_renewed(
    workshop: tuple[Path, Path, Base],
) -> None:
    runtime, project, base = workshop
    approve(runtime, project)
    # A source swapped after the approval (the integrity gate of the worker is a second guard).
    source = next((project / "intake").rglob("*.md"))
    source.chmod(0o644)
    source.write_text(source.read_text() + "\nSource ajoutée après l'accord.")
    assert project_cloud.consent_state(ROOT, runtime, project)["state"] == "stale"
    with pytest.raises(CloudPause) as paused:
        project_runner(ROOT, runtime, project, base=base)("expert-recherche", "x\n{}", "s1")
    assert paused.value.code == "consent_stale" and base.routes == []
    assert project_cloud.read_pause(runtime, project)["code"] == "consent_stale"  # type: ignore[index]
    project_cloud.grant(ROOT, runtime, project, acknowledged=True)
    assert project_cloud.consent_state(ROOT, runtime, project)["state"] == "granted"


def test_cloud_switched_off_after_approval_pauses_the_project(
    workshop: tuple[Path, Path, Base],
) -> None:
    runtime, project, base = workshop
    approve(runtime, project)
    from clawfedora.cloud_state import revoke_activation

    revoke_activation(runtime)
    results = run(runtime, project, base)
    assert results[0]["status"] == "PAUSED" and results[0]["code"] == "cloud_inactive"
    assert base.routes == []


def test_the_independent_review_also_goes_through_the_project_route(
    workshop: tuple[Path, Path, Base],
) -> None:
    runtime, project, base = workshop
    approve(runtime, project)
    run(runtime, project, base)
    base.cloud_events, base.cloud_error = [{"decision": "budget_refused"}], RuntimeError("402")
    runner = project_runner(ROOT, runtime, project, base=base)
    with pytest.raises(CloudPause) as paused:
        review_project(ROOT, runtime, project, "validation", runner=runner)
    assert paused.value.code == "budget_refused" and base.routes[-1] == "cloud"


def test_the_local_model_check_is_skipped_for_cloud_projects_only(
    workshop: tuple[Path, Path, Base], monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, project, base = workshop
    from clawfedora import ollama_api, project_worker

    class OllamaDown(Exception):
        pass

    def no_ollama(*_a: Any, **_k: Any) -> Any:
        raise OllamaDown

    monkeypatch.setattr(ollama_api, "request_json", no_ollama)
    monkeypatch.setattr(project_worker, "openclaw_runner", lambda *_a, **_k: base)
    with pytest.raises(OllamaDown):
        run_project_tasks(ROOT, runtime, project)  # local project: the check still applies
    approve(runtime, project)
    results = run_project_tasks(ROOT, runtime, project)
    assert [r["status"] for r in results] == ["PASS", "PASS"] and base.routes == ["cloud", "cloud"]


# -- display and commands ---------------------------------------------------------
def test_the_overview_reports_cloud_state_and_budget(
    workshop: tuple[Path, Path, Base],
) -> None:
    runtime, project, _ = workshop
    assert project_cloud.overview(ROOT, runtime) == {
        "ready": False, "reason": "cloud non activé"}
    activate(runtime)
    load_ledger(runtime, ROOT).record_invoice(21.0)
    overview = project_cloud.overview(ROOT, runtime)
    assert overview["ready"] is True
    assert overview["budget"]["spent_eur"] == 21.0 and overview["budget"]["level"] == "warning"
    assert overview["budget"]["remaining_eur"] == 4.0


def test_the_command_line_shows_requires_acknowledgement_and_revokes(
    workshop: tuple[Path, Path, Base], capsys: pytest.CaptureFixture[str]
) -> None:
    from clawfedora.cli import main

    runtime, project, _ = workshop
    activate(runtime)
    common = ["--root", str(ROOT), "project"]
    ident = ["--runtime-root", str(runtime), "--project-id", "daily-project"]
    assert main([*common, "cloud-approve", *ident]) == 2
    assert "ne repasse jamais en local" in capsys.readouterr().out
    assert main([*common, "cloud-approve", *ident, "--acknowledge"]) == 0
    assert main([*common, "cloud-status", *ident]) == 0
    assert json.loads(capsys.readouterr().out.split("PROJECT_CLOUD_APPROVE=")[1].split("\n", 1)[1])[
        "state"] == "granted"
    assert main([*common, "cloud-revoke", *ident]) == 0
    assert not project_cloud.consent_path(runtime, project).exists()
