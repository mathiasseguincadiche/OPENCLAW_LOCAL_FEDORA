#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=scripts/linux/lib/runtime.sh
source "$SCRIPT_DIR/lib/runtime.sh"
APPLY=0
case "${1:-}" in
  "") ;;
  --apply) APPLY=1 ;;
  *) echo "Usage: 12_upgrade.sh [--apply]" >&2; exit 2 ;;
esac
(( $# <= 1 )) || { echo "ERREUR: arguments supplémentaires" >&2; exit 2; }
RUNTIME_ROOT="$(claw_runtime_root)"
printf 'UPGRADE_PLAN runtime=%s openclaw=%s ollama=%s\n' "$RUNTIME_ROOT" "$(claw_pin openclaw version)" "$(claw_pin ollama version)"
echo "Arrêt des services, sauvegarde cohérente, convergence des versions, migration et health --probe."
((APPLY == 1)) || { echo "UPGRADE_DRY_RUN=PASS"; exit 0; }
((EUID != 0)) || { echo "ERREUR: lancer avec le compte Fedora habituel" >&2; exit 2; }
[[ -f "$RUNTIME_ROOT/.openclaw-fedora-runtime" ]] || { echo "ERREUR: installation gérée absente" >&2; exit 2; }
[[ ! -e "$RUNTIME_ROOT/state/gaming-mode" ]] || { echo "ERREUR: reprendre le profil quotidien avant la migration" >&2; exit 2; }
mkdir -p "$RUNTIME_ROOT/state"
exec 9>"$RUNTIME_ROOT/state/worker.lock"
flock -n 9 || { echo "ERREUR: worker actif; demander une pause et attendre la fin de tâche" >&2; exit 2; }
finish() {
  local result=$?
  if ((result != 0)); then
    systemctl --user stop clawfedora-webui.service clawfedora-webui-bridge.service clawfedora-speech.service clawfedora-dashboard.service openclaw-gateway.service 2>/dev/null || true
    sudo systemctl stop ollama.service 2>/dev/null || true
    printf 'UPGRADE_RESULT=FAIL services arrêtés; sauvegardes: %s/backups; suivre docs/fiches/09-entretenir.md\n' "$RUNTIME_ROOT" >&2
  fi
}
trap finish EXIT
systemctl --user stop clawfedora-webui.service clawfedora-webui-bridge.service clawfedora-speech.service clawfedora-dashboard.service 2>/dev/null || true
systemctl --user stop openclaw-gateway.service
sudo systemctl stop ollama.service
"$SCRIPT_DIR/08_backup_restore.sh" backup
"$SCRIPT_DIR/06_install.sh" --apply
if [[ -f "$RUNTIME_ROOT/state/webui/enabled" ]]; then
  # Restore all managed units, dependencies and the pinned image after the core migration.
  "$SCRIPT_DIR/13_openwebui.sh" install --apply
  if [[ -f "$RUNTIME_ROOT/state/webui/sealed" ]]; then
    # Reinstall the global file filter into the migrated WebUI database.
    "$SCRIPT_DIR/13_openwebui.sh" seal --apply
  fi
fi
echo "UPGRADE_RESULT=PASS"
