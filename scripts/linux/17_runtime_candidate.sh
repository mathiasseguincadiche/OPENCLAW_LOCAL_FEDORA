#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd -P)"
# shellcheck source=scripts/linux/lib/runtime.sh
source "$SCRIPT_DIR/lib/runtime.sh"

BACKEND="llama-cpp-vulkan"
ACTION="status"
APPLY=0

usage() {
  cat <<'EOF'
Usage: 17_runtime_candidate.sh --backend llama-cpp-vulkan|llama-cpp-sycl \
       --action install|start|stop|restart|status [--apply]

Les actions mutantes sont dry-run sans --apply. `install` génère un preset router llama.cpp
et une unité systemd utilisateur loopback. Aucun modèle n'est téléchargé.
EOF
}

while (($#)); do
  case "$1" in
    --backend)
      shift
      [[ $# -gt 0 ]] || { echo "ERREUR: --backend exige une valeur" >&2; exit 2; }
      BACKEND="$1"
      ;;
    --action)
      shift
      [[ $# -gt 0 ]] || { echo "ERREUR: --action exige une valeur" >&2; exit 2; }
      ACTION="$1"
      ;;
    --apply) APPLY=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERREUR: argument inconnu: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

case "$BACKEND" in
  llama-cpp-vulkan) UNIT="openclaw-llama-vulkan.service"; PORT=8081 ;;
  llama-cpp-sycl) UNIT="openclaw-llama-sycl.service"; PORT=8080 ;;
  *) echo "ERREUR: backend candidat invalide: $BACKEND" >&2; exit 2 ;;
esac
case "$ACTION" in install|start|stop|restart|status) ;; *) echo "ERREUR: action invalide: $ACTION" >&2; exit 2 ;; esac

if [[ "$ACTION" != "status" && "$APPLY" -eq 0 ]]; then
  echo "L6_RUNTIME_PLAN backend=$BACKEND action=$ACTION unit=$UNIT endpoint=http://127.0.0.1:$PORT/v1"
  echo "L6_RUNTIME_DRY_RUN=PASS"
  exit 0
fi

if ! systemctl --user show-environment >/dev/null 2>&1; then
  echo "ERREUR: systemd utilisateur indisponible" >&2
  exit 2
fi

if [[ "$ACTION" == "install" ]]; then
  PYTHON="$(claw_python)"
  UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
  ARGS=(--root "$REPO_ROOT" --runtime-root "$(claw_runtime_root)" runtime-files --backend "$BACKEND" --unit-dir "$UNIT_DIR")
  if "$PYTHON" -c 'import clawfedora' >/dev/null 2>&1; then
    "$PYTHON" -m clawfedora.optimization_cli "${ARGS[@]}"
  else
    PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
      "$PYTHON" -m clawfedora.optimization_cli "${ARGS[@]}"
  fi
  systemctl --user daemon-reload
  systemctl --user enable "$UNIT"
  echo "L6_RUNTIME_INSTALL_RESULT=PASS backend=$BACKEND unit=$UNIT"
  exit 0
fi

if [[ "$ACTION" == "status" ]]; then
  systemctl --user status "$UNIT" --no-pager
  curl -fsS --max-time 5 "http://127.0.0.1:$PORT/v1/models" | jq -e . >/dev/null
  echo "L6_RUNTIME_STATUS_RESULT=PASS backend=$BACKEND"
  exit 0
fi

systemctl --user "$ACTION" "$UNIT"
if [[ "$ACTION" == "start" || "$ACTION" == "restart" ]]; then
  for _ in {1..30}; do
    if curl -fsS --max-time 2 "http://127.0.0.1:$PORT/v1/models" | jq -e . >/dev/null 2>&1; then
      echo "L6_RUNTIME_${ACTION^^}_RESULT=PASS backend=$BACKEND"
      exit 0
    fi
    sleep 1
  done
  echo "ERREUR: router $BACKEND non prêt sur 127.0.0.1:$PORT" >&2
  exit 2
fi

echo "L6_RUNTIME_${ACTION^^}_RESULT=PASS backend=$BACKEND"
