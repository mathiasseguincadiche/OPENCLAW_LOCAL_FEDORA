"""Minimal installed-Fedora acceptance: one short inference, UI checks, no cloud."""
from __future__ import annotations

import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
smoke = SimpleNamespace(**runpy.run_path(str(ROOT / "scripts/validation/quick_smoke.py")))


def test_only_exact_loopback_probes_allowed() -> None:
    with pytest.raises(ValueError, match="externe"):
        smoke.local_ok("https://example.com/health")
    assert all(url.startswith("http://127.0.0.1:") for url in smoke.ENDPOINTS.values())
    assert smoke.ENDPOINTS["Projects"].endswith("/api/status")


def test_unmounted_secondary_storage_fails_before_ai_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Path, "is_mount", lambda _path: False)
    with pytest.raises(ValueError, match="secondaire"):
        smoke.report(ROOT, Path("/data/IA/Openclaw"))


def test_complete_local_software_readiness_keeps_cloud_unverified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from clawfedora.lifecycle import HealthCheck, HealthReport

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / ".openclaw-fedora-runtime").touch()
    (runtime / "projects").mkdir()
    monkeypatch.setitem(smoke.report.__globals__, "require_storage", lambda *_args: None)
    monkeypatch.setitem(
        smoke.report.__globals__, "collect_health",
        lambda _repo, _runtime, *, probe: HealthReport((
            HealthCheck("model-gpu-probe", "PASS", "quick"),
        )),
    )
    monkeypatch.setitem(smoke.report.__globals__, "local_ok", lambda _url: True)
    value = smoke.report(ROOT, runtime)
    assert value["verdict"] == "READY_FOR_FIRST_PROJECT"
    assert value["remote_cloud_tested"] is False
    assert value["long_gpu_stress_tested"] is False
    assert value["real_world_agent_quality_tested"] is False


def test_failing_local_probes_never_give_ready_label(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from clawfedora.lifecycle import HealthCheck, HealthReport

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / ".openclaw-fedora-runtime").touch()
    (runtime / "projects").mkdir()
    monkeypatch.setitem(smoke.report.__globals__, "require_storage", lambda *_args: None)
    monkeypatch.setitem(
        smoke.report.__globals__, "collect_health",
        lambda _repo, _runtime, *, probe: HealthReport((
            HealthCheck("model-gpu-probe", "FAIL", "no Vulkan"),
        )),
    )
    monkeypatch.setitem(smoke.report.__globals__, "local_ok", lambda _url: True)
    assert smoke.report(ROOT, runtime)["verdict"] == "REVIEW_REQUIRED"
