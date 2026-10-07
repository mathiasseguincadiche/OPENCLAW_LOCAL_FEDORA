#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
LINUX="$REPO_ROOT/scripts/linux"
# shellcheck source=scripts/linux/lib/runtime.sh
source "$LINUX/lib/runtime.sh"

APPLY=0
[[ "${1:-}" == "--apply" ]] && APPLY=1
RUNTIME_ROOT="$(claw_runtime_root)"

cat <<EOF
REPAIR_PLAN runtime=$RUNTIME_ROOT
  1. create backup
  2. validate repository/lifecycle contracts
  3. run OpenClaw doctor
  4. redeploy managed agent workspaces
  5. re-render/apply the OpenClaw configuration
  6. restart gateway preserving managed definition
  7. run health
EOF

if ((APPLY == 0)); then
  echo "REPAIR_DRY_RUN=PASS"
  exit 0
fi

"$LINUX/08_backup_restore.sh" backup
PYTHON="$(claw_python)"
if "$PYTHON" -c 'import clawfedora' >/dev/null 2>&1; then
  "$PYTHON" -m clawfedora.cli --root "$REPO_ROOT" validate
  "$PYTHON" -m clawfedora.ops_cli --root "$REPO_ROOT" validate-lifecycle
else
  PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON" -m clawfedora.cli --root "$REPO_ROOT" validate
  PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON" -m clawfedora.ops_cli --root "$REPO_ROOT" validate-lifecycle
fi

command -v openclaw >/dev/null 2>&1 || { echo "REPAIR_RESULT=FAIL openclaw absent" >&2; exit 2; }
unset OPENCLAW_CONFIG_PATH
OPENCLAW_STATE_DIR="$(claw_openclaw_state)"
export OPENCLAW_STATE_DIR
export OLLAMA_API_KEY="ollama-local"
openclaw doctor --non-interactive
"$LINUX/02_deploy_agents.sh"
"$LINUX/03_configure_openclaw.sh" --apply
openclaw gateway restart --preserve-definition
"$LINUX/07_health.sh"

echo "REPAIR_RESULT=PASS"
