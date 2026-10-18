"""Live USB preflight must fail closed, avoid disks and never certify deployment."""

from __future__ import annotations

import runpy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
check = SimpleNamespace(
    **runpy.run_path(str(ROOT / "scripts/validation/live_usb_preflight.py"))
)


def _evidence() -> dict[str, Any]:
    return {
        "release": {
            "ID": "fedora",
            "VERSION_ID": "45",
            "VARIANT_ID": "workstation",
            "PRETTY_NAME": "Fedora Linux 45 (Workstation Edition)",
        },
        "cmdline": "quiet root=live:LABEL=Fedora-WS-Live-45 rd.live.image",
        "uefi": True,
        "euid": 1000,
        "session": "wayland",
        "commands": {
            "gnome": (0, "GNOME Shell 51.0\n"),
            "pci": (0, (
                "01:00.0 VGA compatible controller [0300]: "
                "Intel Corporation Arc B580 [8086:e20b]\n"
                "\tKernel driver in use: xe\n"
            )),
            "vulkan": (0, "deviceName = Intel(R) Arc(TM) B580 Graphics"),
            "selinux": (0, "Enforcing\n"),
            "network": (0, "wifi:connected\nethernet:disconnected\n"),
            "audio": (0, "PipeWire"),
            "disks": (0, "disk nvme\ndisk usb\n"),
        },
        "meminfo": "MemTotal: 49000000 kB\n",
    }


def test_stable_live_workstation_readiness_never_claims_install_certification() -> None:
    report = check.assess(_evidence())
    assert report["precheck"] == "READY_FOR_MANUAL_REVIEW"
    assert report["installation_authorized"] is False
    assert report["installation_performed"] is False
    assert report["storage_written"] is False
    assert report["verdict"] == "NOT_INSTALLED_NOT_END_TO_END_QUALIFIED"
    assert not report["critical_checks_not_passed"]
    assert report["checks"]["xe_driver"]["status"] == "PASS"
    assert report["outstanding_manual_proofs"]


def test_beta_or_normal_installed_session_blocks_preflight() -> None:
    source = _evidence()
    source["release"]["PRETTY_NAME"] = "Fedora Linux 45 Beta"
    assert "fedora_45_workstation" in check.assess(source)["critical_checks_not_passed"]
    source = _evidence()
    source["cmdline"] = "quiet root=UUID=internal-nvme-partition"
    report = check.assess(source)
    assert "live_session" in report["critical_checks_not_passed"]


def test_driver_must_belong_to_b580_not_another_intel_gpu() -> None:
    source = _evidence()
    source["commands"]["pci"] = (0, (
        "00:02.0 VGA compatible controller [0300]: Intel Device [8086:abcd]\n"
        "\tKernel driver in use: xe\n"
        "01:00.0 VGA compatible controller [0300]: "
        "Intel Arc B580 [8086:e20b]\n"
        "\tKernel modules: xe\n"
    ))
    report = check.assess(source)
    assert report["checks"]["arc_b580"]["status"] == "PASS"
    assert report["checks"]["xe_driver"]["status"] == "FAIL"
    assert report["precheck"] == "BLOCKED"


def test_missing_optional_vulkan_is_not_fake_pass() -> None:
    source = _evidence()
    source["commands"]["vulkan"] = (None, "")
    report = check.assess(source)
    assert report["checks"]["vulkan_b580"]["status"] == "REVIEW"
    assert report["installation_authorized"] is False


def test_missing_gpu_probing_command_blocks_premature_installation() -> None:
    source = _evidence()
    source["commands"]["pci"] = (None, "")
    report = check.assess(source)
    assert {"arc_b580", "xe_driver"} <= set(report["critical_checks_not_passed"])


def test_release_file_parser_never_evaluates_shell_code() -> None:
    result = check.release_fields(
        'ID=fedora\nVERSION_ID="45"\nVARIANT_ID=workstation\n'
        "SUSPICIOUS=$(touch /tmp/should-not-exist)\n"
    )
    assert result["ID"] == "fedora"
    assert result["VERSION_ID"] == "45"
    assert result["SUSPICIOUS"] == "$(touch /tmp/should-not-exist)"


def test_command_allowlist_is_read_only_and_ignores_user_input() -> None:
    allowed = {items[0] for items in check.COMMANDS.values()}
    assert allowed == {
        "gnome-shell", "lspci", "vulkaninfo", "getenforce",
        "nmcli", "wpctl", "lsblk",
    }
    assert not {"sudo", "dd", "mkfs", "dnf", "rpm", "mount", "systemctl"} & allowed


def test_root_cli_is_refused_without_running_probes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(check.os, "geteuid", lambda: 0)
    assert check.main([]) == 2
    assert "REFUSED" in capsys.readouterr().out
