#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=scripts/linux/lib/runtime.sh
source "$SCRIPT_DIR/lib/runtime.sh"

REPO_ROOT="$(claw_repo_root)"
RUNTIME_ROOT="$(claw_runtime_root)"
PYTHON="$(claw_python)"

"$PYTHON" -m clawfedora.cli --root "$REPO_ROOT" agents deploy --runtime-root "$RUNTIME_ROOT"
