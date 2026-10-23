"""Three cloud effort profiles are operator-owned, never agent-controlled."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from clawfedora.cloud_profiles import (
    ProfileRefused,
    chosen_profile,
    profile_path,
    profiles,
    set_profile,
)
from clawfedora.core_config import core_contract
from clawfedora.project_worker import worker_lock

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def policy() -> dict[str, object]:
    return core_contract(ROOT, "cloud_policy.yaml")


def test_default_remains_historic_xhigh_and_32k(
    tmp_path: Path, policy: dict[str, object]
) -> None:
    name, settings = chosen_profile(tmp_path, policy)
    assert name == "approfondi"
    assert settings == {"effort": "xhigh", "max_output_tokens": 32768}
    assert not profile_path(tmp_path).exists()
    assert profiles(policy) == {
        "rapide": {"effort": "low", "max_output_tokens": 4096},
        "equilibre": {"effort": "medium", "max_output_tokens": 8192},
        "approfondi": {"effort": "xhigh", "max_output_tokens": 32768},
    }


def test_operator_can_set_and_replace_private_atomic_profile(
    tmp_path: Path, policy: dict[str, object]
) -> None:
    with worker_lock(tmp_path):
        path = set_profile(tmp_path, policy, "rapide")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert chosen_profile(tmp_path, policy)[0] == "rapide"
    with worker_lock(tmp_path):
        set_profile(tmp_path, policy, "equilibre")
    assert chosen_profile(tmp_path, policy)[1] == {
        "effort": "medium", "max_output_tokens": 8192,
    }
    record = json.loads(path.read_text())
    assert record == {"version": 1, "profile": "equilibre"}


def test_invalid_or_tampered_state_fails_closed(
    tmp_path: Path, policy: dict[str, object]
) -> None:
    target = profile_path(tmp_path)
    target.parent.mkdir(parents=True)
    target.write_text('{"version":1,"profile":"openai"}')
    target.chmod(0o600)
    with pytest.raises(ProfileRefused):
        chosen_profile(tmp_path, policy)
    target.write_text("not json")
    with pytest.raises(ProfileRefused):
        chosen_profile(tmp_path, policy)
    target.write_text('{"version":1,"profile":"rapide","bypass":true}')
    with pytest.raises(ProfileRefused):
        chosen_profile(tmp_path, policy)
    target.chmod(0o644)
    with pytest.raises(ProfileRefused, match="0600"):
        chosen_profile(tmp_path, policy)
    target.unlink()
    target.symlink_to("/etc/passwd")
    with pytest.raises(ProfileRefused):
        chosen_profile(tmp_path, policy)
    with pytest.raises(ProfileRefused):
        set_profile(tmp_path, policy, "rapide")


def test_profile_unknown_or_loosened_policy_is_refused(
    tmp_path: Path, policy: dict[str, object]
) -> None:
    with pytest.raises(ProfileRefused):
        set_profile(tmp_path, policy, "supermax")
    tampered = dict(policy)
    tampered["reasoning_profiles"] = {
        "rapide": {"effort": "none", "max_output_tokens": 99999999},
    }
    with pytest.raises(ProfileRefused):
        chosen_profile(tmp_path, tampered)


def test_cli_dry_run_and_explicit_apply(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    from clawfedora import cloud_cli
    from clawfedora.cloud_cli import main

    # Isolated profile persistence; physical storage refusal has separate tests.
    monkeypatch.setattr(cloud_cli, "require_storage", lambda *_args: None)

    prefix = ["--root", str(ROOT), "--runtime-root", str(tmp_path)]
    assert main([*prefix, "profile"]) == 0
    assert "approfondi" in capsys.readouterr().out
    assert main([*prefix, "set-profile", "--name", "rapide"]) == 0
    assert "DRY_RUN" in capsys.readouterr().out
    assert not profile_path(tmp_path).exists()
    assert main([*prefix, "set-profile", "--name", "rapide", "--apply"]) == 0
    assert chosen_profile(tmp_path, core_contract(ROOT, "cloud_policy.yaml"))[0] == "rapide"


def test_unsafe_state_is_not_overwritten(tmp_path: Path, policy: dict[str, object]) -> None:
    target = profile_path(tmp_path)
    target.parent.mkdir(parents=True)
    target.write_text("secret")
    target.chmod(0o644)
    with pytest.raises(ProfileRefused):
        set_profile(tmp_path, policy, "equilibre")
    assert target.read_text() == "secret"
