#!/usr/bin/env bash
# Rôle       : Sauvegarder l'état, les projets et les espaces de travail, ou restaurer une archive.
# Usage      : 08_backup_restore.sh backup [--output-dir CHEMIN] | restore ARCHIVE DESTINATION
# Effets     : backup crée une archive NON chiffrée et est refusé pendant une génération (verrou worker). restore extrait vers DESTINATION.
# Prérequis  : /data monté (claw_require_storage).
# Appelé par : ./menu.sh --action backup ; 09_repair.sh ; 12_upgrade.sh
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

claw_require_storage "$RUNTIME_ROOT"
case "${1:-}" in
  backup)
    shift
    # One consistent instant: refused while a chat, task or audit runs (A04). Reuses the
    # descriptor of a parent that already holds the lock (12_upgrade, 09_repair).
    claw_lock_worker
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
