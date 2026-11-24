"""Offline image build contracts; no actual Podman invocation in CI."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from clawfedora import validator_image as build
from clawfedora.devops_lab import LabRefusal, image_is_pinned

ROOT = Path(__file__).resolve().parents[1]
BASE = "registry.example/fedora@sha256:" + "a" * 64
IMAGE = "sha256:" + "b" * 64


@pytest.fixture
def payload(tmp_path: Path) -> Path:
    root = tmp_path / "payload"
    files = {f"bin/{name}": "binary" for name in build.BINARIES}
    files.update({
        "wheels/example.whl": "wheel", "requirements.lock": "locked",
        "terraform-providers/example/provider": "provider",
        "schemas/master-standalone-strict/configmap.json": "{}",
        "sources.md": "operator provenance",
    })
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    (root / "manifest.json").write_text(json.dumps({
        name: hashlib.sha256(text.encode()).hexdigest() for name, text in files.items()
    }))
    return root


def test_plan_checks_all_resources_without_podman(
    payload: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(build.subprocess, "run", lambda *_a, **_kw: pytest.fail("no Podman"))
    result = build.build_image(ROOT, BASE, payload, apply=False)
    assert result["status"] == "PLAN_ONLY" and result["approved"] is False
    assert result["network"] == "none" and "image" not in result
    with pytest.raises(LabRefusal, match="épinglée"):
        build.build_image(ROOT, "fedora:latest", payload, apply=False)


@pytest.mark.parametrize("change", ["tamper", "extra", "link", "missing"])
def test_manifest_refuses_drift(payload: Path, change: str) -> None:
    binary = payload / "bin/terraform"
    if change == "tamper":
        binary.write_text("different")
    elif change == "extra":
        (payload / "extra").write_text("unlisted")
    elif change == "link":
        (payload / "alias").symlink_to(binary)
    else:
        binary.unlink()
    with pytest.raises(LabRefusal):
        build.verify_payload(payload)


def test_build_is_local_bounded_and_never_approves(
    payload: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        if argv[1] == "build":
            assert "--pull=never" in argv and "--network=none" in argv
            assert "--http-proxy=false" in argv
            context = Path(argv[-1])
            assert context != payload and (context / "payload/manifest.json").is_file()
            Path(argv[argv.index("--iidfile") + 1]).write_text(IMAGE)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(build.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(build.shutil, "which", lambda _: "/usr/bin/podman")
    monkeypatch.setattr(build.subprocess, "run", fake_run)
    result = build.build_image(ROOT, BASE, payload, apply=True)
    assert result["status"] == "BUILT_NOT_QUALIFIED"
    assert result["image"] == IMAGE and result["approved"] is False
    assert [command[1] for command in calls] == ["image", "build"]
    assert image_is_pinned(IMAGE)
    assert not image_is_pinned("sha256:short")
