"""Sandbox tests never execute Podman or touch real projects."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from clawfedora import devops_sandbox
from clawfedora.devops_lab import LabRefusal


@pytest.fixture
def sample(tmp_path: Path) -> tuple[Path, Path, str]:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / ".openclaw-fedora-runtime").touch()
    workspace = runtime / "workspaces/ingenieur-devops"
    workspace.mkdir(parents=True)
    scope = "projects/p/t/uuid"
    snapshot = workspace / scope
    snapshot.mkdir(parents=True)
    (snapshot / ".openclaw-fedora-input-guard.json").write_text('{"files":{}}')
    (snapshot / "main.tf").write_text('resource "null_resource" "old" {}')
    return runtime, workspace, scope


def test_approval_requires_managed_runtime_digest_and_explicit_apply(
    sample: tuple[Path, Path, str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, workspace, scope = sample
    digest_image = "registry.example/validator@sha256:" + "a" * 64
    if devops_sandbox.os.geteuid() == 0:
        with pytest.raises(LabRefusal, match="sous root"):
            devops_sandbox.approve_image(runtime, digest_image, apply=False)
        return  # Fedora container runs as root: refuse approval by design.
    assert devops_sandbox.approve_image(runtime, digest_image, apply=False)["status"] == "DRY_RUN"
    assert not (runtime / devops_sandbox.POLICY_PATH).exists()
    with pytest.raises(LabRefusal, match="image validée"):
        devops_sandbox.validate_proposal(
            runtime, workspace, scope, "terraform-fmt", {"main.tf": "terraform {}"}
        )
    with pytest.raises(LabRefusal, match="digest"):
        devops_sandbox.approve_image(runtime, "latest", apply=False)
    monkeypatch.setattr(devops_sandbox.os, "geteuid", lambda: runtime.stat().st_uid)
    monkeypatch.setattr(devops_sandbox.shutil, "which", lambda name: "/usr/bin/podman")
    monkeypatch.setattr(
        devops_sandbox.subprocess,
        "run",
        lambda *args, **kwargs: type("Proc", (), {"returncode": 0})(),
    )
    result = devops_sandbox.approve_image(runtime, digest_image, apply=True)
    assert result["applied"] is True
    assert devops_sandbox._approved_image(runtime) == digest_image


def test_proposed_edits_are_isolated_bounded_and_receipted(
    sample: tuple[Path, Path, str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, workspace, scope = sample
    image = "registry.example/validator@sha256:" + "b" * 64
    target = runtime / devops_sandbox.POLICY_PATH
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"image": image, "approved_by_operator": True}))
    target.chmod(0o600)
    source = workspace / scope / "main.tf"
    original = source.read_text()
    invoked: list[str] = []

    def fake_lab(project: Path, tool: str, approved: str | None, apply: bool) -> int:
        assert approved == image and apply is True and tool == "terraform-fmt"
        assert (project / "main.tf").read_text() == "terraform {}"
        invoked.append(tool)
        return 0

    monkeypatch.setattr(devops_sandbox, "run_lab", fake_lab)
    for expected in (1, 2, 3):
        result = devops_sandbox.validate_proposal(
            runtime, workspace, scope, "terraform-fmt", {"main.tf": "terraform {}"}
        )
        assert result["status"] == "PASS"
        assert result["attempt"] == expected
        assert result["receipt"]
    assert len(invoked) == 3
    assert source.read_text() == original
    with pytest.raises(LabRefusal, match="Trois tentatives"):
        devops_sandbox.validate_proposal(
            runtime, workspace, scope, "terraform-fmt", {"main.tf": "terraform {}"}
        )


def test_refuses_prohibited_source_or_edit(
    sample: tuple[Path, Path, str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, workspace, scope = sample
    image = "registry.example/validator@sha256:" + "c" * 64
    target = runtime / devops_sandbox.POLICY_PATH
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"image": image, "approved_by_operator": True}))
    target.chmod(0o600)
    monkeypatch.setattr(devops_sandbox, "run_lab", lambda *_args, **_kw: 0)
    for bad_scope in ("../../etc", "/tmp", "projects/another"):
        with pytest.raises(LabRefusal):
            devops_sandbox.validate_proposal(
                runtime, workspace, bad_scope, "terraform-fmt", {"main.tf": "ok"}
            )
    for bad in ("../escape.py", ".ssh/key.py", "secrets.tfvars"):
        with pytest.raises(LabRefusal):
            devops_sandbox.validate_proposal(
                runtime, workspace, scope, "terraform-fmt", {bad: "bad"}
            )
    with pytest.raises(LabRefusal):
        devops_sandbox.validate_proposal(
            runtime, workspace, scope, "bash", {"main.tf": "ok"}
        )
