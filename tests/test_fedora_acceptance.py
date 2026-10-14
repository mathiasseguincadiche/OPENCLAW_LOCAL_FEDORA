from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from clawfedora import fedora_acceptance as accept

ROOT = Path(__file__).resolve().parents[1]


def test_precheck_never_claims_real_hardware_qualification(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / ".openclaw-fedora-runtime").touch()
    commands: list[list[str]] = []
    endpoints: list[str] = []

    def run(args: list[str]) -> bool:
        commands.append(args)
        return True

    def get(url: str) -> bool:
        endpoints.append(url)
        return True

    report = accept.readiness(ROOT, runtime, command=run, health=get)
    assert report["precheck"] == "READY_FOR_MANUAL_TESTS"
    assert report["verdict"] == "NOT_END_TO_END_QUALIFIED"
    assert report["no_sensitive_values_collected"] is True
    assert "SSE_first_chunk_before_end_and_cancel" in report["outstanding_manual_proofs"]
    assert "backup_archive_restore_to_separate_destination" in report[
        "outstanding_manual_proofs"
    ]
    user_commands = commands[:-2]
    assert len(user_commands) == 2 * len(accept.SERVICES)
    assert all(cmd[:2] == ["systemctl", "--user"] for cmd in user_commands)
    assert set(tuple(cmd[2:4]) for cmd in user_commands) == {
        ("is-active", "--quiet"), ("is-enabled", "--quiet")
    }
    assert all(cmd[4].endswith(".service") for cmd in user_commands)
    assert commands[-2] == ["systemctl", "is-active", "--quiet", "ollama.service"]
    assert commands[-1] == ["systemctl", "is-enabled", "--quiet", "ollama.service"]
    assert all(report["checks"]["systemd_user_services_enabled"].values())
    assert set(endpoints) == set(accept.LOOPBACK.values())


def test_precheck_fails_closed_on_stopped_service(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / ".openclaw-fedora-runtime").touch()
    report = accept.readiness(
        ROOT, runtime,
        command=lambda args: args[-1] != "clawfedora-webui.service",
        health=lambda _: True,
    )
    assert report["precheck"] == "INCOMPLETE"
    assert report["verdict"] == "NOT_END_TO_END_QUALIFIED"


def test_precheck_requires_ollama_system_service(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / ".openclaw-fedora-runtime").touch()
    report = accept.readiness(
        ROOT, runtime,
        command=lambda args: args != ["systemctl", "is-active", "--quiet", "ollama.service"],
        health=lambda _: True,
    )
    assert report["precheck"] == "INCOMPLETE"
    assert report["checks"]["ollama_system_service_active"] is False


def test_precheck_never_contacts_external_network(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Destination"):
        accept.loopback_health("https://api.openrouter.ai/v1/models")
    with pytest.raises(ValueError, match="Destination"):
        accept.loopback_health("http://127.0.0.1:18789/v1/chat/completions")
    with pytest.raises(ValueError, match="Destination"):
        accept.loopback_health("http://localhost:3000/health")


def test_unmanaged_runtime_and_symlinks_are_refused(tmp_path: Path) -> None:
    unmanaged = tmp_path / "unmanaged"
    unmanaged.mkdir()
    with pytest.raises(ValueError, match="Runtime"):
        accept.readiness(ROOT, unmanaged, command=lambda _: True, health=lambda _: True)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / ".openclaw-fedora-runtime").touch()
    linked = tmp_path / "linked"
    linked.symlink_to(runtime, target_is_directory=True)
    with pytest.raises(ValueError, match="lien"):
        accept.readiness(ROOT, linked, command=lambda _: True, health=lambda _: True)


def test_cli_failure_outputs_no_secrets(capsys: pytest.CaptureFixture[str]) -> None:
    rc = accept.main([
        "--root", str(ROOT), "--runtime-root", "/invalid/missing-runtime",
    ])
    output = capsys.readouterr().out
    assert rc == 2
    assert "REFUSED" in output
    assert "Bearer" not in output and "token" not in output.lower()


def test_precheck_rejects_disabled_boot_services(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / ".openclaw-fedora-runtime").touch()
    report = accept.readiness(
        ROOT, runtime,
        command=lambda args: not (
            args[-1] == "clawfedora-dashboard.service" and "is-enabled" in args
        ),
        health=lambda _: True,
    )
    assert report["precheck"] == "INCOMPLETE"
    assert report["checks"]["systemd_user_services_enabled"][
        "clawfedora-dashboard.service"
    ] is False
    assert report["verdict"] == "NOT_END_TO_END_QUALIFIED"


def test_health_redirect_never_contacts_untrusted_destination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    arrivals: list[str] = []

    class Receiver(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            arrivals.append(self.path)
            self.send_response(200)
            self.end_headers()

    receiver = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
    threading.Thread(target=receiver.serve_forever, daemon=True).start()

    class Redirect(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            self.send_response(302)
            self.send_header(
                "Location", f"http://127.0.0.1:{receiver.server_port}/stolen"
            )
            self.end_headers()

    redirect = ThreadingHTTPServer(("127.0.0.1", 0), Redirect)
    threading.Thread(target=redirect.serve_forever, daemon=True).start()
    try:
        health_url = f"http://127.0.0.1:{redirect.server_port}/health"
        monkeypatch.setattr(accept, "LOOPBACK", {"test": health_url})
        assert accept.loopback_health(health_url) is False
        assert arrivals == []
    finally:
        redirect.shutdown()
        redirect.server_close()
        receiver.shutdown()
        receiver.server_close()
