#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
# shellcheck source=scripts/linux/lib/runtime.sh
source "$REPO_ROOT/scripts/linux/lib/runtime.sh"
PYTHON="$(claw_python)"
RUNTIME_ROOT="$(claw_runtime_root)"

run_ops() {
  if "$PYTHON" -c 'import clawfedora' >/dev/null 2>&1; then
    "$PYTHON" -m clawfedora.ops_cli --root "$REPO_ROOT" --runtime-root "$RUNTIME_ROOT" "$@"
  else
    PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
      "$PYTHON" -m clawfedora.ops_cli --root "$REPO_ROOT" --runtime-root "$RUNTIME_ROOT" "$@"
  fi
}

case "${1:-}" in
  backup)
    shift
    if [[ "${1:-}" == "--output-dir" ]]; then
      [[ -n "${2:-}" ]] || { echo "ERREUR: --output-dir exige une valeur" >&2; exit 2; }
      run_ops backup --output-dir "$2"
    else
      run_ops backup
    fi
    ;;
  restore)
    [[ -n "${2:-}" && -n "${3:-}" ]] || {
      echo "Usage: $0 restore ARCHIVE DESTINATION" >&2
      exit 2
    }
    run_ops restore "$2" "$3"
    ;;
  *)
    echo "Usage: $0 backup [--output-dir PATH] | restore ARCHIVE DESTINATION" >&2
    exit 2
    ;;
esac
