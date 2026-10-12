"""No real Podman in unit tests: prove command isolation and refusals."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from clawfedora import devops_lab as lab


def test_dry_run_never_uses_podman(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "main.tf").write_text('terraform { required_version = ">= 1.8.0" }')
    monkeypatch.setattr(lab.subprocess, "run", lambda *args, **kwargs: pytest.fail("no subprocess"))
    assert lab.run_lab(tmp_path, "terraform-fmt", None, False) == 0


@pytest.mark.parametrize("name", [
    ".env", "my.tfvars", "terraform.tfstate", "secret.pem", "id_ed25519",
])
def test_sensitive_files_refuse_snapshot(tmp_path: Path, name: str) -> None:
    (tmp_path / "main.tf").write_text("resource {}")
    (tmp_path / name).write_text("top secret")
    with pytest.raises(lab.LabRefusal, match="sensible"):
        lab.snapshot_manifest(tmp_path)


def test_symlink_file_and_directory_are_refused(tmp_path: Path) -> None:
    (tmp_path / "main.tf").write_text("test")
    (tmp_path / "alias.yaml").symlink_to(tmp_path / "main.tf")
    with pytest.raises(lab.LabRefusal, match="lié"):
        lab.snapshot_manifest(tmp_path)
    (tmp_path / "alias.yaml").unlink()
    (tmp_path / "linked-dir").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(lab.LabRefusal, match="lié"):
        lab.snapshot_manifest(tmp_path)


def test_hidden_git_history_and_binary_are_not_copied(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("token")
    (tmp_path / "program.bin").write_bytes(b"bad")
    (tmp_path / "main.tf").write_text("safe")
    assert lab.snapshot_manifest(tmp_path) == (Path("main.tf"),)


def test_snapshot_byte_limit(tmp_path: Path) -> None:
    (tmp_path / "main.tf").write_bytes(b"x" * (lab.MAX_BYTES + 1))
    with pytest.raises(lab.LabRefusal, match="volumineux"):
        lab.snapshot_manifest(tmp_path)


@pytest.mark.parametrize("image", [
    "rockylinux:9",
    "rockylinux:latest",
    "localhost/test@sha256:nope",
    "../test@sha256:" + "a" * 64,
])
def test_reject_unpinned_or_suspicious_image(image: str) -> None:
    assert not lab.image_is_pinned(image)


def test_validation_commands_are_fixed(tmp_path: Path) -> None:
    manifest = (Path("main.tf"), Path(".github/workflows/ci.yml"), Path("run.sh"))
    assert lab.command_for("terraform-fmt", tmp_path, manifest) == [
        "terraform", "-chdir=/workspace", "fmt", "-check", "-recursive", "-no-color"
    ]
    assert lab.command_for("terraform-validate", tmp_path, manifest)[0] == "terraform"
    assert lab.command_for("ansible-lint", tmp_path, manifest)[1] == "--offline"
    assert lab.command_for("actionlint", tmp_path, manifest) == ["actionlint", "-no-color"]
    assert lab.command_for("shellcheck", tmp_path, manifest) == [
        "shellcheck", "--", "/workspace/run.sh"
    ]
    with pytest.raises(lab.LabRefusal):
        lab.command_for("tool;rm", tmp_path, manifest)
    with pytest.raises(lab.LabRefusal):
        lab.command_for("hadolint", tmp_path, manifest)


def test_apply_uses_only_snapshot_and_offline_container(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "hello.sh").write_text("#!/bin/sh\necho hello\n")
    original = tmp_path / "hello.sh"
    image = "registry.example.net/rocky-validators@sha256:" + "a" * 64
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        if len(argv) >= 2 and argv[1] == "run":
            assert "--network=none" in argv
            assert "--read-only" in argv
            assert "--pull=never" in argv
            assert "--cap-drop=ALL" in argv
            assert "--userns=keep-id" in argv
            volume = argv[argv.index("--volume") + 1]
            assert volume.endswith(":/workspace:ro,Z")
            staged = Path(volume.split(":/workspace:", 1)[0])
            assert staged != tmp_path
            assert (staged / "hello.sh").read_bytes() == original.read_bytes()
            assert tmp_path.as_posix() not in " ".join(argv)
            assert argv[-3:] == ["shellcheck", "--", "/workspace/hello.sh"]
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(lab.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(lab.shutil, "which", lambda _: "/usr/bin/podman")
    monkeypatch.setattr(lab.subprocess, "run", fake_run)
    assert lab.run_lab(tmp_path, "shellcheck", image, True) == 0
    assert [call[1] for call in calls] == ["image", "run", "rm"]


def test_apply_requires_user_and_immutable_image(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "main.tf").write_text("test")
    monkeypatch.setattr(lab.os, "geteuid", lambda: 1000)
    with pytest.raises(lab.LabRefusal, match="épinglée"):
        lab.run_lab(tmp_path, "terraform-fmt", "rocky:latest", True)
    monkeypatch.setattr(lab.os, "geteuid", lambda: 0)
    with pytest.raises(lab.LabRefusal, match="root"):
        lab.run_lab(tmp_path, "terraform-fmt", None, True)


def test_missing_image_refuses_without_pulling(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "main.tf").write_text("test")
    image = "registry.example.net/rocky-validators@sha256:" + "b" * 64
    monkeypatch.setattr(lab.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(lab.shutil, "which", lambda _: "/usr/bin/podman")
    monkeypatch.setattr(
        lab.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1),
    )
    with pytest.raises(lab.LabRefusal, match="aucun téléchargement"):
        lab.run_lab(tmp_path, "terraform-fmt", image, True)
