"""Persistent Ornith edit-test loop: controlled behavior, never real Podman."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from clawfedora import devops_iteration
from clawfedora.devops_lab import LabRefusal
from clawfedora.project_common import read_json
from clawfedora.project_worker import _resolve_tool_files


@pytest.fixture
def task_snapshot(tmp_path: Path) -> tuple[Path, Path, str]:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / ".openclaw-fedora-runtime").touch()
    workspace = runtime / "workspaces/ingenieur-devops"
    workspace.mkdir(parents=True)
    scope = "projects/example/task/session"
    source = workspace / scope
    source.mkdir(parents=True)
    initial = 'resource "null_resource" "old" {}\n'
    (source / "main.tf").write_text(initial)
    (source / ".openclaw-fedora-input-guard.json").write_text(json.dumps({
        "files": {"main.tf": hashlib.sha256(initial.encode()).hexdigest()}
    }))
    policy = runtime / "state/lab/validator-image.json"
    policy.parent.mkdir(parents=True)
    policy.write_text(json.dumps({
        "image": "registry.example/validators@sha256:" + "a" * 64,
        "approved_by_operator": True,
    }))
    policy.chmod(0o600)
    return runtime, workspace, scope


def test_ornith_repairs_and_collects_the_exact_tested_code(
    task_snapshot: tuple[Path, Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, workspace, scope = task_snapshot
    calls: list[str] = []

    def fake_validator(project: Path, tool: str, image: str, apply: bool) -> int:
        assert tool == "terraform-fmt" and apply is True
        assert image.endswith("a" * 64)
        content = (project / "main.tf").read_text()
        calls.append(content)
        print("VALIDATION_RESULT=" + ("PASS" if "fixed" in content else "FAIL"))
        return 0 if "fixed" in content else 1

    monkeypatch.setattr(devops_iteration, "run_lab", fake_validator)
    initial = devops_iteration.iterate(runtime, workspace, scope, "inspect", "initial")
    assert initial["status"] == "NOT_STARTED" and initial["attempts"] == 0
    first = devops_iteration.iterate(
        runtime, workspace, scope, "edit_test", "initial", "terraform-fmt",
        {"main.tf": 'resource "null_resource" "broken" {}\n'},
    )
    assert first["status"] == "FAIL" and first["attempt"] == 1
    assert "VALIDATION_RESULT=FAIL" in first["log"]
    assert "references" not in first
    with pytest.raises(LabRefusal, match="périmée"):
        devops_iteration.iterate(runtime, workspace, scope, "edit_test",
                                "initial", "terraform-fmt", {"main.tf": "ignored"})
    good = 'resource "null_resource" "fixed" {}\n'
    second = devops_iteration.iterate(
        runtime, workspace, scope, "edit_test", first["revision"], "terraform-fmt",
        {"main.tf": good},
    )
    assert second["status"] == "PASS" and second["attempt"] == 2
    assert calls == [
        'resource "null_resource" "broken" {}\n',
        good,
    ]
    assert (workspace / scope / "main.tf").read_text() == 'resource "null_resource" "old" {}\n'
    assert devops_iteration.iterate(runtime, workspace, scope, "inspect",
                                   second["revision"])["status"] == "PASS"
    artifact_ref = second["references"]["main.tf"]
    response = {"files": {"work/main.tf": artifact_ref}}
    _resolve_tool_files(workspace, set(), {"role": "ingenieur-devops"}, response, scope=scope)
    with pytest.raises(ValueError, match="preuve sandbox"):
        _resolve_tool_files(
            workspace, set(), {"role": "ingenieur-devops"},
            {"files": {"work/main.tf": artifact_ref}}, scope="projects/other/task/session",
        )
    assert response["files"]["work/main.tf"] == good
    proof = read_json(workspace / second["receipt"])
    assert proof["status"] == "PASS" and proof["role"] == "ingenieur-devops"
    assert proof["files_sha256"]["main.tf"] == hashlib.sha256(good.encode()).hexdigest()


def test_failed_or_forged_references_are_refused(
    task_snapshot: tuple[Path, Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, workspace, scope = task_snapshot
    monkeypatch.setattr(devops_iteration, "run_lab", lambda *_args, **_kw: 1)
    failed = devops_iteration.iterate(
        runtime, workspace, scope, "edit_test", "initial", "terraform-fmt",
        {"main.tf": 'resource "null_resource" "bad" {}\n'},
    )
    proof = read_json(workspace / failed["receipt"])
    digest = proof["files_sha256"]["main.tf"]
    identifier = Path(failed["receipt"]).stem
    forged = f"@tool-sandbox:{identifier}:{digest}"
    for role in ("redacteur-pedagogique", "ingenieur-devops"):
        with pytest.raises(ValueError):
            _resolve_tool_files(workspace, set(), {"role": role},
                                {"files": {"work/main.tf": forged}})
    with pytest.raises(LabRefusal):
        devops_iteration.iterate(
            runtime, workspace, scope, "edit_test", failed["revision"],
            "terraform-fmt", {"../outside.tf": "malicious"},
        )


def test_revisions_are_bounded_and_snapshot_guard_is_rechecked(
    task_snapshot: tuple[Path, Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, workspace, scope = task_snapshot
    monkeypatch.setattr(devops_iteration, "run_lab", lambda *_args, **_kw: 1)
    revision = "initial"
    for attempt in (1, 2, 3):
        result = devops_iteration.iterate(
            runtime, workspace, scope, "edit_test", revision, "terraform-fmt",
            {"main.tf": f"resource \"null_resource\" \"attempt_{attempt}\" {{}}\n"},
        )
        revision = result["revision"]
        assert result["attempt"] == attempt
    with pytest.raises(LabRefusal, match="Trois tentatives"):
        devops_iteration.iterate(
            runtime, workspace, scope, "edit_test", revision, "terraform-fmt",
            {"main.tf": "next"},
        )
    # Even if a model somehow edited the source snapshot, its signed guard refuses it.
    (workspace / scope / "main.tf").write_text("tampered")
    with pytest.raises(LabRefusal, match="intégrité"):
        devops_iteration.iterate(runtime, workspace, scope, "inspect", revision)


def test_only_fixed_validators_are_allowed_and_no_internet_is_used(
    task_snapshot: tuple[Path, Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, workspace, scope = task_snapshot
    monkeypatch.setattr(
        devops_iteration, "run_lab",
        lambda *_args, **_kw: pytest.fail("untrusted command executed"),
    )
    with pytest.raises(LabRefusal, match="Validateur"):
        devops_iteration.iterate(
            runtime, workspace, scope, "edit_test", "initial",
            "bash -c curl", {"main.tf": "foo"},
        )
    with pytest.raises(LabRefusal, match="Opération"):
        devops_iteration.iterate(runtime, workspace, scope, "shell", "initial")


def test_multiple_validators_share_revision_and_fail_closed(
    task_snapshot: tuple[Path, Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, workspace, scope = task_snapshot
    calls: list[tuple[str, str, int]] = []

    def fake_run(project: Path, tool: str, image: str, apply: bool, *, timeout: int) -> int:
        assert apply and image.endswith("a" * 64)
        script = (project / "run.sh").read_text()
        calls.append((tool, script, timeout))
        return int(tool == "shellcheck" and "broken" in script)

    monkeypatch.setattr(devops_iteration, "run_lab", fake_run)
    suite = ["terraform-fmt", "shellcheck"]
    failed = devops_iteration.iterate(
        runtime, workspace, scope, "edit_test", "initial",
        files={"run.sh": "broken"}, validators=suite,
    )
    assert failed["status"] == "FAIL" and "references" not in failed
    assert [result["status"] for result in failed["validation_results"]] == ["PASS", "FAIL"]
    with pytest.raises(LabRefusal, match="Suite de validateurs"):
        devops_iteration.iterate(
            runtime, workspace, scope, "edit_test", failed["revision"],
            "terraform-fmt", {"run.sh": "fixed"},
        )
    fixed = devops_iteration.iterate(
        runtime, workspace, scope, "edit_test", failed["revision"],
        files={"run.sh": "fixed"}, validators=suite,
    )
    assert fixed["status"] == "PASS" and fixed["attempt"] == 2
    assert [result["status"] for result in fixed["validation_results"]] == ["PASS", "PASS"]
    assert calls == [
        ("terraform-fmt", "broken", 40), ("shellcheck", "broken", 40),
        ("terraform-fmt", "fixed", 40), ("shellcheck", "fixed", 40),
    ]
    proof = read_json(workspace / fixed["receipt"])
    assert proof["validators"] == suite and proof["revision"] == fixed["revision"]
    assert proof["validation_results"] == fixed["validation_results"]
    assert "run.sh" in fixed["references"]
    current = devops_iteration.iterate(runtime, workspace, scope, "inspect", fixed["revision"])
    assert current["validation_results"] == fixed["validation_results"]


@pytest.mark.parametrize("suite", [
    [], ["shellcheck"], ["shellcheck", "shellcheck"],
    ["shellcheck", "bash"], ["shellcheck", "terraform-fmt", "pytest", "hadolint"],
])
def test_invalid_validator_suites_refused(
    task_snapshot: tuple[Path, Path, str], suite: list[str]
) -> None:
    runtime, workspace, scope = task_snapshot
    with pytest.raises(LabRefusal, match="Liste de validateurs"):
        devops_iteration.iterate(
            runtime, workspace, scope, "edit_test", "initial",
            files={"run.sh": "echo hi"}, validators=suite,
        )
