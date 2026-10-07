#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=scripts/linux/lib/runtime.sh
source "$SCRIPT_DIR/lib/runtime.sh"
ACTION="${1:-status}"
shift || true
APPLY=0
case "${1:-}" in "") ;; --apply) APPLY=1 ;; *) echo "Argument inconnu" >&2; exit 2 ;; esac
(($# <= 1)) || { echo "Arguments supplémentaires" >&2; exit 2; }
case "$ACTION" in install|start|stop|seal|status) ;; *) echo "Usage: 13_openwebui.sh install|start|stop|seal|status [--apply]" >&2; exit 2 ;; esac
REPO_ROOT="$(claw_repo_root)"
RUNTIME_ROOT="$(claw_runtime_root)"
PYTHON="$(claw_python)"
UNIT_ROOT="$HOME/.config/systemd/user"
if [[ "$ACTION" == status ]]; then
  [[ ! -f "$RUNTIME_ROOT/state/webui/enabled" ]] || systemctl --user --no-pager status clawfedora-webui.service clawfedora-webui-bridge.service clawfedora-dashboard.service
  echo "Discussions: http://127.0.0.1:3000 ; Projets: http://127.0.0.1:18890"
  exit 0
fi
printf 'OPENWEBUI_PLAN action=%s release=v0.11.4 variant=slim cpu=2 memory=3g loopback=1\n' "$ACTION"
((APPLY == 1)) || { echo "DRY_RUN=PASS"; exit 0; }
((EUID != 0)) || { echo "ERREUR: lancer avec le compte Fedora habituel" >&2; exit 2; }
[[ -f "$RUNTIME_ROOT/.openclaw-fedora-runtime" ]] || { echo "ERREUR: runtime géré absent" >&2; exit 2; }
claw_lock_worker
if [[ "$ACTION" == install ]]; then
  # Fedora only; never install Podman or change host services on the review machine.
  # shellcheck disable=SC1091
  source /etc/os-release
  [[ "${ID:-}" == fedora && "${VERSION_ID:-}" == 44 ]] || { echo "ERREUR: Fedora 44 requis" >&2; exit 2; }
  [[ "$(getenforce)" == Enforcing ]] || { echo "ERREUR: SELinux Enforcing requis" >&2; exit 2; }
  command -v podman >/dev/null || sudo dnf install -y podman
  [[ "$(podman info --format '{{.Host.Security.Rootless}}')" == true ]] || { echo "ERREUR: Podman rootless requis" >&2; exit 2; }
  if podman container exists clawfedora-webui; then
    [[ "$(podman inspect --format '{{index .Config.Labels "io.clawfedora.managed"}}' clawfedora-webui)" == true ]] || { echo "ERREUR: nom de conteneur déjà utilisé" >&2; exit 2; }
  fi
  IMAGE="$($PYTHON -c 'from pathlib import Path; from clawfedora.core_config import root_contract; import sys; print(root_contract(Path(sys.argv[1]), "webui_policy.yaml")["image"])' "$REPO_ROOT")"
  podman pull "$IMAGE"
  "$PYTHON" -m clawfedora.webui_setup render --root "$REPO_ROOT" --runtime-root "$RUNTIME_ROOT" --unit-root "$UNIT_ROOT"
  mkdir -p "$HOME/.local/share/applications"
  cat > "$HOME/.local/share/applications/clawfedora-atelier.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=Atelier IA Fedora
Comment=Projets et discussions avec les sept spécialités locales
Exec=xdg-open http://127.0.0.1:18890
Icon=applications-development
Terminal=false
Categories=Development;
DESKTOP
  systemctl --user daemon-reload
  systemctl --user enable clawfedora-webui-bridge.service clawfedora-webui.service clawfedora-dashboard.service
  systemctl --user restart clawfedora-webui-bridge.service clawfedora-webui.service clawfedora-dashboard.service
elif [[ "$ACTION" == seal ]]; then
  # Stop SQLite writers before checking accounts and closing registration.
  systemctl --user stop clawfedora-webui.service
  "$PYTHON" -m clawfedora.webui_setup seal --root "$REPO_ROOT" --runtime-root "$RUNTIME_ROOT" --unit-root "$UNIT_ROOT"
  systemctl --user daemon-reload
  systemctl --user start clawfedora-webui.service
elif [[ "$ACTION" == stop ]]; then
  systemctl --user stop clawfedora-webui.service clawfedora-webui-bridge.service
else
  [[ -f "$RUNTIME_ROOT/state/webui/enabled" ]] || { echo "ERREUR: installer le module avant de le démarrer" >&2; exit 2; }
  systemctl --user start clawfedora-webui-bridge.service clawfedora-webui.service clawfedora-dashboard.service
fi
echo "OPENWEBUI_RESULT=PASS"
