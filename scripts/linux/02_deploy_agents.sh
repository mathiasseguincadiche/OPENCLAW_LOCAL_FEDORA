#!/usr/bin/env bash
# Rôle       : Déployer les consignes des sept rôles dans l'espace d'exécution.
# Usage      : 02_deploy_agents.sh   (aucune option, pas de mode simulation)
# Effets     : écrit les espaces de travail des agents sous le runtime (`clawfedora agents deploy`).
# Prérequis  : /data monté (claw_require_storage).
# Appelé par : ./menu.sh --action agents ; 09_repair.sh
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=scripts/linux/lib/runtime.sh
source "$SCRIPT_DIR/lib/runtime.sh"

REPO_ROOT="$(claw_repo_root)"
RUNTIME_ROOT="$(claw_runtime_root)"
claw_require_storage "$RUNTIME_ROOT"
PYTHON="$(claw_python)"

"$PYTHON" -m clawfedora.cli --root "$REPO_ROOT" agents deploy --runtime-root "$RUNTIME_ROOT"
