"""Production native SSE opt-in: no privilege escalation from browser to Gateway."""

from __future__ import annotations

import json
import threading
from collections.abc import Generator
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

import pytest

from clawfedora import native_stream
from clawfedora.openclaw_config import build_openclaw_patch
from clawfedora.project_worker import worker_lock
from clawfedora.webui_bridge import MODEL_IDS, make_server

ROOT = Path(__file__).resolve().parents[1]
WEB_TOKEN = "b" * 64
OPERATOR_TOKEN = "operator-only-" + "z" * 48


def _runtime(tmp_path: Path) -> Path:
    runtime = tmp_path / "runtime"
    (runtime / "state/webui").mkdir(parents=True)
    (runtime / "state/openclaw").mkdir(parents=True)
    (runtime / ".openclaw-fedora-runtime").touch()
    marker = runtime / native_stream.MARKER
    marker.write_text(native_stream.APPROVAL + "\n", encoding="utf-8")
    marker.chmod(0o600)
    _config(runtime)
    return runtime


def _config(runtime: Path, **gateway_override: Any) -> Path:
    gateway: dict[str, Any] = {
        "mode": "local",
        "bind": "loopback",
        "port": 18789,
        "auth": {"mode": "token", "token": OPERATOR_TOKEN},
        "http": {"endpoints": {"chatCompletions": {"enabled": True}}},
    }
    gateway.update(gateway_override)
    target = runtime / "state/openclaw/openclaw.json"
    target.write_text(json.dumps({"gateway": gateway}), encoding="utf-8")
    target.chmod(0o600)
    return target


def test_native_sse_default_off_and_canary_patch_reverts(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    assert native_stream.opted_in(runtime) is False
    assert build_openclaw_patch(ROOT, runtime)["gateway"]["http"] == {
        "endpoints": {"chatCompletions": {"enabled": False}}
    }
    enabled = _runtime(tmp_path)
    assert native_stream.opted_in(enabled)
    assert build_openclaw_patch(ROOT, enabled)["gateway"]["http"] == {
        "endpoints": {"chatCompletions": {"enabled": True}}
    }
    (enabled / native_stream.MARKER).unlink()
    assert build_openclaw_patch(ROOT, enabled)["gateway"]["http"] == {
        "endpoints": {"chatCompletions": {"enabled": False}}
    }


def test_native_operator_token_is_read_only_from_private_loopback_config(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    assert native_stream.operator_token(runtime) == OPERATOR_TOKEN
    assert OPERATOR_TOKEN not in json.dumps(build_openclaw_patch(ROOT, runtime))


@pytest.mark.parametrize("mutation", [
    "public-marker", "symlink-marker", "wrong-marker", "public-config",
    "symlink-config", "bind-all", "http-disabled", "password-auth",
    "no-auth-token", "remote-mode", "wrong-port",
])
def test_operator_auth_denies_all_invalid_runtime_states(
    tmp_path: Path, mutation: str,
) -> None:
    runtime = _runtime(tmp_path)
    marker = runtime / native_stream.MARKER
    path = runtime / "state/openclaw/openclaw.json"
    if mutation == "public-marker":
        marker.chmod(0o644)
    elif mutation == "symlink-marker":
        marker.unlink()
        marker.symlink_to(path)
    elif mutation == "wrong-marker":
        marker.write_text("enabled\n")
    elif mutation == "public-config":
        path.chmod(0o644)
    elif mutation == "symlink-config":
        target = runtime / "source.json"
        target.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(target)
    elif mutation == "bind-all":
        _config(runtime, bind="lan")
    elif mutation == "http-disabled":
        _config(runtime, http={"endpoints": {"chatCompletions": {"enabled": False}}})
    elif mutation == "password-auth":
        _config(runtime, auth={"mode": "password", "password": OPERATOR_TOKEN})
    elif mutation == "no-auth-token":
        _config(runtime, auth={"mode": "token"})
    elif mutation == "remote-mode":
        _config(runtime, mode="remote")
    elif mutation == "wrong-port":
        _config(runtime, port=9999)
    with pytest.raises((ValueError, OSError)):
        native_stream.operator_token(runtime)


def test_gateway_env_reference_is_explicit_and_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime(tmp_path)
    token_ref = {"source": "env", "provider": "default", "id": "OPENCLAW_GATEWAY_TOKEN"}
    _config(runtime, auth={"mode": "token", "token": token_ref})
    monkeypatch.delenv("OPENCLAW_GATEWAY_TOKEN", raising=False)
    with pytest.raises(ValueError, match="indisponible"):
        native_stream.operator_token(runtime)
    monkeypatch.setenv("OPENCLAW_GATEWAY_TOKEN", OPERATOR_TOKEN)
    assert native_stream.operator_token(runtime) == OPERATOR_TOKEN


def test_preflight_runs_before_opening_gateway_or_sending_http(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime(tmp_path)
    events: list[str] = []

    def refused(*_args: Any) -> dict[str, Any]:
        events.append("preflight")
        raise ValueError("modèle Qwen incorrect")

    def no_gateway(*_args: Any, **_kwargs: Any) -> Generator[str, None, None]:
        pytest.fail("Gateway must not be contacted after failed preflight")
        yield "never"

    monkeypatch.setattr(native_stream, "gateway_local_deltas", no_gateway)
    source = native_stream.native_source(runtime, ROOT, preflight=refused)
    with pytest.raises(ValueError, match="Qwen"):
        source("chef-operations", "bonjour", "123e4567-e89b-12d3-a456-426614174000")
    assert events == ["preflight"]
    with pytest.raises(ValueError, match="Mentor"):
        source("ingenieur-devops", "bonjour", "123e4567-e89b-12d3-a456-426614174000")
    assert events == ["preflight"]


def test_opted_in_bridge_streams_local_only_under_lock_without_token_leak(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime(tmp_path)
    called: list[str] = []
    released = threading.Event()
    first = threading.Event()

    def checker(role: str, _prompt: str, _session: str) -> dict[str, Any]:
        called.append("preflight:" + role)
        return {"text": "", "route": "local"}

    def preflight_factory(*_args: Any, **kwargs: Any) -> Any:
        assert kwargs["preflight_only"] is True
        return checker

    def remote(
        role: str, _prompt: str, _session: str, *, operator_token: str,
    ) -> Generator[str, None, None]:
        assert role == "chef-operations" and operator_token == OPERATOR_TOKEN
        called.append("gateway")
        try:
            yield "Premier fragment "
            first.set()
            assert released.wait(timeout=5)
            yield "final."
        finally:
            called.append("closed")

    monkeypatch.setattr(native_stream, "openclaw_runner", preflight_factory)
    monkeypatch.setattr(native_stream, "gateway_local_deltas", remote)
    def forbidden_cli(*_args: Any) -> dict[str, Any]:
        pytest.fail("local CLI fallback should not run on opted-in simple chat")
    with make_server(ROOT, runtime, WEB_TOKEN, 0, runner=forbidden_cli) as server:
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        conn = HTTPConnection("127.0.0.1", server.server_port, timeout=8)
        conn.request(
            "POST", "/v1/chat/completions",
            body=json.dumps({
                "model": MODEL_IDS[0], "stream": True,
                "messages": [{"role": "user", "content": "Fedora streaming"}],
            }),
            headers={
                "Authorization": "Bearer " + WEB_TOKEN,
                "Content-Type": "application/json",
            },
        )
        response = conn.getresponse()
        assert response.status == 200
        assert b"chat.completion.chunk" in response.readline()
        assert response.readline() == b"\n"
        assert b"Premier fragment" in response.readline()
        assert first.wait(timeout=2)
        with pytest.raises(ValueError, match="déjà actif"), worker_lock(runtime):
            pass
        released.set()
        content = response.read().decode()
        assert '"finish_reason": "stop"' in content
        assert "data: [DONE]" in content and OPERATOR_TOKEN not in content
        conn.close()
        server.shutdown()
        server_thread.join(timeout=5)
    assert called == ["preflight:chef-operations", "gateway", "closed"]
