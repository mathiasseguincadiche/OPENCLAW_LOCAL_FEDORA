from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/linux/14_webui_canary.sh"


def test_canary_browser_flag_dry_run_never_starts_container(tmp_path: Path) -> None:
    runtime = tmp_path / "nonexistent"
    result = subprocess.run(
        ["bash", str(SCRIPT), "--browser", "--with-db-copy"],
        env={**os.environ, "OPENCLAW_LOCAL_FEDORA_ROOT": str(runtime)},
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0
    assert "DRY_RUN=PASS" in result.stdout
    assert "browser=1" in result.stdout
    assert not runtime.exists()


@pytest.mark.skipif(os.geteuid() == 0, reason="real installer refuses root")
def test_browser_canary_refuses_noninteractive_unsafe_apply(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    result = subprocess.run(
        ["bash", str(SCRIPT), "--apply", "--browser", "--with-db-copy"],
        env={**os.environ, "OPENCLAW_LOCAL_FEDORA_ROOT": str(runtime)},
        capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL,
    )
    assert result.returncode == 2
    assert "terminal interactif" in result.stderr
    assert not runtime.exists()


def test_browser_network_is_unique_private_and_never_in_production() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    assert 'NET="clawfedora-webui-test-net-$$"' in script
    assert 'NET="clawfedora-webui-test-net-$"' not in script
    assert 'podman network create --internal "$NET"' in script
    assert '--publish 127.0.0.1:3001:8080' in script
    assert 'podman network rm "$NET"' in script
    assert 'ENABLE_OLLAMA_API=false' in script and 'ENABLE_OPENAI_API=false' in script
    # The real Podman/migrated SQLite/browser functionality is only qualified on Fedora.


def test_canary_uses_same_exact_stable_webui_release_as_first_install() -> None:
    from clawfedora.core_config import root_contract

    policy = root_contract(ROOT, "webui_policy.yaml")
    source = SCRIPT.read_text(encoding="utf-8")
    assert policy["release"] == "v0.12.1"
    assert policy["image"] == "ghcr.io/open-webui/open-webui:v0.12.1-slim"
    assert 'IMAGE="ghcr.io/open-webui/open-webui:v0.12.1-slim"' in source
    installer = (ROOT / "scripts/linux/13_openwebui.sh").read_text(encoding="utf-8")
    assert 'podman pull "$IMAGE"' in installer
    assert 'IMAGE_DIGEST="$(podman image inspect "$IMAGE"' in installer
    assert '--image-digest "$IMAGE_DIGEST"' in installer
    assert 'podman run --rm' in source
