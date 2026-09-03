#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# Runtime path is derived from this script's canonical directory.
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/runtime.sh"

STRICT=0
JSON=0
for arg in "$@"; do
  case "$arg" in
    --strict) STRICT=1 ;;
    --json) JSON=1 ;;
    -h|--help)
      echo "Usage: 01_audit_host.sh [--strict] [--json]"
      exit 0
      ;;
    *) echo "ERREUR: argument inconnu: $arg" >&2; exit 2 ;;
  esac
done

PYTHON="$(claw_python)"
REPO_ROOT="$(claw_repo_root)"
ARGS=(--root "$REPO_ROOT" audit)
((STRICT == 1)) && ARGS+=(--strict)
((JSON == 1)) && ARGS+=(--json)

if "$PYTHON" -c 'import clawfedora' >/dev/null 2>&1; then
  exec "$PYTHON" -m clawfedora.cli "${ARGS[@]}"
fi

PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
  exec "$PYTHON" -m clawfedora.cli "${ARGS[@]}"
