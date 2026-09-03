#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
# shellcheck source=scripts/linux/lib/runtime.sh
source "$REPO_ROOT/scripts/linux/lib/runtime.sh"

APPLY=0
PURGE=0
for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=1 ;;
    --purge-data) PURGE=1 ;;
    -h|--help)
      echo "Usage: $0 [--apply] [--purge-data]"
      exit 0
      ;;
    *) echo "ERREUR: argument inconnu: $arg" >&2; exit 2 ;;
  esac
done

RUNTIME_ROOT="$(claw_runtime_root)"
cat <<EOF
UNINSTALL_PLAN runtime=$RUNTIME_ROOT
  gateway service: stop + uninstall
  managed workspaces: remove
  managed venv: remove
  projects/models/proofs: preserve by default
  purge-data: $PURGE
EOF

if ((APPLY == 0)); then
  echo "UNINSTALL_DRY_RUN=PASS"
  exit 0
fi

if command -v openclaw >/dev/null 2>&1; then
  openclaw gateway stop || true
  openclaw gateway uninstall || true
fi

PYTHON="$(claw_python)"
ARGS=(--root "$REPO_ROOT" --runtime-root "$RUNTIME_ROOT" cleanup --apply)
((PURGE == 1)) && ARGS+=(--purge-data)
if "$PYTHON" -c 'import clawfedora' >/dev/null 2>&1; then
  "$PYTHON" -m clawfedora.ops_cli "${ARGS[@]}"
else
  PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
    "$PYTHON" -m clawfedora.ops_cli "${ARGS[@]}"
fi

echo "UNINSTALL_RESULT=PASS purge_data=$PURGE"
