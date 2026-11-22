#!/usr/bin/env bash
# Retrait définitif du routage OpenRouter de l'atelier local.
# Aucun appel réseau et aucune activation cloud ne sont possibles ici.
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=scripts/linux/lib/runtime.sh
source "$SCRIPT_DIR/lib/runtime.sh"
ACTION="${1:-status}"
shift || true
APPLY=0
while (($#)); do
  case "$1" in
    --apply) APPLY=1 ;;
    -h|--help) echo "Usage: 14_cloud.sh status|retire [--apply]"; exit 0 ;;
    *) echo "ERREUR: argument inconnu: $1" >&2; exit 2 ;;
  esac
  shift
done
case "$ACTION" in
  status) echo "CLOUD_STATUS=RETIRED provider=ollama only" ;;
  retire)
    if (( APPLY == 0 )); then
      echo "LOCAL_RETIRE_PLAN=PASS arrêtera la passerelle cloud, effacera uniquement les clés/activation locales, reconfigurera OpenClaw (--apply)"
      exit 0
    fi
    (( EUID != 0 )) || { echo "ERREUR: compte utilisateur requis" >&2; exit 2; }
    ROOT="$(claw_runtime_root)"
    claw_require_storage "$ROOT"
    [[ -f "$ROOT/.openclaw-fedora-runtime" ]] || { echo "ERREUR: runtime non géré" >&2; exit 2; }
    claw_lock_worker
    systemctl --user disable --now clawfedora-cloud-gateway.service 2>/dev/null || true
    # Ne jamais suivre un lien symbolique ni effacer l'historique de facturation.
    for path in "$ROOT/state/cloud/upstream.key" "$ROOT/state/cloud/gateway.token" "$ROOT/state/cloud/activation.json"; do
      [[ ! -L "$path" ]] || { echo "ERREUR: lien symbolique interdit: $path" >&2; exit 2; }
      [[ ! -e "$path" || -f "$path" ]] || { echo "ERREUR: fichier irrégulier: $path" >&2; exit 2; }
      rm -f -- "$path"
    done
    "$SCRIPT_DIR/03_configure_openclaw.sh" --apply
    echo "LOCAL_RETIRE_RESULT=PASS aucun fournisseur cloud configuré; historique conservé"
    ;;
  *) echo "ERREUR: action inconnue; seulement status|retire" >&2; exit 2 ;;
esac
