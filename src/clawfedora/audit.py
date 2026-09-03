from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class Check:
    id: str
    status: str
    detail: str


@dataclass(frozen=True)
class AuditReport:
    checks: tuple[Check, ...]

    @property
    def failures(self) -> int:
        return sum(check.status == "FAIL" for check in self.checks)

    @property
    def warnings(self) -> int:
        return sum(check.status == "WARN" for check in self.checks)

    @property
    def ok(self) -> bool:
        return self.failures == 0

    def to_json(self) -> str:
        return json.dumps(
            {
                "schema_version": "1.0.0",
                "verdict": "PASS" if self.ok else "FAIL",
                "failures": self.failures,
                "warnings": self.warnings,
                "checks": [asdict(check) for check in self.checks],
            },
            indent=2,
            ensure_ascii=False,
        )


def _run(command: Sequence[str], timeout: int = 10) -> tuple[int, str]:
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
    output = (completed.stdout + "\n" + completed.stderr).strip()
    return completed.returncode, output


def _os_release() -> dict[str, str]:
    result: dict[str, str] = {}
    path = Path("/etc/os-release")
    if not path.is_file():
        return result
    for raw in path.read_text(encoding="utf-8").splitlines():
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        result[key] = value.strip().strip('"')
    return result


def collect_audit(strict: bool = False) -> AuditReport:
    checks: list[Check] = []
    os_release = _os_release()
    fedora44 = os_release.get("ID") == "fedora" and os_release.get("VERSION_ID") == "44"
    checks.append(
        Check(
            "os-fedora44",
            "PASS" if fedora44 else ("FAIL" if strict else "WARN"),
            f"ID={os_release.get('ID', '?')} VERSION_ID={os_release.get('VERSION_ID', '?')}",
        )
    )

    kernel = platform.release()
    checks.append(Check("kernel", "PASS", kernel))

    session = os.environ.get("XDG_SESSION_TYPE", "unknown").lower()
    checks.append(
        Check(
            "wayland",
            "PASS" if session == "wayland" else ("FAIL" if strict else "WARN"),
            f"XDG_SESSION_TYPE={session}",
        )
    )

    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "unknown")
    desktop_ok = "GNOME" in desktop.upper()
    checks.append(
        Check(
            "gnome",
            "PASS" if desktop_ok else ("FAIL" if strict else "WARN"),
            f"XDG_CURRENT_DESKTOP={desktop}",
        )
    )

    rc, lspci = _run(["lspci", "-nn"])
    b580 = rc == 0 and "B580" in lspci and "Intel" in lspci
    checks.append(
        Check(
            "gpu-b580",
            "PASS" if b580 else ("FAIL" if strict else "WARN"),
            "Intel Arc B580 détectée" if b580 else lspci[-500:] or "GPU non détectée",
        )
    )

    rc, lsmod = _run(["lsmod"])
    xe_loaded = rc == 0 and any(line.split()[0] == "xe" for line in lsmod.splitlines() if line)
    checks.append(
        Check(
            "driver-xe",
            "PASS" if xe_loaded else ("FAIL" if strict else "WARN"),
            "module xe chargé" if xe_loaded else "module xe non observé",
        )
    )

    render_nodes = sorted(str(path) for path in Path("/dev/dri").glob("renderD*"))
    checks.append(
        Check(
            "drm-render-node",
            "PASS" if render_nodes else ("FAIL" if strict else "WARN"),
            ", ".join(render_nodes) if render_nodes else "aucun /dev/dri/renderD*",
        )
    )

    rc, groups_output = _run(["id", "-nG"])
    groups = set(groups_output.split()) if rc == 0 else set()
    render_membership = "render" in groups
    checks.append(
        Check(
            "group-render",
            "PASS" if render_membership else ("FAIL" if strict else "WARN"),
            "groupes=" + ",".join(sorted(groups)) if groups else groups_output,
        )
    )

    rc, selinux = _run(["getenforce"])
    enforcing = rc == 0 and selinux.strip().lower() == "enforcing"
    checks.append(
        Check(
            "selinux",
            "PASS" if enforcing else ("FAIL" if strict else "WARN"),
            selinux or "getenforce indisponible",
        )
    )

    rc, vulkan = _run(["vulkaninfo", "--summary"], timeout=20)
    vulkan_ok = rc == 0 and ("B580" in vulkan or "Intel" in vulkan)
    checks.append(
        Check(
            "vulkan",
            "PASS" if vulkan_ok else ("FAIL" if strict else "WARN"),
            "Vulkan Intel opérationnel" if vulkan_ok else vulkan[-800:] or "vulkaninfo indisponible",
        )
    )

    rc, level_zero = _run(["rpm", "-q", "intel-level-zero"])
    l0_ok = rc == 0
    checks.append(
        Check(
            "level-zero-runtime",
            "PASS" if l0_ok else ("FAIL" if strict else "WARN"),
            level_zero,
        )
    )

    rc, compute_runtime = _run(["rpm", "-q", "intel-compute-runtime"])
    compute_ok = rc == 0
    checks.append(
        Check(
            "intel-compute-runtime",
            "PASS" if compute_ok else ("FAIL" if strict else "WARN"),
            compute_runtime,
        )
    )

    rc, sycl = _run(["sycl-ls"], timeout=20)
    sycl_ok = rc == 0 and "level_zero" in sycl.lower() and "gpu" in sycl.lower()
    checks.append(
        Check(
            "sycl-candidate",
            "PASS" if sycl_ok else "WARN",
            "SYCL/Level Zero disponible" if sycl_ok else "optionnel avant qualification: " + sycl[-500:],
        )
    )

    preferred_root = Path("/srv/openclaw-local")
    checks.append(
        Check(
            "runtime-root",
            "PASS" if preferred_root.is_dir() else "WARN",
            str(preferred_root) if preferred_root.is_dir() else "/srv/openclaw-local non préparé",
        )
    )

    rc, service = _run(["systemctl", "--user", "is-system-running"])
    systemd_user_ok = rc in {0, 1} and "offline" not in service.lower()
    checks.append(
        Check(
            "systemd-user",
            "PASS" if systemd_user_ok else ("FAIL" if strict else "WARN"),
            service or "systemd --user non joignable",
        )
    )

    return AuditReport(tuple(checks))
