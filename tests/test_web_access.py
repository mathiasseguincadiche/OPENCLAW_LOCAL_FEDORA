"""Private Web access does not silently inherit local-agent search permissions."""

from __future__ import annotations

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
