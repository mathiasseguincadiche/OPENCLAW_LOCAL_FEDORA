"""Short read-only acceptance test for installed Fedora + B580 + IA stack.
Run after installing OpenClaw and WebUI. Does not test cloud or GPU stress.
"""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from clawfedora.lifecycle import collect_health
from clawfedora.storage import load_settings, require_storage

ENDPOINTS = {
    "WebUI": "http://127.0.0.1:3000/health",
    "Projects": "http://127.0.0.1:18890/api/status",
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: urllib.request.Request, fp: Any, code: int,
                         msg: str, headers: Any, newurl: str) -> None:
        return None


def local_ok(url: str) -> bool:
    if url not in ENDPOINTS.values():
        raise ValueError("sonde externe interdite")
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), NoRedirect(),
    )
    try:
        with opener.open(urllib.request.Request(url, method="GET"), timeout=5) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def report(repo: Path, runtime: Path) -> dict[str, Any]:
    require_storage(runtime, load_settings(repo))
    if not (runtime / ".openclaw-fedora-runtime").is_file():
        raise ValueError("atelier IA non installé")
    health = collect_health(repo, runtime, probe=True)
    health_checks = {c.id: c.status == "PASS" for c in health.checks}
    endpoints = {key: local_ok(url) for key, url in ENDPOINTS.items()}
    projects = (runtime / "projects").is_dir()
    all_good = health.ok and all(endpoints.values()) and projects
    return {
        "verdict": "READY_FOR_FIRST_PROJECT" if all_good else "REVIEW_REQUIRED",
        "secondary_storage": True,
        "local_model_and_system": health_checks,
        "interfaces": endpoints,
        "projects_directory": projects,
        "remote_cloud_tested": False,
        "long_gpu_stress_tested": False,
        "real_world_agent_quality_tested": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, default=load_settings().runtime_root)
    args = parser.parse_args(argv)
    try:
        payload = report(args.root, args.runtime_root)
    except (OSError, ValueError) as exc:
        print(json.dumps({"verdict": "REFUSED", "reason": str(exc)}, ensure_ascii=False))
        return 2
    for section in ("local_model_and_system", "interfaces"):
        for name, value in payload[section].items():
            print(f"{'PASS' if value else 'FAIL'} {name}")
    print(f"{'PASS' if payload['projects_directory'] else 'FAIL'} projects_directory")
    print("RECEPTION=" + str(payload["verdict"]))
    print("CLOUD=NOT_TESTED (opt-in separate) GPU_STRESS=NOT_TESTED (optional)")
    return 0 if payload["verdict"] == "READY_FOR_FIRST_PROJECT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
