"""Private Web access does not silently inherit local-agent search permissions."""

from __future__ import annotations

import json
import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

from clawfedora import ops_cli
from clawfedora.openclaw_config import build_openclaw_patch
from clawfedora.web_access import MARKER, private_mode, set_private_mode

ROOT = Path(__file__).resolve().parents[1]


def managed(tmp_path: Path) -> Path:
    runtime = tmp_path / "runtime"
    (runtime / "state").mkdir(parents=True)
    (runtime / ".openclaw-fedora-runtime").write_text("managed\n", encoding="utf-8")
    return runtime


def test_private_mode_disables_all_agent_web_grants_and_native_tools(tmp_path: Path) -> None:
    runtime = managed(tmp_path)
    assert private_mode(runtime) is False
    assert set_private_mode(runtime, True) is True
    assert private_mode(runtime) is True
    assert (runtime / MARKER).stat().st_mode & 0o777 == 0o600
    patch = build_openclaw_patch(ROOT, runtime)
    global_tools = patch["tools"]
    assert {"web_search", "web_fetch"} <= set(global_tools["deny"])
    assert global_tools["web"]["search"]["enabled"] is False
    assert global_tools["web"]["fetch"]["enabled"] is False
    for agent in patch["agents"]["entries"].values():
        tools = agent["tools"]
        assert not {"web_search", "web_fetch"} & set(tools.get("alsoAllow", []))
        assert {"web_search", "web_fetch"} <= set(tools["deny"])
    assert patch["models"]["providers"].keys() == {"ollama"}
    assert patch["agents"]["defaults"]["maxConcurrent"] == 1


def test_connected_mode_requires_explicit_reversal_and_retains_original_grants(
    tmp_path: Path,
) -> None:
    runtime = managed(tmp_path)
    set_private_mode(runtime, True)
    assert set_private_mode(runtime, True) is False
    assert set_private_mode(runtime, False) is True
    assert private_mode(runtime) is False
    connected = build_openclaw_patch(ROOT, runtime)
    assert connected["tools"]["web"]["search"]["enabled"] is True
    assert connected["tools"]["web"]["fetch"]["enabled"] is True
    assert "web_search" not in connected["tools"]["deny"]
    for agent in connected["agents"]["entries"].values():
        assert {"web_search", "web_fetch"} <= set(agent["tools"]["alsoAllow"])


def test_untrusted_markers_refuse_web_configuration_instead_of_silent_revert(
    tmp_path: Path,
) -> None:
    runtime = managed(tmp_path)
    path = runtime / MARKER
    path.parent.mkdir(parents=True)
    path.write_text("unexpected\n", encoding="utf-8")
    path.chmod(0o600)
    with pytest.raises(ValueError, match="non reconnu"):
        build_openclaw_patch(ROOT, runtime)
    path.write_text("private-web-tools-v1\n", encoding="utf-8")
    path.chmod(0o644)
    with pytest.raises(ValueError, match="non privé"):
        private_mode(runtime)
    path.unlink()
    target = tmp_path / "other"
    target.write_text("private-web-tools-v1\n", encoding="utf-8")
    path.symlink_to(target)
    with pytest.raises(ValueError, match="lié"):
        private_mode(runtime)


def test_web_access_cli_only_stages_and_never_claims_running_gateway(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    runtime = managed(tmp_path)
    args = ["--root", str(ROOT), "--runtime-root", str(runtime), "web-access"]
    assert ops_cli.main([*args, "private"]) == 0
    assert not (runtime / MARKER).exists()
    assert "WEB_ACCESS_PLAN" in capsys.readouterr().out
    assert ops_cli.main([*args, "private", "--apply"]) == 0
    staged = capsys.readouterr().out
    assert "WEB_ACCESS_STAGED=private" in staged
    assert "GATEWAY_APPLIED=NOT_VERIFIED" in staged
    assert "RESTART=REQUIRED" in staged
    assert ops_cli.main([*args, "status"]) == 0
    assert "WEB_ACCESS_DESIRED=private" in capsys.readouterr().out
    assert ops_cli.main([*args, "connected", "--apply"]) == 0
    assert not (runtime / MARKER).exists()


def test_unmanaged_runtime_and_linked_directory_are_refused(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    with pytest.raises(ValueError, match="runtime géré"):
        set_private_mode(runtime, True)
    runtime = managed(tmp_path / "managed")
    (runtime / "state/web-access").symlink_to(tmp_path)
    with pytest.raises(ValueError, match="lié"):
        set_private_mode(runtime, True)

# The native mode switch uses the same verifier against the *saved* OpenClaw
# config, before restarting the Gateway. This test makes no network requests.
web_verify = runpy.run_path(str(ROOT / "scripts/validation/verify_web_config.py"))


@pytest.mark.parametrize("private", [True, False])
def test_saved_native_config_matches_desired_web_policy(
    tmp_path: Path, private: bool,
) -> None:
    runtime = managed(tmp_path)
    if private:
        set_private_mode(runtime, True)
    patch = build_openclaw_patch(ROOT, runtime)
    web_verify["verify_policy"](patch, private=private)
    corrupt = json.loads(json.dumps(patch))
    corrupt["tools"]["web"]["search"]["enabled"] = private
    with pytest.raises(ValueError, match="globale"):
        web_verify["verify_policy"](corrupt, private=private)
    if private:
        corrupt = json.loads(json.dumps(patch))
        first = next(iter(corrupt["agents"]["entries"].values()))
        first["tools"]["alsoAllow"].append("web_fetch")
        with pytest.raises(ValueError, match="rôle"):
            web_verify["verify_policy"](corrupt, private=True)


def test_native_web_verifier_refuses_open_permissions_and_symlinks(tmp_path: Path) -> None:
    runtime = managed(tmp_path)
    set_private_mode(runtime, True)
    patch = build_openclaw_patch(ROOT, runtime)
    config = tmp_path / "openclaw.json"
    config.write_text(json.dumps(patch), encoding="utf-8")
    config.chmod(0o600)
    web_verify["verify_file"](config, private=True)
    command = [sys.executable, str(ROOT / "scripts/validation/verify_web_config.py"),
               "--config", str(config), "--mode", "private"]
    good = subprocess.run(command, capture_output=True, text=True, check=False)
    assert good.returncode == 0
    assert "WEB_CONFIG_RESULT=PASS" in good.stdout
    config.chmod(0o644)
    bad = subprocess.run(command, capture_output=True, text=True, check=False)
    assert bad.returncode == 2
    assert "REFUSED" in bad.stdout
    assert "openclaw.json" not in bad.stdout
    config.chmod(0o600)
    link = tmp_path / "linked.json"
    link.symlink_to(config)
    with pytest.raises(ValueError, match="lié"):
        web_verify["verify_file"](link, private=True)


def test_private_mode_switch_is_dry_run_and_requires_explicit_apply() -> None:
    env = {**os.environ, "OPENCLAW_LOCAL_FEDORA_ROOT": "/unmounted-private-test"}
    for action in ("web-private", "web-connected"):
        result = subprocess.run(
            [str(ROOT / "menu.sh"), "--action", action],
            capture_output=True, text=True, env=env, check=False,
        )
        assert result.returncode == 0, result.stderr
        assert "WEB_ACCESS_DRY_RUN=PASS" in result.stdout
    shell = (ROOT / "scripts/linux/17_web_access.sh").read_text(encoding="utf-8")
    assert shell.index("systemctl --user stop openclaw-gateway.service") < shell.index(
        'ops "$ACTION" --apply'
    ) < shell.index('systemctl --user restart openclaw-gateway.service')
    assert shell.index("verify_web_config.py") < shell.index(
        'systemctl --user restart openclaw-gateway.service'
    )
    assert "WEB_ACCESS_RESULT=PASS" in shell
    assert "claw_lock_worker" in shell
