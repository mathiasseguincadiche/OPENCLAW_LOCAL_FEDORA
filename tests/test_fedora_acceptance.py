from __future__ import annotations

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
    assert all(command[:4] == ["systemctl", "--user", "is-active", "--quiet"]
               for command in commands[:-1])
    assert all(command[4].endswith(".service") for command in commands[:-1])
    assert commands[-1] == ["systemctl", "is-active", "--quiet", "ollama.service"]
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
