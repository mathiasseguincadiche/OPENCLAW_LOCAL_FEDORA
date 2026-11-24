#!/usr/bin/env bash
# Atelier Projets autonome, sans conteneur WebUI ni LM Studio.
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd -P)"
# shellcheck source=scripts/linux/lib/runtime.sh
source "$SCRIPT_DIR/lib/runtime.sh"
(($# >= 1)) || { echo "Usage : 21_atelier.sh install|start|stop|status [--apply]" >&2; exit 2; }
ACTION="$1"
shift
APPLY=0
if (($# > 0)); then
  [[ "$1" == "--apply" && "$#" == 1 ]] || { echo "Argument invalide" >&2; exit 2; }
  APPLY=1
fi
case "$ACTION" in install|start|stop|status) ;; *) echo "Action inconnue" >&2; exit 2 ;; esac
UNIT="clawfedora-dashboard.service"
REPO_ROOT="$(claw_repo_root)"
RUNTIME_ROOT="$(claw_runtime_root)"
PYTHON="$(claw_python)"
if [[ "$ACTION" == status ]]; then
  if systemctl --user is-active --quiet "$UNIT"; then
    echo "ATELIER=ACTIVE url=http://127.0.0.1:18890"
  else
    echo "ATELIER=INACTIVE"
  fi
  exit 0
fi
printf 'ATELIER_PLAN action=%s standalone=1 port=18890\n' "$ACTION"
((APPLY == 1)) || { echo "DRY_RUN=PASS"; exit 0; }
((EUID != 0)) || { echo "Compte Fedora normal requis" >&2; exit 2; }
claw_lock_worker
if [[ "$ACTION" == stop ]]; then
  systemctl --user stop "$UNIT"
  echo "ATELIER_RESULT=PASS action=stop"
  exit 0
fi
claw_require_storage "$RUNTIME_ROOT"
[[ -f "$RUNTIME_ROOT/.openclaw-fedora-runtime" ]] || {
  echo "Runtime de l'atelier absent" >&2; exit 2;
}
if [[ "$ACTION" == install ]]; then
  # shellcheck disable=SC1091
  source /etc/os-release
  [[ "$ID" == fedora && "$VERSION_ID" == 45 ]] || {
    echo "Fedora 45 requis" >&2; exit 2;
  }
  [[ "$(getenforce)" == Enforcing ]] || {
    echo "SELinux Enforcing requis" >&2; exit 2;
  }
  PYTHONPATH="$REPO_ROOT/src" "$PYTHON" \
    -m clawfedora.atelier_setup --root "$REPO_ROOT" \
    --runtime-root "$RUNTIME_ROOT" \
    --unit-root "$HOME/.config/systemd/user"
  mkdir -p "$HOME/.local/share/applications"
  cat > "$HOME/.local/share/applications/clawfedora-atelier.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=Atelier IA Fedora
Comment=Discussions, agents, projets et outils locaux
Exec=xdg-open http://127.0.0.1:18890
Icon=applications-development
Terminal=false
Categories=Development;
DESKTOP
  systemctl --user daemon-reload
  systemctl --user enable --now "$UNIT"
else
  [[ -f "$HOME/.config/systemd/user/$UNIT" ]] || {
    echo "Installer l'Atelier avant démarrage" >&2; exit 2;
  }
  systemctl --user start "$UNIT"
fi
systemctl --user is-active --quiet "$UNIT" || {
  echo "Atelier inactif après demande" >&2; exit 1;
}
echo "ATELIER_RESULT=PASS url=http://127.0.0.1:18890"
