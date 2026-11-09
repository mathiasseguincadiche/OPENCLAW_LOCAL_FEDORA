#!/usr/bin/env bash
# Rôle       : Précontrôle de l'hôte avant installation (verdict PRECHECK=READY_TO_INSTALL ou BLOCKED).
# Usage      : 19_preinstall_check.sh   (aucun argument)
# Effets     : lecture seule (`preinstall_host.py`).
# Prérequis  : python3.
# Appelé par : ./menu.sh --action precheck ; ./menu.sh --action install --apply
set -Eeuo pipefail
REPO_ROOT="$(cd -- "$(dirname -- "$0")/../.." && pwd -P)"
[[ $# -eq 0 ]] || { echo "Usage: precheck (lecture seule, sans --apply)" >&2; exit 2; }
command -v python3 >/dev/null 2>&1 || { echo "PRECHECK=BLOCKED python3 absent" >&2; exit 2; }
exec python3 "$REPO_ROOT/scripts/validation/preinstall_host.py"
