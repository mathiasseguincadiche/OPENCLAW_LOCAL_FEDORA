#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=scripts/linux/lib/runtime.sh
source "$SCRIPT_DIR/lib/runtime.sh"

usage() {
  cat <<'EOT'
Usage: 14_cloud.sh ACTION [--value N] [--apply]

  status      État du cloud, de la clé (empreinte seulement) et du budget du mois
  set-key     Enregistre la clé OpenRouter (saisie masquée, jamais en argument)
  enable      Lance les contrôles; avec --apply, active le cloud et la passerelle
              --value = limite posée sur la clé chez OpenRouter, en dollars
  disable     Désactive le cloud et arrête la passerelle
  reconcile   Enregistre ce qu'OpenRouter a réellement facturé ce mois-ci
              --value = montant en euros (le plafond en tient compte)

Sans --apply, enable n'active rien et ne touche à aucun service.
EOT
}

ACTION="${1:-status}"
shift || true
APPLY=0
VALUE=""
while (($#)); do
  case "$1" in
    --apply) APPLY=1 ;;
    --value)
      shift
      [[ $# -gt 0 ]] || { echo "ERREUR: --value exige une valeur" >&2; exit 2; }
      VALUE="$1"
      ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERREUR: argument inconnu: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done
case "$ACTION" in status|set-key|enable|disable|reconcile) ;; *) usage >&2; exit 2 ;; esac
if [[ -n "$VALUE" && ! "$VALUE" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  echo "ERREUR: --value doit être un nombre positif" >&2
  exit 2
fi

REPO_ROOT="$(claw_repo_root)"
RUNTIME_ROOT="$(claw_runtime_root)"
PYTHON="$(claw_python)"
UNIT_ROOT="$HOME/.config/systemd/user"
cloud() { "$PYTHON" -m clawfedora.cloud_cli --root "$REPO_ROOT" --runtime-root "$RUNTIME_ROOT" "$@"; }
require_runtime() {
  ((EUID != 0)) || { echo "ERREUR: lancer avec le compte Fedora habituel" >&2; exit 2; }
  [[ -f "$RUNTIME_ROOT/.openclaw-fedora-runtime" ]] || { echo "ERREUR: runtime géré absent" >&2; exit 2; }
}

case "$ACTION" in
  status) cloud status ;;
  set-key)
    require_runtime
    echo "Collez la clé OpenRouter (rien ne s'affiche), puis Entrée."
    read -r -s -p "Clé: " PROVIDER_KEY
    echo
    printf '%s\n' "$PROVIDER_KEY" | cloud set-key
    unset PROVIDER_KEY
    ;;
  reconcile)
    [[ -n "$VALUE" ]] || { echo "ERREUR: --value MONTANT_EUROS exigé" >&2; exit 2; }
    cloud reconcile --eur "$VALUE" --note "relevé OpenRouter saisi à la main"
    ;;
  enable)
    [[ -n "$VALUE" ]] || { echo "ERREUR: --value LIMITE_DE_LA_CLE_EN_DOLLARS exigé" >&2; exit 2; }
    args=(enable --key-limit-usd "$VALUE")
    if [[ "${CLAWFEDORA_CONFIRM_PREPAID:-}" != 1 ]]; then
      read -r -p "Crédits OpenRouter prépayés, sans rechargement automatique ? [oui/non] " ANSWER
      [[ "$ANSWER" == oui ]] || { echo "Cloud non activé: confirmer le prépayé sans rechargement automatique." >&2; exit 2; }
    fi
    args+=(--confirm-prepaid --verify-online)
    if ((APPLY == 0)); then
      cloud "${args[@]}"
      exit $?
    fi
    require_runtime
    claw_lock_worker
    cloud "${args[@]}" --apply
    cloud render-unit --unit-root "$UNIT_ROOT"
    systemctl --user daemon-reload
    systemctl --user enable clawfedora-cloud-gateway.service
    systemctl --user restart clawfedora-cloud-gateway.service
    "$SCRIPT_DIR/03_configure_openclaw.sh" --apply
    systemctl --user restart clawfedora-webui-bridge.service 2>/dev/null || true
    cloud status
    ;;
  disable)
    if ((APPLY == 0)); then
      echo "DRY_RUN=PASS le cloud serait désactivé et la passerelle arrêtée (--apply)"
      exit 0
    fi
    require_runtime
    claw_lock_worker
    cloud disable
    systemctl --user disable --now clawfedora-cloud-gateway.service 2>/dev/null || true
    "$SCRIPT_DIR/03_configure_openclaw.sh" --apply
    systemctl --user restart clawfedora-webui-bridge.service 2>/dev/null || true
    cloud status
    ;;
esac
