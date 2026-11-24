#!/usr/bin/env bash
# Rôle : comparer les variantes GPU Ollama sans changer les contrats des agents.
# Usage : bash scripts/linux/24_gpu_profiles.sh status|reference|flash|q8 [--apply]
# Effets : dry-run par défaut ; changement explicite, verrou exclusif, retour arrière.
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=scripts/linux/lib/runtime.sh
source "$SCRIPT_DIR/lib/runtime.sh"
PROFILE="${1:-status}"
shift || true
case "$PROFILE" in
  status|reference|flash|q8) ;;
  *) echo "ERREUR: profil GPU attendu status|reference|flash|q8" >&2; exit 2 ;;
esac
APPLY=0
if [[ "${1:-}" == "--apply" ]]; then APPLY=1; shift; fi
(($# == 0)) || { echo "ERREUR: argument GPU inconnu" >&2; exit 2; }
PYTHON="$(claw_python)"
REPO_ROOT="$(claw_repo_root)"
profile_tool() {
  PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
    "$PYTHON" -m clawfedora.gpu_profiles "$@"
}
if [[ "$PROFILE" == "status" ]]; then
  systemctl show ollama.service --property=Environment --value | profile_tool status
  exit 0
fi
printf 'GPU_PROFILE_PLAN=%s context=32768 keep_alive=3m one_model=1 experimental=true\n' "$PROFILE"
((APPLY == 1)) || { echo "DRY_RUN=PASS"; exit 0; }

# No change while a project, a discussion or another maintenance operation is active.
((EUID != 0)) || { echo "ERREUR: utiliser le compte Fedora, pas root" >&2; exit 2; }
RUNTIME_ROOT="$(claw_runtime_root)"
claw_lock_worker
[[ ! -e "$RUNTIME_ROOT/state/gaming-mode" ]] || {
  echo "ERREUR: quitter le mode jeux avant un essai GPU" >&2; exit 2;
}
systemctl is-active --quiet ollama.service || {
  echo "ERREUR: Ollama doit être actif avant la modification" >&2; exit 2;
}
MANAGED="/etc/systemd/system/ollama.service.d/openclaw-daily.conf"
if ! sudo test -f "$MANAGED" || sudo test -L "$MANAGED"; then
  echo "ERREUR: complément Ollama géré absent ou lié" >&2; exit 2
fi
umask 077
TMP="$(mktemp -d)"
CHANGED=0
STAGED=""
# Atomically replace only the existing, managed daily drop-in.
replace_config() {
  STAGED="$(sudo mktemp "${MANAGED}.tmp.XXXXXXXX")" || return 2
  sudo install -o root -g root -m 0644 -- "$1" "$STAGED" || return 2
  sudo mv -fT -- "$STAGED" "$MANAGED" || return 2
  STAGED=""
  sudo restorecon -- "$MANAGED" || return 2
}
cleanup() {
  local rc=$?
  trap - EXIT INT TERM
  if ((CHANGED == 1 && rc != 0)); then
    echo "GPU_PROFILE_ROLLBACK=ATTEMPT" >&2
    if [[ -n "$STAGED" ]]; then
      sudo rm -f -- "$STAGED" || true
      STAGED=""
    fi
    if replace_config "$TMP/before.conf" && sudo systemctl daemon-reload &&
        sudo systemctl restart ollama.service &&
        systemctl is-active --quiet ollama.service; then
      echo "GPU_PROFILE_ROLLBACK=PASS" >&2
    else
      echo "GPU_PROFILE_ROLLBACK=FAIL; sauvegarde privée: $TMP/before.conf" >&2
      [[ -z "$STAGED" ]] || sudo rm -f -- "$STAGED"
      exit 2
    fi
  fi
  [[ -z "$STAGED" ]] || sudo rm -f -- "$STAGED"
  rm -rf -- "$TMP"
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
# Redirect as the operator, so the private backup belongs to the operator.
# shellcheck disable=SC2024
sudo cat -- "$MANAGED" > "$TMP/before.conf"
profile_tool patch "$PROFILE" < "$TMP/before.conf" > "$TMP/after.conf"
CHANGED=1
replace_config "$TMP/after.conf"
sudo systemctl daemon-reload
sudo systemctl restart ollama.service
systemctl is-active --quiet ollama.service
systemctl show ollama.service --property=Environment --value | profile_tool check "$PROFILE"
CHANGED=0
echo "GPU_PROFILE_RESULT=CONFIGURED_NOT_QUALIFIED"
