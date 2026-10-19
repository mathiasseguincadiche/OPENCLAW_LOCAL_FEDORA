#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=scripts/linux/lib/runtime.sh
source "$SCRIPT_DIR/lib/runtime.sh"

ACTION="${1:-status}"
MODE="${2:-}"
case "$ACTION" in
  status|private|connected) ;;
  *) echo "Usage: 17_web_access.sh status|private|connected [--apply]" >&2; exit 2 ;;
esac
[[ -z "$MODE" || "$MODE" == --apply ]] || {
  echo "Usage: 17_web_access.sh status|private|connected [--apply]" >&2
  exit 2
}
[[ $# -le 2 ]] || { echo "Arguments supplémentaires refusés" >&2; exit 2; }
if [[ "$ACTION" == status && -n "$MODE" ]]; then
  echo "L'état Web n'accepte pas --apply" >&2
  exit 2
fi

REPO_ROOT="$(claw_repo_root)"
RUNTIME_ROOT="$(claw_runtime_root)"
PYTHON="$(claw_python)"
OPENCLAW_STATE="$(claw_openclaw_state)"

ops() {
  "$PYTHON" -m clawfedora.ops_cli --root "$REPO_ROOT" \
    --runtime-root "$RUNTIME_ROOT" web-access "$@"
}

if [[ "$ACTION" == status ]]; then
  ops status
  # The staged marker alone is not evidence of an applied native policy.
  echo "WEB_ACCESS_NOTE=status shows desired mode only; use private|connected --apply to verify it"
  exit 0
fi

echo "WEB_ACCESS_PLAN mode=$ACTION stop_gateway=true native_apply=true verify=true restart=true"
if [[ "$MODE" != --apply ]]; then
  echo "WEB_ACCESS_DRY_RUN=PASS"
  exit 0
fi

((EUID != 0)) || { echo "ERREUR: utilisateur Fedora non-root requis" >&2; exit 2; }
claw_require_storage "$RUNTIME_ROOT"
[[ -f "$RUNTIME_ROOT/.openclaw-fedora-runtime" ]] || {
  echo "WEB_ACCESS_RESULT=REFUSED: runtime géré absent" >&2
  exit 2
}
command -v systemctl >/dev/null || { echo "systemctl requis" >&2; exit 127; }
systemctl --user cat openclaw-gateway.service >/dev/null || {
  echo "WEB_ACCESS_RESULT=REFUSED: Gateway systemd non installé" >&2
  exit 2
}
claw_lock_worker

# Fail-closed: do not leave the old connected Gateway serving requests while
# a private marker is being staged but native configuration is still stale.
systemctl --user stop openclaw-gateway.service
echo "WEB_ACCESS_TRANSITION=gateway-stopped"
ops "$ACTION" --apply
export PATH="$HOME/.openclaw/bin:$HOME/.local/bin:$PATH"
"$SCRIPT_DIR/03_configure_openclaw.sh" --apply
"$PYTHON" "$REPO_ROOT/scripts/validation/verify_web_config.py" \
  --config "$OPENCLAW_STATE/openclaw.json" --mode "$ACTION"
systemctl --user restart openclaw-gateway.service
systemctl --user is-active --quiet openclaw-gateway.service || {
  echo "WEB_ACCESS_RESULT=REFUSED: Gateway pas actif après redémarrage" >&2
  exit 2
}
echo "WEB_ACCESS_RESULT=PASS mode=$ACTION gateway=active saved_policy=verified"
echo "WEB_ACCESS_NOTE=aucun test de non-sortie réseau n'a été exécuté; le mode privé n'est pas un pare-feu"
