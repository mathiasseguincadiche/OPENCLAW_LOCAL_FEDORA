#!/usr/bin/env bash
set -Eeuo pipefail
REPO_ROOT="$(cd -- "$(dirname -- "$0")/../.." && pwd -P)"
[[ $# -eq 0 ]] || { echo "Usage: precheck (lecture seule, sans --apply)" >&2; exit 2; }
command -v python3 >/dev/null 2>&1 || { echo "PRECHECK=BLOCKED python3 absent" >&2; exit 2; }
exec python3 "$REPO_ROOT/scripts/validation/preinstall_host.py"
