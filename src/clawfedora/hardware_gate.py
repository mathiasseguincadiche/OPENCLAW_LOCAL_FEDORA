from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from clawfedora.core_config import root_contract


@dataclass(frozen=True)
class GateCheck:
    id: str
    status: str
    detail: str


@dataclass(frozen=True)
class HardwareGateReport:
    gate: str
    checks: tuple[GateCheck, ...]
    collected_at: str

    @property
    def failures(self) -> int:
        return sum(item.status == "FAIL" for item in self.checks)

    @property
    def warnings(self) -> int:
        return sum(item.status == "WARN" for item in self.checks)

    @property
    def ok(self) -> bool:
        return self.failures == 0

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "gate": self.gate,
            "collected_at": self.collected_at,
            "kernel": platform.release(),
            "verdict": "PASS" if self.ok else "FAIL",
            "failures": self.failures,
            "warnings": self.warnings,
            "checks": [asdict(item) for item in self.checks],
        }

    def to_json(self) -> str:
        return json.dumps(self.payload(), indent=2, ensure_ascii=False)


def _run(command: list[str], timeout: int = 15) -> tuple[int, str]:
    executable = shutil.which(command[0])
    if executable is None:
        return 127, f"commande absente: {command[0]}"
    try:
        completed = subprocess.run(
            [executable, *command[1:]],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 126, str(exc)
    return completed.returncode, (completed.stdout + "\n" + completed.stderr).strip()


def _os_release() -> dict[str, str]:
    path = Path("/etc/os-release")
    if not path.is_file():
        return {}
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        result[key] = value.strip().strip('"')
    return result


def _mem_total_gib() -> float:
    path = Path("/proc/meminfo")
    if not path.is_file():
        return 0.0
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.startswith("MemTotal:"):
            parts = raw.split()
            if len(parts) >= 2:
                return int(parts[1]) / 1024 / 1024
    return 0.0


def _cpu_model() -> str:
    path = Path("/proc/cpuinfo")
    if not path.is_file():
        return "unknown"
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if raw.lower().startswith("model name") and ":" in raw:
            return raw.split(":", 1)[1].strip()
    return "unknown"


def _gnome_major() -> tuple[int | None, str]:
    rc, output = _run(["gnome-shell", "--version"])
    if rc != 0:
        return None, output
    match = re.search(r"\b(\d+)(?:\.\d+)?\b", output)
    return (int(match.group(1)) if match else None), output


def _b580_lspci() -> tuple[bool, str]:
    rc, output = _run(["lspci", "-nnk"])
    if rc != 0:
        return False, output
    lines = output.splitlines()
    matched = [index for index, line in enumerate(lines) if "B580" in line and "Intel" in line]
    if len(matched) != 1:
        return False, "B580 PCI unique non observée"
    start = matched[0]
    block = [lines[start]]
    for line in lines[start + 1 :]:
        if line and not line[0].isspace():
            break
        block.append(line)
    return True, "\n".join(block)


def parse_rebar_current_size(output: str) -> int | None:
    """Return the largest *current* BAR aperture in MiB, never its supported sizes."""
    sizes = re.findall(r"current size:\s*(\d+)\s*(MB|GB)", output, flags=re.IGNORECASE)
    return max(
        (int(number) * (1024 if unit.upper() == "GB" else 1) for number, unit in sizes), default=None
    )


def _rebar_enabled() -> tuple[bool, str]:
    rc, inventory = _run(["lspci", "-Dnn"])
    matches = [
        line.split()[0] for line in inventory.splitlines() if "B580" in line and "Intel" in line
    ]
    if rc != 0 or len(matches) != 1:
        return False, "B580 PCI unique non identifiée; ReBAR non confirmé"
    slot = matches[0]
    rc, output = _run(["lspci", "-s", slot, "-vv"], timeout=20)
    size = parse_rebar_current_size(output) if rc == 0 else None
    # A 12 GiB device needs an aperture large enough for its framebuffer.
    ok = size is not None and size >= 12 * 1024
    return ok, f"B580={slot} current_BAR_MiB={size}; cible>=12288 (permissions requises si inconnu)"


def _check_l2(repo_root: Path) -> list[GateCheck]:
    hardware = root_contract(repo_root, "hardware.yaml")
    host = dict(hardware["host"])
    expected_cpu = str(dict(host["cpu"])["model"])
    min_memory = float(dict(host["memory"])["minimum_supported_gib"])
    checks: list[GateCheck] = []

    release = _os_release()
    fedora = release.get("ID") == "fedora" and release.get("VERSION_ID") == "44"
    checks.append(
        GateCheck(
            "fedora-44",
            "PASS" if fedora else "FAIL",
            f"ID={release.get('ID', '?')} VERSION_ID={release.get('VERSION_ID', '?')}",
        )
    )

    major, gnome = _gnome_major()
    checks.append(
        GateCheck(
            "gnome-50",
            "PASS" if major == 50 else "FAIL",
            gnome or "GNOME Shell non détecté",
        )
    )

    session = os.environ.get("XDG_SESSION_TYPE", "unknown").casefold()
    checks.append(GateCheck("wayland", "PASS" if session == "wayland" else "FAIL", session))

    cpu = _cpu_model()
    checks.append(
        GateCheck(
            "cpu",
            "PASS" if expected_cpu.casefold() in cpu.casefold() else "FAIL",
            cpu,
        )
    )

    threads = os.cpu_count() or 0
    expected_threads = int(dict(host["cpu"])["threads"])
    checks.append(
        GateCheck(
            "cpu-threads",
            "PASS" if threads >= expected_threads else "FAIL",
            f"threads={threads} attendu>={expected_threads}",
        )
    )

    memory = _mem_total_gib()
    minimum_observed = min_memory * 0.95
    checks.append(
        GateCheck(
            "memory",
            "PASS" if memory >= minimum_observed else "FAIL",
            f"MemTotal={memory:.1f} GiB cible={min_memory:.0f} GiB",
        )
    )

    checks.append(
        GateCheck(
            "uefi",
            "PASS" if Path("/sys/firmware/efi").is_dir() else "FAIL",
            "/sys/firmware/efi",
        )
    )

    b580, gpu_detail = _b580_lspci()
    checks.append(GateCheck("gpu-b580", "PASS" if b580 else "FAIL", gpu_detail))

    rebar, rebar_detail = _rebar_enabled()
    checks.append(GateCheck("resizable-bar", "PASS" if rebar else "FAIL", rebar_detail))

    rc, selinux = _run(["getenforce"])
    enforcing = rc == 0 and selinux.strip().casefold() == "enforcing"
    checks.append(
        GateCheck(
            "selinux-enforcing",
            "PASS" if enforcing else "FAIL",
            selinux or "getenforce indisponible",
        )
    )

    rc, systemd_user = _run(["systemctl", "--user", "is-system-running"])
    usable = rc in {0, 1} and "offline" not in systemd_user.casefold()
    checks.append(
        GateCheck(
            "systemd-user",
            "PASS" if usable else "FAIL",
            systemd_user or "systemd --user non joignable",
        )
    )
    return checks


def _check_l3() -> list[GateCheck]:
    checks: list[GateCheck] = []
    b580, gpu_detail = _b580_lspci()
    checks.append(GateCheck("gpu-b580", "PASS" if b580 else "FAIL", gpu_detail))

    bound = "Kernel driver in use: xe" in gpu_detail
    checks.append(
        GateCheck(
            "b580-bound-driver",
            "PASS" if bound else "FAIL",
            "B580 liée à xe" if bound else "driver de la B580 non confirmé",
        )
    )
    rc, lsmod = _run(["lsmod"])
    xe = rc == 0 and any(line.split()[0] == "xe" for line in lsmod.splitlines() if line.split())
    checks.append(
        GateCheck("driver-xe", "PASS" if xe else "FAIL", "xe chargé" if xe else lsmod[-500:])
    )

    nodes = sorted(str(path) for path in Path("/dev/dri").glob("renderD*"))
    checks.append(
        GateCheck(
            "render-node",
            "PASS" if nodes else "FAIL",
            ", ".join(nodes) if nodes else "aucun renderD*",
        )
    )

    rc, groups_output = _run(["id", "-nG"])
    groups = set(groups_output.split()) if rc == 0 else set()
    checks.append(
        GateCheck(
            "group-render",
            "PASS" if "render" in groups else "FAIL",
            ",".join(sorted(groups)) if groups else groups_output,
        )
    )

    rc, mesa = _run(["rpm", "-q", "mesa-vulkan-drivers"])
    checks.append(
        GateCheck(
            "mesa-vulkan",
            "PASS" if rc == 0 else "FAIL",
            mesa or "mesa-vulkan-drivers absent",
        )
    )

    rc, vulkan = _run(["vulkaninfo", "--summary"], timeout=30)
    vulkan_ok = rc == 0 and "B580" in vulkan and "Intel" in vulkan
    checks.append(
        GateCheck(
            "vulkan-b580",
            "PASS" if vulkan_ok else "FAIL",
            "Intel Arc B580 Vulkan opérationnelle" if vulkan_ok else vulkan[-1200:],
        )
    )
    return checks


def collect_hardware_gate(repo_root: Path, gate: str) -> HardwareGateReport:
    normalized = gate.strip().casefold()
    if normalized == "l2":
        checks = _check_l2(repo_root)
    elif normalized == "l3":
        checks = _check_l3()
    else:
        raise ValueError("gate matériel attendu: l2 ou l3")
    return HardwareGateReport(
        gate=normalized.upper(),
        checks=tuple(checks),
        collected_at=datetime.now(UTC).isoformat(),
    )


def _canonical_evidence_directory(directory: Path) -> Path:
    if directory.name == "qualification" and directory.parent.name == "proofs":
        return directory.parent / "hardware"
    return directory


def write_hardware_evidence(report: HardwareGateReport, directory: Path) -> Path:
    canonical = _canonical_evidence_directory(directory)
    canonical.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    path = canonical / f"hardware_{report.gate.casefold()}_{stamp}.json"
    path.write_text(report.to_json() + "\n", encoding="utf-8")
    return path
