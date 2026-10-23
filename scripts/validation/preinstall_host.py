"""Preinstallation checks: Python standard library only, read-only, no sudo."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))


def text(path: str | Path) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def cmd(*args: str) -> tuple[int, str]:
    if shutil.which(args[0]) is None:
        return 127, ""
    try:
        out = subprocess.run(args, text=True, capture_output=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return 126, ""
    return out.returncode, out.stdout.strip()


def collect() -> list[tuple[str, str, str]]:
    from clawfedora.storage import free_bytes, load_settings, require_storage

    result: list[tuple[str, str, str]] = []

    def add(key: str, passed: bool, detail: str, advisory: bool = False) -> None:
        result.append((key, "PASS" if passed else ("REVIEW" if advisory else "FAIL"), detail))

    info = dict(line.split("=", 1) for line in text("/etc/os-release").splitlines()
                if "=" in line)
    info = {k: v.strip().strip('"') for k, v in info.items()}
    add("non-root", os.geteuid() != 0, "Compte utilisateur Fedora requis")
    add("fedora-45", info.get("ID") == "fedora"
        and info.get("VERSION_ID") == "45"
        and info.get("VARIANT_ID") == "workstation"
        and info.get("RELEASE_TYPE", "stable") == "stable",
        "Fedora 45 Workstation stable requis")
    rc, gnome = cmd("gnome-shell", "--version")
    add("gnome-51", rc == 0 and bool(re.search(r"GNOME Shell 51(?:\b|\.)", gnome)),
        "GNOME Shell 51 requis")
    add("wayland", os.environ.get("XDG_SESSION_TYPE") == "wayland", "Session Wayland requise")
    add("uefi", Path("/sys/firmware/efi").is_dir(), "Démarrage UEFI requis")
    rc, se = cmd("getenforce")
    add("selinux", rc == 0 and se == "Enforcing", "SELinux Enforcing requis")
    add("cpu", "AMD Ryzen 7 7700" in text("/proc/cpuinfo"), "Ryzen 7 7700 requis")
    add("threads", (os.cpu_count() or 0) >= 16, "16 threads nécessaires")
    memory = re.search(r"(?m)^MemTotal:\s+(\d+)", text("/proc/meminfo"))
    add("memory", memory is not None and int(memory.group(1)) >= 47_000_000,
        "48 Go de RAM installée attendus")
    gpu = next((p for p in Path("/sys/bus/pci/devices").glob("*")
                if text(p / "vendor").strip() == "0x8086"
                and text(p / "device").strip() == "0xe20b"), None)
    add("b580", gpu is not None, "Intel Arc B580 PCI 8086:e20b requise")
    add("driver-xe", gpu is not None and (gpu / "driver").exists()
        and (gpu / "driver").resolve().name == "xe", "Pilote xe lié à la B580 requis")
    settings = load_settings()
    runtime, mount = settings.runtime_root, settings.mountpoint
    try:
        require_storage(runtime, settings)
        add("storage", True, f"{mount} monté, EXT4, distinct du système; runtime={runtime}")
        add("disk-free", free_bytes(mount) >= settings.minimum_data_gib * 1024**3,
            f"{settings.minimum_data_gib} GiB libres minimum sur {mount}")
        parent = runtime
        while not parent.exists():
            parent = parent.parent
        access = os.access(parent, os.X_OK) and (not runtime.exists()
                                                or os.access(runtime, os.W_OK))
        add("storage-access", access, "Accès au runtime ou à son parent existant requis")
        add("storage-create", os.access(parent, os.W_OK),
            "Si nécessaire, bootstrap créera uniquement les dossiers IA avec sudo",
            advisory=True)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        add("storage", False, str(exc))
    add("system-free", free_bytes(Path("/")) >= settings.minimum_system_gib * 1024**3,
        f"{settings.minimum_system_gib} GiB libres minimum sur le SSD système")
    for tool in ("dnf5", "sudo", "python3", "systemctl"):
        add("required-" + tool, shutil.which(tool) is not None,
            "Outil Fedora requis avant l'installation")
    rc, _ = cmd("systemctl", "--user", "show-environment")
    add("systemd-user", rc == 0, "Session utilisateur systemd nécessaire")
    for tool in ("curl", "jq", "lspci", "vulkaninfo", "node", "npm",
                 "zstd", "python3.13", "podman"):
        add("to-install-" + tool, shutil.which(tool) is not None,
            "Absent avant bootstrap: sera installé par le projet", advisory=True)
    rc, net = cmd("nmcli", "-t", "-f", "CONNECTIVITY", "general")
    add("internet", rc == 0 and net.splitlines()[:1] == ["full"],
        "Vérifier réseau avant les téléchargements", advisory=True)
    add("rebar", False, "Vérifier ReBAR dans l'UEFI avant 32K", advisory=True)
    add("gpu-vram-32k", False, "VRAM et génération réelle testées ensuite", advisory=True)
    return result


def main() -> int:
    print("PRECHECK_PLAN=READ_ONLY no_install=true no_network_calls=true")
    try:
        result = collect()
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(f"PRECHECK=BLOCKED: {exc}")
        return 2
    for name, status, note in result:
        print(f"{status:<6} {name:<25} {note}")
    failures = sum(status == "FAIL" for _, status, _ in result)
    print(f"PRECHECK={'BLOCKED' if failures else 'READY_TO_INSTALL'} "
          f"failures={failures} reviews={sum(x[1] == 'REVIEW' for x in result)}")
    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
