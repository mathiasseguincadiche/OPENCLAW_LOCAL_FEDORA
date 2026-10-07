from __future__ import annotations

from pathlib import Path

import pytest

from clawfedora import hardware_gate

ROOT = Path(__file__).resolve().parents[1]


def test_system_check_passes_expected_fedora_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        hardware_gate,
        "_os_release",
        lambda: {"ID": "fedora", "VERSION_ID": "44"},
    )
    monkeypatch.setattr(hardware_gate, "_gnome_major", lambda: (50, "GNOME Shell 50.2"))
    monkeypatch.setattr(hardware_gate, "_cpu_model", lambda: "AMD Ryzen 7 7700 8-Core Processor")
    monkeypatch.setattr(hardware_gate, "_mem_total_gib", lambda: 47.0)
    monkeypatch.setattr(
        hardware_gate, "_b580_lspci", lambda: (True, "Intel Arc B580\n Kernel driver in use: xe")
    )
    monkeypatch.setattr(hardware_gate, "_rebar_enabled", lambda: (True, "Resizable BAR enabled"))
    monkeypatch.setattr(hardware_gate.os, "cpu_count", lambda: 16)
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")

    def run(command: list[str], timeout: int = 15) -> tuple[int, str]:
        del timeout
        if command[0] == "getenforce":
            return 0, "Enforcing"
        if command[:3] == ["systemctl", "--user", "is-system-running"]:
            return 0, "running"
        raise AssertionError(command)

    monkeypatch.setattr(hardware_gate, "_run", run)
    original_is_dir = Path.is_dir

    def is_dir(path: Path) -> bool:
        if str(path) == "/sys/firmware/efi":
            return True
        return original_is_dir(path)

    monkeypatch.setattr(Path, "is_dir", is_dir)
    report = hardware_gate.collect_hardware_gate(ROOT, "system")
    assert report.ok is True
    assert report.gate == "system"
    assert {item.id for item in report.checks} >= {
        "fedora-44",
        "gnome-50",
        "wayland",
        "cpu",
        "memory",
        "uefi",
        "resizable-bar",
        "selinux-enforcing",
    }


def test_gpu_check_requires_xe_render_mesa_and_vulkan(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        hardware_gate, "_b580_lspci", lambda: (True, "Intel Arc B580\n Kernel driver in use: xe")
    )

    def run(command: list[str], timeout: int = 15) -> tuple[int, str]:
        del timeout
        if command[0] == "lsmod":
            return 0, "xe 123 0"
        if command[:2] == ["id", "-nG"]:
            return 0, "user wheel render video"
        if command[:2] == ["rpm", "-q"]:
            return 0, "mesa-vulkan-drivers-26.1.8"
        if command[:2] == ["vulkaninfo", "--summary"]:
            return 0, "GPU0 Intel(R) Arc(TM) B580 Graphics"
        raise AssertionError(command)

    monkeypatch.setattr(hardware_gate, "_run", run)
    original_glob = Path.glob

    def glob(path: Path, pattern: str):  # type: ignore[no-untyped-def]
        if str(path) == "/dev/dri" and pattern == "renderD*":
            return iter([Path("/dev/dri/renderD128")])
        return original_glob(path, pattern)

    monkeypatch.setattr(Path, "glob", glob)
    report = hardware_gate.collect_hardware_gate(ROOT, "gpu")
    assert report.ok is True
    assert report.gate == "gpu"
    assert all(item.status == "PASS" for item in report.checks)


def test_hardware_evidence_is_written(tmp_path: Path) -> None:
    report = hardware_gate.HardwareGateReport(
        gate="gpu",
        checks=(hardware_gate.GateCheck("vulkan", "PASS", "ok"),),
        collected_at="2026-09-03T00:00:00+00:00",
    )
    path = hardware_gate.write_hardware_evidence(report, tmp_path)
    assert path.is_file()
    assert '"verdict": "PASS"' in path.read_text(encoding="utf-8")


def test_hardware_snapshot_uses_canonical_directory(tmp_path: Path) -> None:
    report = hardware_gate.HardwareGateReport(
        gate="system",
        checks=(),
        collected_at="2026-09-03T00:00:00+00:00",
    )
    requested = tmp_path / "proofs" / "hardware"
    path = hardware_gate.write_hardware_evidence(report, requested)
    assert path.parent == tmp_path / "proofs" / "hardware"
    assert path.is_file()


def test_unknown_hardware_gate_is_rejected() -> None:
    with pytest.raises(ValueError, match="system ou gpu"):
        hardware_gate.collect_hardware_gate(ROOT, "l9")
