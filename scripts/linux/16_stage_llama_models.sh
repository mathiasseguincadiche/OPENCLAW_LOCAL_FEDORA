#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd -P)"
# shellcheck source=scripts/linux/lib/runtime.sh
source "$SCRIPT_DIR/lib/runtime.sh"

APPLY=0
[[ "${1:-}" == "--apply" ]] && APPLY=1
PYTHON="$(claw_python)"
ARGS=(--root "$REPO_ROOT" --runtime-root "$(claw_runtime_root)" stage-models)
((APPLY == 1)) && ARGS+=(--apply)

if "$PYTHON" -c 'import clawfedora' >/dev/null 2>&1; then
  exec "$PYTHON" -m clawfedora.optimization_cli "${ARGS[@]}"
fi
PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
  exec "$PYTHON" -m clawfedora.optimization_cli "${ARGS[@]}"
