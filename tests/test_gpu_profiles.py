"""GPU configuration experiments: fail closed and preserve the managed service."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from clawfedora import gpu_profiles

ROOT = Path(__file__).resolve().parents[1]
CONFIG = """[Unit]
ConditionPathIsMountPoint=/data
[Service]
SupplementaryGroups=render video
Environment="OLLAMA_HOST=127.0.0.1:11434"
Environment="OLLAMA_MODELS=/data/IA/Openclaw/models/ollama"
Environment="OLLAMA_VULKAN=1"
Environment="GGML_VK_VISIBLE_DEVICES=0"
Environment="OLLAMA_NUM_PARALLEL=1"
Environment="OLLAMA_MAX_LOADED_MODELS=1"
Environment="OLLAMA_MAX_QUEUE=4"
Environment="OLLAMA_CONTEXT_LENGTH=32768"
Environment="OLLAMA_KEEP_ALIVE=3m"
Environment="OLLAMA_NO_CLOUD=1"
Environment="OLLAMA_KV_CACHE_TYPE=f16"
"""


def _environment(config: str) -> str:
    return " ".join(line.removeprefix("Environment=") for line in config.splitlines()
                    if line.startswith("Environment="))


@pytest.mark.parametrize("name", ["reference", "flash", "q8"])
def test_only_two_gpu_settings_change(name: str) -> None:
    changed = gpu_profiles.patch_config(CONFIG, name)
    assert gpu_profiles.effective_profile(_environment(changed)) == name
    assert changed.startswith(CONFIG.removesuffix('Environment="OLLAMA_KV_CACHE_TYPE=f16"\n'))
    assert gpu_profiles.patch_config(changed, name) == changed
    assert gpu_profiles.patch_config(changed, "reference") == gpu_profiles.patch_config(
        CONFIG, "reference"
    )


@pytest.mark.parametrize("broken", [
    CONFIG.replace("OLLAMA_NO_CLOUD=1", "OLLAMA_NO_CLOUD=0"),
    CONFIG.replace("OLLAMA_CONTEXT_LENGTH=32768", "OLLAMA_CONTEXT_LENGTH=16384"),
    CONFIG.replace("OLLAMA_MAX_LOADED_MODELS=1", "OLLAMA_MAX_LOADED_MODELS=2"),
    CONFIG + 'Environment="OLLAMA_KV_CACHE_TYPE=f16"\n',
    CONFIG + "EnvironmentFile=/tmp/custom\n",
    CONFIG + "UnsetEnvironment=OLLAMA_NO_CLOUD\n",
    CONFIG.replace('Environment="OLLAMA_KV_CACHE_TYPE=f16"', ""),
])
def test_unsafe_or_unknown_drop_in_is_refused(broken: str) -> None:
    with pytest.raises(ValueError):
        gpu_profiles.patch_config(broken, "flash")


def test_missing_flash_flag_is_not_claimed_as_reference() -> None:
    assert gpu_profiles.effective_profile(_environment(CONFIG)) == "unverified"
    with pytest.raises(ValueError):
        gpu_profiles.patch_config(CONFIG, "q4")
    with pytest.raises(ValueError):
        gpu_profiles.effective_profile(_environment(CONFIG.replace("OLLAMA_NO_CLOUD=1",
                                                                    "OLLAMA_NO_CLOUD=0")))


def test_systemd_profile_mismatch_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    env = _environment(gpu_profiles.patch_config(CONFIG, "flash"))
    monkeypatch.setattr(
        gpu_profiles.subprocess, "run",
        lambda *a, **kw: subprocess.CompletedProcess(a, 0, stdout=env, stderr=""),
    )
    gpu_profiles.require_configured("flash")
    with pytest.raises(ValueError, match="différent"):
        gpu_profiles.require_configured("q8")


@pytest.mark.parametrize("name", ["reference", "flash", "q8"])
def test_profile_dry_run_never_restarts_ollama(name: str) -> None:
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/linux/24_gpu_profiles.sh"), name],
        capture_output=True, text=True, check=True,
    )
    assert f"GPU_PROFILE_PLAN={name}" in result.stdout
    assert "DRY_RUN=PASS" in result.stdout
    assert "GPU_PROFILE_RESULT" not in result.stdout
