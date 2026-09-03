#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=scripts/linux/lib/runtime.sh
source "$SCRIPT_DIR/lib/runtime.sh"

BACKEND="ollama-vulkan"
DRY_RUN=0

while (($#)); do
  case "$1" in
    --backend)
      shift
      [[ $# -gt 0 ]] || { echo "ERREUR: --backend exige une valeur" >&2; exit 2; }
      BACKEND="$1"
      ;;
    --dry-run) DRY_RUN=1 ;;
    -h|--help)
      echo "Usage: 06_openclaw_e2e.sh [--backend BACKEND] [--dry-run]"
      exit 0
      ;;
    *) echo "ERREUR: argument inconnu: $1" >&2; exit 2 ;;
  esac
  shift
done

case "$BACKEND" in
  ollama-vulkan|llama-cpp-vulkan|llama-cpp-sycl) ;;
  *) echo "ERREUR: backend non supporté: $BACKEND" >&2; exit 2 ;;
esac

REPO_ROOT="$(claw_repo_root)"
RUNTIME_ROOT="$(claw_runtime_root)"
PYTHON="$(claw_python)"

run_cli() {
  if "$PYTHON" -c 'import clawfedora' >/dev/null 2>&1; then
    "$PYTHON" -m clawfedora.cli --root "$REPO_ROOT" "$@"
  else
    PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
      "$PYTHON" -m clawfedora.cli --root "$REPO_ROOT" "$@"
  fi
}

if ((DRY_RUN == 1)); then
  run_cli e2e --backend "$BACKEND" --runtime-root "$RUNTIME_ROOT" --dry-run
  exit $?
fi

command -v systemd-inhibit >/dev/null 2>&1 || {
  echo "ERREUR: systemd-inhibit requis pour protéger le E2E contre la veille." >&2
  exit 127
}

export OPENCLAW_LOCAL_CLOUD_ENABLED=false
export OPENCLAW_LOCAL_FEDORA_ROOT="$RUNTIME_ROOT"

if "$PYTHON" -c 'import clawfedora' >/dev/null 2>&1; then
  exec systemd-inhibit --what=sleep --mode=block \
    --why="OPENCLAW_LOCAL_FEDORA L4 E2E" \
    "$PYTHON" -m clawfedora.cli --root "$REPO_ROOT" e2e \
    --backend "$BACKEND" --runtime-root "$RUNTIME_ROOT"
fi

exec systemd-inhibit --what=sleep --mode=block \
  --why="OPENCLAW_LOCAL_FEDORA L4 E2E" \
  env PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
  "$PYTHON" -m clawfedora.cli --root "$REPO_ROOT" e2e \
  --backend "$BACKEND" --runtime-root "$RUNTIME_ROOT"
