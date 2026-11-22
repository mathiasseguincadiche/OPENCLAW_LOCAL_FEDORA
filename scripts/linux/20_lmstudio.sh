#!/usr/bin/env bash
# Rôle       : Pont local indépendant pour LM Studio (sans suppression d'Open WebUI).
# Usage      : menu.sh --action lmstudio-install|lmstudio-start|lmstudio-stop|lmstudio-status [--apply]
# Effets     : install crée uniquement un jeton privé et une unité systemd user.
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=scripts/linux/lib/runtime.sh
source "$SCRIPT_DIR/lib/runtime.sh"
ACTION="${1:-status}"
shift || true
APPLY=0
case "${1:-}" in
  "") ;;
  --apply) APPLY=1 ;;
  *) echo "Argument inconnu" >&2; exit 2 ;;
esac
(($# <= 1)) || { echo "Arguments supplémentaires" >&2; exit 2; }
case "$ACTION" in install|start|stop|status) ;; *) echo "Action LM Studio inconnue" >&2; exit 2 ;; esac

REPO_ROOT="$(claw_repo_root)"
RUNTIME_ROOT="$(claw_runtime_root)"
PYTHON="$(claw_python)"
UNIT="clawfedora-lmstudio-bridge.service"
if [[ "$ACTION" == status ]]; then
  if systemctl --user is-active --quiet "$UNIT"; then
    echo "LMSTUDIO_BRIDGE=ACTIVE port=18894 localhost=1"
  else
    echo "LMSTUDIO_BRIDGE=INACTIVE"
  fi
  exit 0
fi
printf 'LMSTUDIO_PLAN action=%s port=18894 WebUI_unmodified=1 token_private=1\n' "$ACTION"
((APPLY == 1)) || { echo "DRY_RUN=PASS"; exit 0; }
((EUID != 0)) || { echo "Compte Fedora habituel requis, pas root" >&2; exit 2; }
if [[ "$ACTION" == stop ]]; then
  systemctl --user stop "$UNIT"
  echo "LMSTUDIO_RESULT=PASS action=stop"
  exit 0
fi
claw_require_storage "$RUNTIME_ROOT"
[[ -f "$RUNTIME_ROOT/.openclaw-fedora-runtime" ]] || {
  echo "Runtime ClawFedora manquant" >&2; exit 2;
}
if [[ "$ACTION" == install ]]; then
  # Fedora validation without making claims about LM Studio GPU support.
  # shellcheck disable=SC1091
  source /etc/os-release
  [[ "${ID:-}" == fedora && "${VERSION_ID:-}" == 45 ]] || {
    echo "Fedora 45 requis" >&2; exit 2;
  }
  [[ "$(getenforce)" == Enforcing ]] || {
    echo "SELinux Enforcing requis" >&2; exit 2;
  }
  PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON" \
    -m clawfedora.lmstudio_setup --root "$REPO_ROOT" \
    --runtime-root "$RUNTIME_ROOT" \
    --unit-root "$HOME/.config/systemd/user"
  systemctl --user daemon-reload
  systemctl --user enable --now "$UNIT"
else
  [[ -f "$HOME/.config/systemd/user/$UNIT" ]] || {
    echo "Pont LM Studio non installé" >&2; exit 2;
  }
  systemctl --user start "$UNIT"
fi
systemctl --user is-active --quiet "$UNIT" || {
  echo "Le pont LM Studio ne fonctionne pas" >&2; exit 1;
}
echo "LMSTUDIO_RESULT=PASS port=18894"
