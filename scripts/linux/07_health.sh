#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
# shellcheck source=scripts/linux/lib/runtime.sh
source "$REPO_ROOT/scripts/linux/lib/runtime.sh"
PYTHON="$(claw_python)"
RUNTIME_ROOT="$(claw_runtime_root)"

if "$PYTHON" -c 'import clawfedora' >/dev/null 2>&1; then
  exec "$PYTHON" -m clawfedora.ops_cli --root "$REPO_ROOT" --runtime-root "$RUNTIME_ROOT" health
fi
PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
  exec "$PYTHON" -m clawfedora.ops_cli --root "$REPO_ROOT" --runtime-root "$RUNTIME_ROOT" health
