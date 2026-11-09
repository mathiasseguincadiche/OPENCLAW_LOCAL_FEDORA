#!/usr/bin/env bash
# Rôle       : Désinstaller l'atelier ; avec --purge-data, supprimer aussi les données.
# Usage      : 10_uninstall.sh [--apply] [--purge-data]
# Effets     : sans --apply : plan seulement. Avec --apply : arrête les services (arrêt vérifié avant toute suppression). --purge-data supprime aussi les données, dont les modèles Ollama (sudo rm -rf).
# Prérequis  : lancer avec le compte Fedora habituel (sudo sert à arrêter Ollama et à supprimer ses modèles) ; copie externe recommandée avant --purge-data.
# Appelé par : ./menu.sh --action uninstall
set -Eeuo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
# shellcheck source=scripts/linux/lib/runtime.sh
source "$REPO_ROOT/scripts/linux/lib/runtime.sh"

APPLY=0
PURGE=0
for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=1 ;;
    --purge-data) PURGE=1 ;;
    -h|--help)
      echo "Usage: $0 [--apply] [--purge-data]"
      exit 0
      ;;
    *) echo "ERREUR: argument inconnu: $arg" >&2; exit 2 ;;
  esac
done

RUNTIME_ROOT="$(claw_runtime_root)"
cat <<EOF
UNINSTALL_PLAN runtime=$RUNTIME_ROOT
  services WebUI/bridge/voix/tableau: stop verified
  gateway service (managed CLI + state): stop verified, then uninstall
  managed workspaces: remove
  managed venv: remove
  projects/models/proofs: preserve by default
  purge: stops Ollama, removes models/ollama with sudo, then projects/proofs/state/models
  purge-data: $PURGE
EOF

if ((APPLY == 0)); then
  echo "UNINSTALL_DRY_RUN=PASS"
  exit 0
fi

claw_lock_worker
# Services built on top of the Gateway stop first. A unit that is installed must really stop:
# its failure aborts before anything is removed. Units never installed are simply skipped.
for unit in clawfedora-webui.service clawfedora-webui-bridge.service clawfedora-speech.service clawfedora-dashboard.service; do
  systemctl --user cat "$unit" >/dev/null 2>&1 || continue
  systemctl --user disable --now "$unit" || {
    echo "UNINSTALL_RESULT=FAIL arrêt de $unit refusé; rien n'a été supprimé" >&2
    exit 2
  }
  if systemctl --user is-active --quiet "$unit"; then
    echo "UNINSTALL_RESULT=FAIL $unit encore actif; rien n'a été supprimé" >&2
    exit 2
  fi
done
# Managed CLI + managed state, stop proven before the first deletion (A02).
claw_uninstall_gateway "$(claw_openclaw_state)" || {
  echo "UNINSTALL_RESULT=FAIL Gateway OpenClaw non arrêté de façon vérifiée; données intactes" >&2
  exit 2
}
rm -f "$HOME/.local/share/applications/clawfedora-atelier.desktop"

PYTHON="$(claw_python)"
ops() {
  if "$PYTHON" -c 'import clawfedora' >/dev/null 2>&1; then
    "$PYTHON" -m clawfedora.ops_cli --root "$REPO_ROOT" --runtime-root "$RUNTIME_ROOT" "$@"
  else
    PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
      "$PYTHON" -m clawfedora.ops_cli --root "$REPO_ROOT" --runtime-root "$RUNTIME_ROOT" "$@"
  fi
}

if ((PURGE == 1)); then
  # 1. Every permission checked first, without removing anything (A07). models/ollama
  #    belongs to the ollama service account and is handled by the bounded step 2.
  ops cleanup --check --purge-data --models-by-root
  # 2. Stop Ollama, prove it, then remove exactly this managed directory with sudo.
  MODELS="$RUNTIME_ROOT/models/ollama"
  if systemctl cat ollama.service >/dev/null 2>&1; then
    sudo systemctl stop ollama.service
    if systemctl is-active --quiet ollama.service; then
      echo "UNINSTALL_RESULT=FAIL Ollama encore actif; modèles et données intacts" >&2
      exit 2
    fi
  fi
  if [[ -e "$MODELS" || -L "$MODELS" ]]; then
    [[ -f "$RUNTIME_ROOT/.openclaw-fedora-runtime" && ! -L "$RUNTIME_ROOT/models" && ! -L "$MODELS" && -d "$MODELS" ]] || {
      echo "UNINSTALL_RESULT=FAIL dossier des modèles inattendu: $MODELS; rien n'a été supprimé" >&2
      exit 2
    }
    sudo rm -rf --one-file-system -- "$MODELS"
  fi
  # 3. The user-level purge, checked again by itself before its first removal.
  ops cleanup --apply --purge-data
else
  ops cleanup --apply
fi

echo "UNINSTALL_RESULT=PASS purge_data=$PURGE"
