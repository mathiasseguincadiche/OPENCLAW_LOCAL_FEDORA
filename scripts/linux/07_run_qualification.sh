#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=scripts/linux/lib/runtime.sh
source "$SCRIPT_DIR/lib/runtime.sh"

DRY_RUN=0
ENDPOINT="http://127.0.0.1:11434"

while (($#)); do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --endpoint)
      shift
      [[ $# -gt 0 ]] || { echo "ERREUR: --endpoint exige une valeur" >&2; exit 2; }
      ENDPOINT="$1"
      ;;
    -h|--help)
      echo "Usage: 07_run_qualification.sh [--dry-run] [--endpoint LOOPBACK_URL]"
      exit 0
      ;;
    *) echo "ERREUR: argument inconnu: $1" >&2; exit 2 ;;
  esac
  shift
done

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
  run_cli qualification --runtime-root "$RUNTIME_ROOT" --endpoint "$ENDPOINT" --dry-run
  exit $?
fi

command -v systemd-inhibit >/dev/null 2>&1 || {
  echo "ERREUR: systemd-inhibit requis pour garantir HARD-40M sans suspension." >&2
  exit 127
}

export OPENCLAW_LOCAL_CLOUD_ENABLED=false
export OPENCLAW_LOCAL_FEDORA_ROOT="$RUNTIME_ROOT"

printf '%s\n' 'QUALIFICATION_PROTECTION=sleep-blocked-via-systemd-inhibit'
printf '%s\n' 'QUALIFICATION_CLOUD=false'
printf 'QUALIFICATION_ENDPOINT=%s\n' "$ENDPOINT"

if "$PYTHON" -c 'import clawfedora' >/dev/null 2>&1; then
  exec systemd-inhibit --what=sleep --mode=block \
    --why="OPENCLAW_LOCAL_FEDORA HARD-40M qualification" \
    env OPENCLAW_LOCAL_FEDORA_SLEEP_INHIBITED=1 \
    "$PYTHON" -m clawfedora.cli --root "$REPO_ROOT" qualification \
    --runtime-root "$RUNTIME_ROOT" --endpoint "$ENDPOINT"
fi

exec systemd-inhibit --what=sleep --mode=block \
  --why="OPENCLAW_LOCAL_FEDORA HARD-40M qualification" \
  env OPENCLAW_LOCAL_FEDORA_SLEEP_INHIBITED=1 \
  PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
  "$PYTHON" -m clawfedora.cli --root "$REPO_ROOT" qualification \
  --runtime-root "$RUNTIME_ROOT" --endpoint "$ENDPOINT"
