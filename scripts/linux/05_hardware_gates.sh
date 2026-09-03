#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=scripts/linux/lib/runtime.sh
source "$SCRIPT_DIR/lib/runtime.sh"

GATE="${1:-}"
case "$GATE" in
  l2|l3) ;;
  *) echo "Usage: 05_hardware_gates.sh l2|l3" >&2; exit 2 ;;
esac

REPO_ROOT="$(claw_repo_root)"
RUNTIME_ROOT="$(claw_runtime_root)"
PYTHON="$(claw_python)"

if "$PYTHON" -c 'import clawfedora' >/dev/null 2>&1; then
  exec "$PYTHON" -m clawfedora.cli --root "$REPO_ROOT" hardware \
    --gate "$GATE" --runtime-root "$RUNTIME_ROOT"
fi

PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
  exec "$PYTHON" -m clawfedora.cli --root "$REPO_ROOT" hardware \
    --gate "$GATE" --runtime-root "$RUNTIME_ROOT"
