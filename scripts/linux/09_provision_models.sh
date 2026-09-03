#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
# shellcheck source=scripts/linux/lib/runtime.sh
source "$REPO_ROOT/scripts/linux/lib/runtime.sh"

APPLY=0
[[ "${1:-}" == "--apply" ]] && APPLY=1
PYTHON="$(claw_python)"

run_ops() {
  if "$PYTHON" -c 'import clawfedora' >/dev/null 2>&1; then
    "$PYTHON" -m clawfedora.ops_cli --root "$REPO_ROOT" "$@"
  else
    PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
      "$PYTHON" -m clawfedora.ops_cli --root "$REPO_ROOT" "$@"
  fi
}

if ((APPLY == 0)); then
  run_ops models
  echo "MODEL_PROVISION_PLAN=PASS apply=false"
  exit 0
fi

command -v ollama >/dev/null 2>&1 || {
  echo "MODEL_PROVISION_RESULT=FAIL ollama absent" >&2
  exit 2
}
run_ops models --apply
