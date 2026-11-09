#!/usr/bin/env bash
# Rôle       : Contrôler le système (Fedora, GNOME, matériel) ou le GPU (B580, pilote xe, Vulkan).
# Usage      : 04_check_hardware.sh system|gpu
# Effets     : contrôle sans modification du système ; écrit un rapport JSON horodaté dans le runtime.
# Prérequis  : /data monté (claw_require_storage).
# Appelé par : ./menu.sh --action check-system | check-gpu
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=scripts/linux/lib/runtime.sh
source "$SCRIPT_DIR/lib/runtime.sh"

CHECK="${1:-}"
case "$CHECK" in
  system|gpu) ;;
  *) echo "Usage: 04_check_hardware.sh system|gpu" >&2; exit 2 ;;
esac

REPO_ROOT="$(claw_repo_root)"
RUNTIME_ROOT="$(claw_runtime_root)"
claw_require_storage "$RUNTIME_ROOT"
PYTHON="$(claw_python)"

if "$PYTHON" -c 'import clawfedora' >/dev/null 2>&1; then
  exec "$PYTHON" -m clawfedora.cli --root "$REPO_ROOT" hardware \
    --check "$CHECK" --runtime-root "$RUNTIME_ROOT"
fi

PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
  exec "$PYTHON" -m clawfedora.cli --root "$REPO_ROOT" hardware \
    --check "$CHECK" --runtime-root "$RUNTIME_ROOT"
