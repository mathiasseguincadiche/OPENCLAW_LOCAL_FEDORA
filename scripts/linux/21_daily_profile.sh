#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=scripts/linux/lib/runtime.sh
source "$SCRIPT_DIR/lib/runtime.sh"
ACTION="${1:-status}"
shift || true
APPLY=0
[[ "${1:-}" != "--apply" ]] || APPLY=1
RUNTIME_ROOT="$(claw_runtime_root)"
STATE_ROOT="$(claw_openclaw_state)"
PYTHON="$(claw_python)"
case "$ACTION" in
  status|configure-ollama|configure-gateway|gaming|daily) ;;
  *) echo "Usage: 21_daily_profile.sh status|configure-ollama|configure-gateway|gaming|daily [--apply]" >&2; exit 2 ;;
esac
if [[ "$ACTION" == "status" ]]; then
  [[ ! -e "$RUNTIME_ROOT/state/gaming-mode" ]] && echo "PROFILE=daily" || echo "PROFILE=gaming"
  exit 0
fi
printf 'DAILY_PROFILE_PLAN action=%s root=%s one_model=1 parallel=1 queue=4\n' "$ACTION" "$RUNTIME_ROOT"
((APPLY == 1)) || { echo "DRY_RUN=PASS"; exit 0; }
[[ -f "$RUNTIME_ROOT/.openclaw-fedora-runtime" ]] || { echo "ERREUR: runtime non géré" >&2; exit 2; }
mkdir -p "$RUNTIME_ROOT/state"
case "$ACTION" in
  configure-ollama)
    # Match the B580 in Vulkan enumeration instead of assuming device zero.
    GPU_INDEX="$(vulkaninfo --summary | "$PYTHON" -c '
import re,sys
text=sys.stdin.read()
blocks=re.split(r"GPU(\d+):", text)
indices=[blocks[i] for i in range(1,len(blocks),2) if "B580" in blocks[i+1] and "Intel" in blocks[i+1]]
if len(indices)!=1: raise SystemExit("B580 Vulkan unique non observée")
print(indices[0])
')"
    # Models belong to the service user; preserve SELinux protections.
    sudo install -d -m 0750 -o ollama -g ollama "$RUNTIME_ROOT/models/ollama"
    sudo restorecon -RF "$RUNTIME_ROOT/models/ollama"
    sudo install -d -m 0755 /etc/systemd/system/ollama.service.d
    sudo tee /etc/systemd/system/ollama.service.d/openclaw-daily.conf >/dev/null <<EOF
[Service]
Environment="OLLAMA_HOST=127.0.0.1:11434"
Environment="OLLAMA_MODELS=$RUNTIME_ROOT/models/ollama"
Environment="OLLAMA_VULKAN=1"
Environment="GGML_VK_VISIBLE_DEVICES=$GPU_INDEX"
Environment="OLLAMA_NUM_PARALLEL=1"
Environment="OLLAMA_MAX_LOADED_MODELS=1"
Environment="OLLAMA_MAX_QUEUE=4"
Environment="OLLAMA_CONTEXT_LENGTH=8192"
Environment="OLLAMA_KEEP_ALIVE=3m"
EOF
    # Grant directory traversal only, not access to user projects or secrets.
    sudo setfacl -m u:ollama:--x "$RUNTIME_ROOT" "$RUNTIME_ROOT/models"
    sudo systemctl daemon-reload
    sudo systemctl restart ollama.service
    ;;
  configure-gateway)
    mkdir -p "$HOME/.config/systemd/user/openclaw-gateway.service.d"
    cat > "$HOME/.config/systemd/user/openclaw-gateway.service.d/openclaw-daily.conf" <<EOF
[Unit]
ConditionPathExists=!$RUNTIME_ROOT/state/gaming-mode
[Service]
UnsetEnvironment=OPENCLAW_CONFIG_PATH
Environment="OPENCLAW_STATE_DIR=$STATE_ROOT"
Environment="OPENCLAW_LOCAL_FEDORA_ROOT=$RUNTIME_ROOT"
Environment="OPENCLAW_LOCAL_CLOUD_ENABLED=false"
Environment="OLLAMA_API_KEY=ollama-local"
Environment="INTEL_VULKAN_API_KEY=intel-vulkan-local"
UMask=0077
RestartPreventExitStatus=78
EOF
    systemctl --user daemon-reload
    ;;
  gaming)
    # Refuse to interrupt a project mutation; mark before stopping services.
    exec 9>"$RUNTIME_ROOT/state/worker.lock"
    flock -n 9 || { echo "ERREUR: worker actif; terminer la tâche avant le mode jeux" >&2; exit 2; }
    touch "$RUNTIME_ROOT/state/gaming-mode"
    systemctl --user stop openclaw-gateway.service
    systemctl --user stop openclaw-llama-vulkan.service 2>/dev/null || true
    sudo systemctl stop ollama.service
    ;;
  daily)
    sudo systemctl start ollama.service
    rm -f "$RUNTIME_ROOT/state/gaming-mode"
    systemctl --user start openclaw-gateway.service
    ;;
esac
echo "DAILY_PROFILE_RESULT=PASS action=$ACTION"
