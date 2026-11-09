#!/usr/bin/env bash
# Rôle       : Rapport détaillé de l'état des services de l'atelier.
# Usage      : 07_health.sh   (aucune option)
# Effets     : contrôle seulement (`clawfedora-ops health`), aucune option de modification.
# Prérequis  : /data monté (claw_require_storage).
# Appelé par : ./menu.sh --action health ; 09_repair.sh
set -Eeuo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
# shellcheck source=scripts/linux/lib/runtime.sh
source "$REPO_ROOT/scripts/linux/lib/runtime.sh"
PYTHON="$(claw_python)"
RUNTIME_ROOT="$(claw_runtime_root)"
claw_require_storage "$RUNTIME_ROOT"

if "$PYTHON" -c 'import clawfedora' >/dev/null 2>&1; then
  exec "$PYTHON" -m clawfedora.ops_cli --root "$REPO_ROOT" --runtime-root "$RUNTIME_ROOT" health
fi
PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
  exec "$PYTHON" -m clawfedora.ops_cli --root "$REPO_ROOT" --runtime-root "$RUNTIME_ROOT" health
