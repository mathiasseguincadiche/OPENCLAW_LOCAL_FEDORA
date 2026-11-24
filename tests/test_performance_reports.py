"""The local GPU performance dashboard displays only explicit, private measurements."""
from __future__ import annotations

import json
import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from clawfedora import gpu_acceptance, performance_reports
from clawfedora.project_worker import worker_lock

ROOT = Path(__file__).resolve().parents[1]


def _runtime(tmp_path: Path) -> Path:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "state").mkdir(mode=0o700)
    (runtime / ".openclaw-fedora-runtime").touch()
    return runtime


def _measure(alias: str, *, near_limit: bool = False) -> dict[str, Any]:
    return {
        "model_alias": alias,
        "cloud_used": False,
        "config_modified": False,
        "near_limit_requested": near_limit,
        "results": [{
            "context_tokens": 16384,
            "allocated_context_tokens": 16384,
            "prompt_tokens": 14500 if near_limit else 9800,
            "prompt_fill_pct": 88.5 if near_limit else 59.8,
            "gpu_share_pct": 100.0,
            "resident_gib": 8.7,
            "resident_vram_gib": 8.7,
            "load_seconds": 1.4,
            "prompt_tokens_per_second": 128.3,
            "output_tokens_per_second": 23.6,
            "verdict": "FULL_GPU",
            "near_limit_qualified": near_limit,
        }],
    }


def test_dashboard_empty_does_not_create_files_or_run_any_model(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    result = performance_reports.view(runtime)
    assert result["status"] == "NOT_MEASURED"
    assert [m["status"] for m in result["models"]] == ["NOT_MEASURED"] * 2
    assert result["hardware_certified"] is False
    assert not (runtime / performance_reports.RELATIVE).exists()
    assert not (runtime / "state/performance").exists()


def test_operator_record_preserves_both_models_and_private_permissions(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    performance_reports.save(runtime, {
        "qwen-max": _measure("qwen-max", near_limit=True),
        "ornith-code": _measure("ornith-code"),
    })
    path = runtime / performance_reports.RELATIVE
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert path.stat().st_size <= performance_reports.MAX_REPORT_BYTES
    saved = path.read_text(encoding="utf-8")
    assert "model-runs" not in saved and "prompt_text" not in saved
    report = performance_reports.view(runtime)
    assert report["status"] == "MEASURED"
    assert report["source"] == "clawfedora-gpu-benchmark"
    assert report["hardware_certified"] is False
    qwen, ornith = report["models"]
    assert (qwen["status"], ornith["status"]) == ("MEASURED", "MEASURED")
    assert qwen["qualified_near_limit_context"] == 16384
    assert ornith["qualified_near_limit_context"] is None
    assert ornith["largest_full_gpu_context"] == 16384
    assert qwen["results"][0]["output_tokens_per_second"] == 23.6


def test_second_operator_run_replaces_not_mixes_old_model_measurements(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    performance_reports.save(runtime, {
        "qwen-max": _measure("qwen-max"),
        "ornith-code": _measure("ornith-code"),
    })
    performance_reports.save(runtime, {"ornith-code": _measure("ornith-code")})
    qwen, ornith = performance_reports.view(runtime)["models"]
    assert qwen["status"] == "NOT_MEASURED" and qwen["results"] == []
    assert ornith["status"] == "MEASURED"


@pytest.mark.parametrize("invalid", [
    {"mystery-model": _measure("qwen-max")},
    {"qwen-max": {**_measure("qwen-max"), "cloud_used": True}},
    {"qwen-max": {**_measure("qwen-max"), "config_modified": True}},
    {"qwen-max": {**_measure("ornith-code")}},
    {"qwen-max": {**_measure("qwen-max"), "results": []}},
    {"qwen-max": {**_measure("qwen-max"), "results": [
        {**_measure("qwen-max")["results"][0], "context_tokens": 100000}
    ]}},
    {"qwen-max": {**_measure("qwen-max"), "results": [
        {**_measure("qwen-max")["results"][0], "output_tokens_per_second": float("nan")}
    ]}},
    {"qwen-max": {**_measure("qwen-max"), "results": [
        {**_measure("qwen-max")["results"][0], "near_limit_qualified": True}
    ]}},
])
def test_untrusted_results_are_never_saved(tmp_path: Path, invalid: Any) -> None:
    runtime = _runtime(tmp_path)
    with pytest.raises(ValueError):
        performance_reports.save(runtime, invalid)
    assert not (runtime / performance_reports.RELATIVE).exists()


def test_corrupt_stale_future_and_unprivate_reports_are_rejected_or_flagged(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    performance_reports.save(runtime, {"qwen-max": _measure("qwen-max")})
    path = runtime / performance_reports.RELATIVE
    doc = json.loads(path.read_text())
    doc["recorded_at"] = (datetime.now(UTC) - timedelta(days=35)).isoformat()
    path.write_text(json.dumps(doc))
    assert performance_reports.view(runtime)["status"] == "STALE"
    doc["recorded_at"] = (datetime.now(UTC) + timedelta(days=3)).isoformat()
    path.write_text(json.dumps(doc))
    assert performance_reports.view(runtime)["status"] == "UNVERIFIED"
    doc["recorded_at"] = datetime.now(UTC).isoformat()
    doc["models"]["qwen-max"]["results"][0]["verdict"] = "SUPER_GPU"
    path.write_text(json.dumps(doc))
    assert performance_reports.view(runtime)["status"] == "UNVERIFIED"
    path.write_text("not json")
    assert performance_reports.view(runtime)["status"] == "UNVERIFIED"
    performance_reports.save(runtime, {"qwen-max": _measure("qwen-max")})
    path.chmod(0o644)
    assert performance_reports.view(runtime)["status"] == "UNVERIFIED"
    with pytest.raises(ValueError, match="0600"):
        performance_reports.save(runtime, {"qwen-max": _measure("qwen-max")})


def test_linked_report_and_linked_folder_are_rejected(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    performance_reports.save(runtime, {"qwen-max": _measure("qwen-max")})
    path = runtime / performance_reports.RELATIVE
    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    path.unlink()
    path.symlink_to(outside)
    assert performance_reports.view(runtime)["status"] == "UNVERIFIED"
    with pytest.raises(ValueError, match="lié"):
        performance_reports.save(runtime, {"qwen-max": _measure("qwen-max")})
    path.unlink()
    path.parent.rmdir()
    path.parent.symlink_to(tmp_path)
    assert performance_reports.view(runtime)["status"] == "UNVERIFIED"
    with pytest.raises(ValueError, match="lié"):
        performance_reports.save(runtime, {"qwen-max": _measure("qwen-max")})


def test_record_cli_requires_explicit_apply_and_runtime(
    tmp_path: Path, capsys: Any,
) -> None:
    runtime = _runtime(tmp_path)
    assert gpu_acceptance.main([
        "--root", str(ROOT), "--record", "--runtime-root", str(runtime),
    ]) == 2
    assert "REFUSED" in capsys.readouterr().out
    assert gpu_acceptance.main([
        "--root", str(ROOT), "--record", "--apply",
    ]) == 2
    assert "REFUSED" in capsys.readouterr().out
    assert not (runtime / performance_reports.RELATIVE).exists()


def test_explicit_locked_cli_record_is_refused_while_worker_is_busy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any,
) -> None:
    runtime = _runtime(tmp_path)
    monkeypatch.setattr(gpu_acceptance, "require_storage", lambda *_args: None)
    calls: list[str] = []

    def fake(_repo: Path, *, context_sizes: tuple[int, ...],
             near_limit: bool, model_alias: str) -> dict[str, Any]:
        calls.append(model_alias)
        return _measure(model_alias)

    monkeypatch.setattr(gpu_acceptance, "benchmark", fake)
    args = ["--root", str(ROOT), "--models", "all", "--contexts", "16384",
            "--apply", "--record", "--runtime-root", str(runtime)]
    with worker_lock(runtime):
        assert gpu_acceptance.main(args) == 2
    assert "REFUSED" in capsys.readouterr().out
    assert calls == []
    assert gpu_acceptance.main(args) == 0
    measured = json.loads(capsys.readouterr().out)
    assert set(measured["benchmarks"]) == {"qwen-max", "ornith-code"}
    assert calls == ["qwen-max", "ornith-code"]
    assert [m["status"] for m in performance_reports.view(runtime)["models"]] == [
        "MEASURED", "MEASURED",
    ]


def test_recorded_benchmark_checks_profile_before_and_after_measurement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any,
) -> None:
    runtime = _runtime(tmp_path)
    monkeypatch.setattr(gpu_acceptance, "require_storage", lambda *_args: None)
    events: list[str] = []

    def check(name: str) -> None:
        events.append("check:" + name)

    def fake(_repo: Path, *, context_sizes: tuple[int, ...],
             near_limit: bool, model_alias: str) -> dict[str, Any]:
        events.append("measure:" + model_alias)
        return _measure(model_alias)

    monkeypatch.setattr(gpu_acceptance, "require_configured", check)
    monkeypatch.setattr(gpu_acceptance, "benchmark", fake)
    args = ["--root", str(ROOT), "--models", "all", "--contexts", "16384",
            "--apply", "--record", "--runtime-root", str(runtime),
            "--expected-profile", "q8"]
    assert gpu_acceptance.main(args) == 0
    assert events == ["check:q8", "measure:qwen-max", "measure:ornith-code", "check:q8"]
    out = json.loads(capsys.readouterr().out)
    assert out["configured_profile"] == "q8"
    assert out["backend_profile_verified"] is False
    assert performance_reports.view(runtime)["configured_profile"] == "q8"

    def mismatch(_name: str) -> None:
        raise ValueError("profil différent")

    before = (runtime / performance_reports.RELATIVE).read_bytes()
    monkeypatch.setattr(gpu_acceptance, "require_configured", mismatch)
    events.clear()
    assert gpu_acceptance.main(args) == 2
    assert events == []
    assert (runtime / performance_reports.RELATIVE).read_bytes() == before


def test_non_recording_benchmark_also_refuses_busy_worker_and_gaming(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any,
) -> None:
    runtime = _runtime(tmp_path)
    monkeypatch.setattr(gpu_acceptance, "require_storage", lambda *_args: None)

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("inference attempted while GPU reserved")

    monkeypatch.setattr(gpu_acceptance, "benchmark", forbidden)
    args = ["--root", str(ROOT), "--apply", "--runtime-root", str(runtime)]
    with worker_lock(runtime):
        assert gpu_acceptance.main(args) == 2
    assert "déjà actif" in capsys.readouterr().out
    (runtime / "state/gaming-mode").touch()
    assert gpu_acceptance.main(args) == 2
    assert "mode jeux actif" in capsys.readouterr().out


def test_special_gpu_report_is_rejected_without_blocking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime(tmp_path)
    path = performance_reports.prepare_record(runtime)
    os.mkfifo(path, 0o600)
    real_open = os.open

    def checked_open(target: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        if target == path:
            assert flags & os.O_NONBLOCK
        return real_open(target, flags, *args, **kwargs)

    monkeypatch.setattr(performance_reports.os, "open", checked_open)
    result = performance_reports.view(runtime)
    assert result["status"] == "UNVERIFIED"
    assert all(row["results"] == [] for row in result["models"])
