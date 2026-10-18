"""Read-only Fedora runtime readiness evidence. Never claims end-to-end qualification.

Only fixed local commands and loopback /health endpoints are inspected.
No credential, pipeline, model prompt, backup, migration or cloud call is made.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from clawfedora.core_config import root_contract


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A local /health response must never send a readiness probe to the internet."""

    def redirect_request(
        self, req: urllib.request.Request, fp: Any, code: int,
        msg: str, headers: Any, newurl: str,
    ) -> None:
        return None


SERVICES = (
    "openclaw-gateway.service",
    "clawfedora-webui-bridge.service",
    "clawfedora-webui.service",
    "clawfedora-dashboard.service",
    "clawfedora-speech.service",
)
LOOPBACK = {
    "webui": "http://127.0.0.1:3000/health",
    "dashboard": "http://127.0.0.1:18890/health",
}


def fixed_command(args: list[str]) -> bool:
    try:
        result = subprocess.run(
            args, capture_output=True, text=False, check=False, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def loopback_health(url: str) -> bool:
    # No target URL can come from model, user, command output or network response.
    if url not in LOOPBACK.values():
        raise ValueError("Destination locale non autorisée")
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), _NoRedirect()
    )
    try:
        with opener.open(
            urllib.request.Request(url, method="GET"), timeout=4
        ) as response:
            return bool(response.status == 200)
    except (OSError, urllib.error.URLError):
        return False


def readiness(
    repo_root: Path,
    runtime: Path,
    *,
    command: Callable[[list[str]], bool] = fixed_command,
    health: Callable[[str], bool] = loopback_health,
) -> dict[str, Any]:
    """Safe precheck, not evidence of real streaming/GPU/backup/cloud success."""
    if not (repo_root / "config/webui_policy.yaml").is_file():
        raise ValueError("Source de configuration WebUI introuvable")
    for root in (repo_root, runtime):
        if not root.is_absolute() or any(p.is_symlink() for p in (root, *root.parents)):
            raise ValueError("Chemin relatif ou lien symbolique interdit")
    if not (runtime / ".openclaw-fedora-runtime").is_file():
        raise ValueError("Runtime Fedora géré absent")
    release = root_contract(repo_root, "webui_policy.yaml")["release"]
    services = {
        service: command(["systemctl", "--user", "is-active", "--quiet", service])
        for service in SERVICES
    }
    enabled = {
        service: command(["systemctl", "--user", "is-enabled", "--quiet", service])
        for service in SERVICES
    }
    loopback = {key: health(url) for key, url in LOOPBACK.items()}
    local_model = command(["systemctl", "is-active", "--quiet", "ollama.service"])
    local_model_enabled = command(["systemctl", "is-enabled", "--quiet", "ollama.service"])
    checks = {
        "systemd_user_services": services,
        "systemd_user_services_enabled": enabled,
        "loopback_health": loopback,
        "ollama_system_service_active": local_model,
        "ollama_system_service_enabled": local_model_enabled,
    }
    complete = (
        all(services.values()) and all(enabled.values())
        and all(loopback.values()) and local_model and local_model_enabled
    )
    return {
        "schema_version": "1.0.0",
        "observed_at_utc": datetime.now(UTC).isoformat(),
        "open_webui_policy_release": release,
        "checks": checks,
        "precheck": "READY_FOR_MANUAL_TESTS" if complete else "INCOMPLETE",
        "verdict": "NOT_END_TO_END_QUALIFIED",
        "no_sensitive_values_collected": True,
        "outstanding_manual_proofs": [
            "SSE_first_chunk_before_end_and_cancel",
            "local_Qwen_exact_model_digest_and_no_fallback",
            "Fedora_B580_real_GPU_AV1_and_sleep",
            "OpenRouter_opt_in_cost_reconciliation",
            "WebUI_v0.12.3_first_install_browser_and_storage",
            "backup_archive_restore_to_separate_destination",
            "PDF_DOCX_Drawio_visual_inspection",
            "local_image_and_scanned_PDF_vision_accuracy",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Précontrôle local Fedora, sans mutation et sans secrets"
    )
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--runtime-root", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = readiness(args.root, args.runtime_root)
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({"precheck": "REFUSED", "reason": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["precheck"] == "READY_FOR_MANUAL_TESTS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
