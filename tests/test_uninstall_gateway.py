"""A02: uninstall stops the *managed* Gateway and proves it before removing anything.

Every scenario runs the real ``claw_uninstall_gateway`` from scripts/linux/lib/runtime.sh
with a temporary HOME and stub ``systemctl``/``openclaw`` commands: nothing on the host is
stopped, installed or removed.
"""

from __future__ import annotations

import os
import socket
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SH = ROOT / "scripts/linux/lib/runtime.sh"

SYSTEMCTL = """#!/usr/bin/env bash
echo "systemctl $*" >> "$FAKE_LOG"
case "$2" in
  cat) [[ "${FAKE_UNIT:-0}" == 1 ]] ;;
  stop) exit "${FAKE_STOP_RC:-0}" ;;
  is-active) [[ "${FAKE_ACTIVE:-0}" == 1 ]] ;;
  *) exit 0 ;;
esac
"""
OPENCLAW = """#!/usr/bin/env bash
echo "openclaw $*|${OPENCLAW_STATE_DIR:-}|${OPENCLAW_CONFIG_PATH:-unset}" >> "$FAKE_LOG"
case "$2" in
  stop) exit "${FAKE_CLI_STOP_RC:-0}" ;;
  uninstall) exit "${FAKE_CLI_UNINSTALL_RC:-0}" ;;
esac
"""


def _executable(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(0o755)


@contextmanager
def _port(listening: bool) -> Iterator[int]:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = int(sock.getsockname()[1])
        if listening:
            sock.listen(4)
            yield port
            return
    yield port  # closed: nothing listens there any more


@pytest.fixture
def host(tmp_path: Path) -> dict[str, Path]:
    home = tmp_path / "home"
    stubs = tmp_path / "stubs"
    _executable(stubs / "systemctl", SYSTEMCTL)
    return {"home": home, "stubs": stubs, "log": tmp_path / "calls.log",
            "state": tmp_path / "data/IA/Openclaw/state/openclaw"}


def _run(host: dict[str, Path], port: int, *, cli: bool = True,
         **fake: str) -> subprocess.CompletedProcess[str]:
    if cli:
        _executable(host["home"] / ".openclaw/bin/openclaw", OPENCLAW)
    host["log"].touch()
    env = {
        # A fresh terminal: ~/.openclaw/bin is NOT on the PATH.
        "PATH": f"{host['stubs']}:/usr/bin:/bin",
        "HOME": str(host["home"]),
        "FAKE_LOG": str(host["log"]),
        # Another OpenClaw instance (default state) that must not be targeted.
        "OPENCLAW_STATE_DIR": str(host["home"] / ".openclaw"),
        "OPENCLAW_CONFIG_PATH": str(host["home"] / "elsewhere.json"),
        "CLAW_GATEWAY_STOP_WAIT": "1",
        **fake,
    }
    script = 'source "$1"; claw_uninstall_gateway "$2" "$3"'
    return subprocess.run(
        ["bash", "-c", script, "bash", str(RUNTIME_SH), str(host["state"]), str(port)],
        capture_output=True, text=True, env=env, timeout=30, check=False,
    )


def _calls(host: dict[str, Path]) -> list[str]:
    return host["log"].read_text().splitlines()


def test_fresh_terminal_targets_the_managed_cli_and_state(host: dict[str, Path]) -> None:
    drop_in = host["home"] / ".config/systemd/user/openclaw-gateway.service.d/openclaw-daily.conf"
    drop_in.parent.mkdir(parents=True)
    drop_in.write_text("[Service]\n")
    with _port(listening=False) as port:
        result = _run(host, port, FAKE_UNIT="1")
    assert result.returncode == 0, result.stderr
    calls = _calls(host)
    managed = f"|{host['state']}|unset"
    stop = calls.index("openclaw gateway stop" + managed)
    systemd_stop = calls.index("systemctl --user stop openclaw-gateway.service")
    uninstall = calls.index("openclaw gateway uninstall" + managed)
    assert stop < systemd_stop < uninstall
    assert not any(str(host["home"] / ".openclaw") + "|" in call for call in calls)
    assert not drop_in.exists()
    assert "GATEWAY_STOP=CONFIRMED" in result.stdout
    assert "GATEWAY_UNINSTALL=PASS" in result.stdout


@pytest.mark.parametrize(
    ("fake", "reason"),
    [({"FAKE_ACTIVE": "1"}, "encore actif"), ({"FAKE_STOP_RC": "1"}, "refusé par systemd")],
)
def test_unconfirmed_stop_removes_nothing(
    host: dict[str, Path], fake: dict[str, str], reason: str
) -> None:
    with _port(listening=False) as port:
        result = _run(host, port, FAKE_UNIT="1", **fake)
    assert result.returncode == 2
    assert reason in result.stderr
    assert not any("gateway uninstall" in call for call in _calls(host))


def test_port_still_answering_blocks_the_uninstall(host: dict[str, Path]) -> None:
    with _port(listening=True) as port:
        result = _run(host, port, FAKE_UNIT="1")
    assert result.returncode == 2
    assert f"port {port} répond encore" in result.stderr
    assert not any("gateway uninstall" in call for call in _calls(host))


def test_cli_stop_error_is_tolerated_only_when_the_stop_is_verified(
    host: dict[str, Path],
) -> None:
    with _port(listening=False) as port:
        result = _run(host, port, FAKE_UNIT="1", FAKE_CLI_STOP_RC="1")
    assert result.returncode == 0, result.stderr
    assert "arrêt est vérifié" in result.stderr


def test_failed_definition_removal_is_reported(host: dict[str, Path]) -> None:
    with _port(listening=False) as port:
        result = _run(host, port, FAKE_UNIT="1", FAKE_CLI_UNINSTALL_RC="1")
    assert result.returncode == 2
    assert "données intactes" in result.stderr


def test_without_cli_the_unit_is_still_stopped_and_disabled(host: dict[str, Path]) -> None:
    with _port(listening=False) as port:
        result = _run(host, port, cli=False, FAKE_UNIT="1")
    assert result.returncode == 0, result.stderr
    calls = _calls(host)
    assert "systemctl --user stop openclaw-gateway.service" in calls
    assert "systemctl --user disable openclaw-gateway.service" in calls
    assert "définition conservée" in result.stderr


def test_nothing_installed_is_a_clean_no_op(host: dict[str, Path]) -> None:
    with _port(listening=False) as port:
        result = _run(host, port, cli=False)
    assert result.returncode == 0, result.stderr
    assert "GATEWAY_STOP=ABSENT" in result.stdout
    assert not any(call.startswith("openclaw") for call in _calls(host))


def test_unknown_listener_without_any_managed_gateway_is_refused(host: dict[str, Path]) -> None:
    with _port(listening=True) as port:
        result = _run(host, port, cli=False)
    assert result.returncode == 2


def test_uninstall_script_proves_the_stop_before_the_first_deletion() -> None:
    text = (ROOT / "scripts/linux/10_uninstall.sh").read_text(encoding="utf-8")
    assert "gateway stop || true" not in text
    assert "gateway uninstall || true" not in text
    assert "command -v openclaw" not in text
    lock = text.index("claw_lock_worker\n")
    stop = text.index('claw_uninstall_gateway "$(claw_openclaw_state)"')
    first_removal = text.index("rm -f")
    cleanup = text.index("cleanup --apply")
    assert lock < stop < first_removal < cleanup
    assert os.access(ROOT / "scripts/linux/10_uninstall.sh", os.X_OK)
