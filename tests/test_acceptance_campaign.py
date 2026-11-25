"""The acceptance plan is not a physical certification or an implicit test runner."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from clawfedora import acceptance_campaign as ac
from clawfedora.contracts import ContractReport
from clawfedora.hardware_gate import GateCheck, HardwareGateReport
from clawfedora.lifecycle import HealthCheck, HealthReport

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_HARDWARE = "TEST_ONLY_HARDWARE_DETAIL_9a0e77"
PRIVATE_HEALTH = "TEST_ONLY_HEALTH_STDOUT_2d71e8"
PRIVATE_FAILURE = "TEST_ONLY_HEALTH_FAILURE_731f0c"


def _no_call(*_args: Any, **_kwargs: Any) -> Any:
    pytest.fail("unexpected host inspection")


def test_plan_never_invokes_checks_or_requires_installed_fedora(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    for name in ("validate_repository", "collect_health", "collect_hardware_gate",
                 "require_storage", "fixed_command", "_page", "_ollama_read"):
        monkeypatch.setattr(ac, name, _no_call)
    result = ac.campaign(tmp_path)
    assert result["precheck"] == "NOT_RUN" and result["checks"] == []
    assert result["hardware_certified"] is False
    assert result["verdict"] == "NOT_END_TO_END_QUALIFIED"
    assert len(result["outstanding"]) >= 17
    stages = [row["id"] for row in result["outstanding"]]
    assert stages.index("validator-image") < stages.index("ornith-work-loop")
    assert stages[-1] == "first-infraops-project"
    assert all(row["status"] == "NOT_RUN" for row in result["outstanding"])
    assert all((ROOT / "docs" / row["guide"]).is_file() for row in result["outstanding"])


def test_source_contracts_run_without_host_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("collect_health", "collect_hardware_gate", "require_storage", "fixed_command",
                 "_page", "_ollama_read"):
        monkeypatch.setattr(ac, name, _no_call)
    result = ac.campaign(ROOT, mode="source")
    assert result["precheck"] == "SOURCE_CONTRACTS_PASS"
    assert result["checks"] == [{"id": "source-contracts", "status": "PASS"}]
    assert result["active_tests_executed"] is False
    assert result["remote_integrations_tested"] is False
    assert result["hardware_certified"] is False


def test_missing_source_or_storage_stops_before_runtime_probes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    for name in ("collect_health", "collect_hardware_gate", "fixed_command", "_page"):
        monkeypatch.setattr(ac, name, _no_call)
    monkeypatch.setattr(ac, "validate_repository", lambda _: ContractReport(("bad",), ()))
    monkeypatch.setattr(ac, "require_storage", _no_call)
    assert ac.campaign(ROOT, mode="inspect", runtime=tmp_path)["precheck"] == "BLOCKED"
    monkeypatch.setattr(ac, "validate_repository", lambda _: ContractReport((), ()))

    def missing(*_args: Any) -> None:
        raise ValueError("private path must not leak")

    monkeypatch.setattr(ac, "require_storage", missing)
    report = ac.campaign(ROOT, mode="inspect", runtime=tmp_path)
    assert report["precheck"] == "BLOCKED"
    assert "private path" not in json.dumps(report)
    assert report["checks"][-1] == {"id": "managed-secondary-storage", "status": "FAIL"}


@pytest.mark.parametrize("problem", ["none", "missing", "duplicate", "warning", "page", "service"])
def test_inspect_reports_only_status_and_never_certifies_hardware(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, problem: str,
) -> None:
    (tmp_path / ".openclaw-fedora-runtime").touch()
    monkeypatch.setattr(ac, "validate_repository", lambda _: ContractReport((), ()))
    monkeypatch.setattr(ac, "require_storage", lambda *_args: None)
    monkeypatch.setattr(ac, "collect_hardware_gate", lambda *_args: HardwareGateReport(
        "system", (GateCheck("host", "WARN" if problem == "warning" else "PASS", PRIVATE_HARDWARE),),
        "now",
    ))
    calls: list[list[str]] = []

    def command(args: list[str]) -> bool:
        calls.append(args)
        return problem != "service" or args[-1] != "clawfedora-dashboard.service"

    def health(_repo: Path, runtime: Path, *, probe: bool, ollama_request: Any) -> HealthReport:
        assert runtime == tmp_path and probe is False
        assert ollama_request is ac._ollama_read
        checks = [HealthCheck(name, "PASS", PRIVATE_HEALTH) for name in ac.HEALTH_IDS
                  if problem != "missing" or name != "model-inventory"]
        if problem == "duplicate":
            checks.append(HealthCheck("model-inventory", "FAIL", PRIVATE_FAILURE))
        return HealthReport(tuple(checks))

    monkeypatch.setattr(ac, "fixed_command", command)
    monkeypatch.setattr(ac, "collect_health", health)
    monkeypatch.setattr(ac, "_page", lambda path: problem != "page" or path != "/notion.html")
    report = ac.campaign(ROOT, mode="inspect", runtime=tmp_path)
    assert report["precheck"] == (
        "READY_FOR_MANUAL_TESTS" if problem == "none" else "REVIEW_REQUIRED"
    )
    assert report["hardware_certified"] is False
    assert report["verdict"] == "NOT_END_TO_END_QUALIFIED"
    assert all(row["status"] == "NOT_RUN" for row in report["outstanding"])
    serialized = json.dumps(report)
    for detail in (PRIVATE_HARDWARE, PRIVATE_HEALTH, PRIVATE_FAILURE):
        assert detail not in serialized
    # Status-only structure also rejects arbitrary details even if their text varies.
    assert all(set(row) == {"id", "status"} for row in report["checks"])
    assert report["outstanding"] == ac.campaign(ROOT)["outstanding"]
    assert len(calls) == 6
    assert all(call[-2] == "--quiet" for call in calls)
    assert not any("webui" in " ".join(call) for call in calls)


@pytest.mark.parametrize("status,size", [(200, 10), (302, 10), (200, 1_048_577)])
def test_local_inventory_is_bounded_and_never_follows_redirects(
    monkeypatch: pytest.MonkeyPatch, status: int, size: int,
) -> None:
    calls: list[tuple[str, str]] = []

    class Response:
        def __init__(self) -> None:
            self.status = status

        def read(self, limit: int) -> bytes:
            assert limit == 1_048_577
            return b'{"ok":true}' if size < 100 else b"x" * size

    class Connection:
        def __init__(self, host: str, port: int, timeout: int) -> None:
            assert (host, port, timeout) == ("127.0.0.1", 11434, 5)

        def request(self, method: str, path: str) -> None:
            calls.append((method, path))

        def getresponse(self) -> Response:
            return Response()

        def close(self) -> None:
            pass

    monkeypatch.setattr(ac, "HTTPConnection", Connection)
    for url in ("http://evil.invalid", "http://127.0.0.1:11434/api/generate"):
        with pytest.raises(ValueError, match="non autorisée"):
            ac._ollama_read(url)
    assert calls == []
    if status == 200 and size < 100:
        assert ac._ollama_read("http://127.0.0.1:11434/api/tags") == {"ok": True}
    else:
        with pytest.raises(ValueError):
            ac._ollama_read("http://127.0.0.1:11434/api/tags")
    assert calls == [("GET", "/api/tags")]


def test_cli_modes_and_exit_status(capsys: pytest.CaptureFixture[str]) -> None:
    assert ac.main(["--root", str(ROOT)]) == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "plan"
    assert ac.main(["--root", str(ROOT), "--source"]) == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "source"
    with pytest.raises(SystemExit) as exc:
        ac.main(["--root", str(ROOT), "--inspect"])
    assert exc.value.code == 2
    with pytest.raises(SystemExit) as exc:
        ac.main(["--root", str(ROOT), "--source", "--runtime-root", "/data/IA/Openclaw"])
    assert exc.value.code == 2
