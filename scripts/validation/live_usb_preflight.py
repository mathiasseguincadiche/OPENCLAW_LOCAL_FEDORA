"""Read-only Fedora Workstation Live USB hardware prequalification.

Run without installing Python packages or enabling services:
    python3 scripts/validation/live_usb_preflight.py

NEVER mounts/formats/installs/writes to a block device. Only local observations.
This deliberately cannot certify OpenClaw, a deployed WebUI or hardware stability.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

COMMANDS: dict[str, tuple[str, ...]] = {
    "gnome": ("gnome-shell", "--version"),
    "pci": ("lspci", "-nnk"),
    "vulkan": ("vulkaninfo", "--summary"),
    "selinux": ("getenforce",),
    "network": ("nmcli", "-t", "-f", "TYPE,STATE", "device", "status"),
    "audio": ("wpctl", "status"),
    "disks": ("lsblk", "-dn", "-o", "TYPE,TRAN"),
}
REQUIRED = (
    "live_session", "fedora_45_workstation", "uefi_boot", "gnome_51",
    "wayland_session", "arc_b580", "xe_driver",
)
OUTSTANDING = (
    "official_stable_ISO_origin_and_signed_checksum_manual",
    "actual_multi_monitor_refresh_and_white_point_manual",
    "wifi_internet_bluetooth_audio_microphone_camera_USB_manual",
    "B580_AV1_encode_decode_real_media_manual",
    "5_sleep_resume_cycles_manual_and_post_install",
    "Fedora_45_installed_SELinux_systemd_boot_validation",
    "Ollama_OpenClaw_WebUI_real_install_and_agents",
    "8K_16K_32K_near_limit_gpu_model_benchmark",
    "OpenRouter_real_opt_in_billing_reconciliation",
    "real_WebUI_browser_SSE_audio_and_backup_restore",
)


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:120_000]
    except OSError:
        return ""


def release_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            if re.fullmatch(r"[A-Z_]+", key):
                fields[key] = value.strip().strip("\"'")
    return fields


def _command(argv: tuple[str, ...]) -> tuple[int | None, str]:
    """Fixed read-only commands only; never pass any user-supplied arguments."""
    if not shutil.which(argv[0]):
        return None, ""
    try:
        result = subprocess.run(
            argv, check=False, capture_output=True, text=True, timeout=12,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, ""
    # No command output is ever put into the report verbatim (PII/SSID safe).
    return result.returncode, result.stdout[:120_000]


def collect() -> dict[str, Any]:
    return {
        "release": release_fields(_text(Path("/etc/os-release"))),
        "cmdline": _text(Path("/proc/cmdline")),
        "uefi": Path("/sys/firmware/efi").is_dir(),
        "euid": os.geteuid(),
        "session": os.environ.get("XDG_SESSION_TYPE", "").lower(),
        "commands": {name: _command(argv) for name, argv in COMMANDS.items()},
        "meminfo": _text(Path("/proc/meminfo")),
    }


def _check(condition: bool | None, success: str, missing: str) -> dict[str, str]:
    if condition is None:
        return {"status": "REVIEW", "detail": missing}
    return {"status": "PASS" if condition else "FAIL",
            "detail": success if condition else missing}


def _gpu_block(pci: str) -> str:
    # Isolate a single PCI device so another GPU's xe driver cannot satisfy B580.
    records = re.split(
        r"(?im)^(?=(?:[0-9a-f]{4}:)?[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]\s)",
        pci,
    )
    return next(
        (part for part in records if "8086:e20b" in part.lower()
         or re.search(r"arc.{0,35}b580", part, re.IGNORECASE)),
        "",
    )


def assess(evidence: dict[str, Any]) -> dict[str, Any]:
    release = evidence["release"]
    commands = evidence["commands"]
    cmdline = evidence["cmdline"]
    # A Live boot is indicated by dracut kernel options, not merely an overlay.
    live = "root=live:" in cmdline or "rd.live.image" in cmdline.split()
    gnome_rc, gnome = commands["gnome"]
    pci_rc, pci = commands["pci"]
    gpu = _gpu_block(pci) if pci_rc == 0 else ""
    vulkan_rc, vulkan = commands["vulkan"]
    selinux_rc, selinux = commands["selinux"]
    net_rc, network = commands["network"]
    audio_rc, _ = commands["audio"]
    disks_rc, disks = commands["disks"]
    mem = re.search(r"(?m)^MemTotal:\s+(\d+)\s+kB", evidence["meminfo"])
    ram_gib = round(int(mem.group(1)) / 1024**2, 1) if mem else None

    checks: dict[str, dict[str, str]] = {
        "live_session": _check(
            live, "Démarrage Live détecté", "Démarrer en mode Essayer Fedora depuis la clé USB"
        ),
        "fedora_45_workstation": _check(
            release.get("ID") == "fedora" and release.get("VERSION_ID") == "45"
            and release.get("VARIANT_ID") == "workstation"
            and not re.search(
                r"beta|alpha|prerelease|rawhide|testing",
                " ".join([release.get("PRETTY_NAME", ""), release.get("VERSION", "")]),
                re.IGNORECASE,
            ),
            "Fedora 45 Workstation identifié (signature de l'ISO à vérifier séparément)",
            "Fedora 45 Workstation finale requise (pas bêta/Rawhide)",
        ),
        "uefi_boot": _check(
            bool(evidence["uefi"]), "Démarrage UEFI", "Session non démarrée en UEFI"
        ),
        "gnome_51": _check(
            None if gnome_rc is None else bool(
                gnome_rc == 0 and re.search(r"GNOME Shell 51(?:\.|\b)", gnome)
            ),
            "GNOME Shell 51 détecté", "GNOME 51 absent ou version incorrecte",
        ),
        "wayland_session": _check(
            evidence["session"] == "wayland",
            "Session Wayland", "Session Wayland non détectée",
        ),
        "arc_b580": _check(
            None if pci_rc is None else bool(gpu),
            "Intel Arc B580 (8086:e20b) détectée",
            "Arc B580 non détectée par lspci",
        ),
        "xe_driver": _check(
            None if pci_rc is None or not gpu else bool(
                re.search(r"(?im)^\s*Kernel driver in use:\s*xe\s*$", gpu)
            ),
            "Pilote noyau xe attaché à la B580",
            "Pilote xe non confirmé sur le périphérique B580",
        ),
        "vulkan_b580": _check(
            None if vulkan_rc is None else bool(
                vulkan_rc == 0 and re.search(r"\bB580\b", vulkan, re.IGNORECASE)
            ),
            "Vulkan annonce la B580 (performances non mesurées)",
            "Vulkan/B580 non vérifié ; outil ou pilote à examiner",
        ),
        "selinux_live": _check(
            None if selinux_rc is None else (
                selinux_rc == 0 and selinux.strip() == "Enforcing"
            ),
            "SELinux Enforcing en session Live",
            "SELinux Enforcing non confirmé ; à recontrôler après installation",
        ),
        "ram_48gb_class": _check(
            None if ram_gib is None else ram_gib >= 40,
            "Mémoire système >= 40 Gio détectée",
            "Mémoire attendue non confirmée (configuration cible : 48 Go)",
        ),
        "network_link": _check(
            None if net_rc is None else (
                net_rc == 0 and any(
                    line.lower().endswith(":connected")
                    for line in network.splitlines()
                )
            ),
            "Au moins un lien réseau connecté (Internet non testé)",
            "Liaison réseau non confirmée",
        ),
        "audio_service": _check(
            None if audio_rc is None else audio_rc == 0,
            "PipeWire/WirePlumber interrogé (lecture audio non testée)",
            "Service audio non confirmé ; test manuel requis",
        ),
        "storage_enumeration": _check(
            None if disks_rc is None else (
                disks_rc == 0 and any("disk" in line for line in disks.splitlines())
            ),
            "Disques détectés en lecture seule (aucune écriture)",
            "Inventaire disques impossible ; vérifier avant installation",
        ),
    }
    # Even a passing check does not certify a real codec test, sleep, WebUI or
    # actual application install. Missing optional tools are REVIEW, not PASS.
    blocked = [key for key in REQUIRED if checks[key]["status"] != "PASS"]
    return {
        "schema_version": "1.0.0",
        "observed_at_utc": datetime.now(UTC).isoformat(),
        "mode": "LIVE_USB_READ_ONLY",
        "storage_written": False,
        "commands_execute_shell": False,
        "installation_performed": False,
        "installation_authorized": False,
        "precheck": "BLOCKED" if blocked else "READY_FOR_MANUAL_REVIEW",
        "verdict": "NOT_INSTALLED_NOT_END_TO_END_QUALIFIED",
        "critical_checks_not_passed": blocked,
        "checks": checks,
        "outstanding_manual_proofs": list(OUTSTANDING),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Préqualification matérielle Live USB Fedora 45 sans écrire sur les disques"
    )
    parser.add_argument("--json", action="store_true", help="Afficher un rapport JSON synthétique")
    args = parser.parse_args(argv)
    if os.geteuid() == 0:
        print("LIVE_USB_RESULT=REFUSED: exécuter comme utilisateur Live, sans sudo")
        return 2
    result = assess(collect())
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("LIVE_USB_PRECHECK=" + str(result["precheck"]))
        for key, check in result["checks"].items():
            print(f"  {check['status']:6} {key}: {check['detail']}")
        print("INSTALLATION_AUTHORIZED=false")
        print("Rester en mode Live : compléter les tests manuels avant toute installation.")
        print("Rapport JSON facultatif : ajouter --json (rediriger seulement vers la clé USB).")
    return 0 if result["precheck"] == "READY_FOR_MANUAL_REVIEW" else 1


if __name__ == "__main__":
    raise SystemExit(main())
