#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=scripts/linux/lib/runtime.sh
source "$SCRIPT_DIR/lib/runtime.sh"

APPLY=0
BACKEND="ollama-vulkan"

usage() {
  cat <<'EOF'
Usage: 04_configure_openclaw.sh [--apply] [--backend ollama-vulkan|llama-cpp-vulkan|llama-cpp-sycl]

Dry-run par défaut. --apply exécute la validation et l'application du patch OpenClaw.
EOF
}

while (($#)); do
  case "$1" in
    --apply) APPLY=1 ;;
    --backend)
      shift
      [[ $# -gt 0 ]] || { echo "ERREUR: --backend exige une valeur" >&2; exit 2; }
      BACKEND="$1"
      ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERREUR: argument inconnu: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

case "$BACKEND" in
  ollama-vulkan|llama-cpp-vulkan|llama-cpp-sycl) ;;
  *) echo "ERREUR: backend non supporté: $BACKEND" >&2; exit 2 ;;
esac

REPO_ROOT="$(claw_repo_root)"
RUNTIME_ROOT="$(claw_runtime_root)"
PYTHON="$(claw_python)"
STATE_ROOT="${XDG_STATE_HOME:-$HOME/.local/state}/openclaw-local"
GENERATED_ROOT="$RUNTIME_ROOT/runtime/generated"
SYSTEM_WORKSPACE="$RUNTIME_ROOT/workspaces/system"
PATCH_PATH="$GENERATED_ROOT/openclaw.$BACKEND.patch.json"
SCHEMA_PATH="$GENERATED_ROOT/openclaw.schema.json"

printf 'OPENCLAW_CONFIG_PLAN backend=%s runtime=%s state=%s\n' "$BACKEND" "$RUNTIME_ROOT" "$STATE_ROOT"
printf '  workspaces: %s\n' "$RUNTIME_ROOT/workspaces"
printf '  patch: %s\n' "$PATCH_PATH"
printf '  schema: %s\n' "$SCHEMA_PATH"
printf '  sequence: schema -> agents -> render -> patch-dry-run -> apply -> validate -> agents-list\n'

if ((APPLY == 0)); then
  echo "DRY_RUN=PASS -- aucune configuration OpenClaw modifiée."
  exit 0
fi

OPENCLAW="$(command -v openclaw || true)"
[[ -n "$OPENCLAW" ]] || { echo "ERREUR: openclaw absent du PATH." >&2; exit 127; }
command -v jq >/dev/null 2>&1 || { echo "ERREUR: jq requis." >&2; exit 127; }
command -v curl >/dev/null 2>&1 || { echo "ERREUR: curl requis." >&2; exit 127; }

mkdir -p "$STATE_ROOT" "$GENERATED_ROOT" "$SYSTEM_WORKSPACE"
export OPENCLAW_STATE_DIR="$STATE_ROOT"
export OPENCLAW_LOCAL_FEDORA_ROOT="$RUNTIME_ROOT"
export OLLAMA_API_KEY="ollama-local"
export INTEL_VULKAN_API_KEY="intel-vulkan-local"
export INTEL_SYCL_API_KEY="intel-sycl-local"

if [[ ! -f "$STATE_ROOT/openclaw.json" ]]; then
  "$OPENCLAW" setup --baseline --workspace "$SYSTEM_WORKSPACE"
fi

PLUGIN_JSON="$($OPENCLAW plugins list --json)"
if ! jq -e '.plugins[]? | select(.id == "parallel")' >/dev/null <<<"$PLUGIN_JSON"; then
  "$OPENCLAW" plugins install 'npm:@openclaw/parallel-plugin@2026.7.1' --pin
  PLUGIN_JSON="$($OPENCLAW plugins list --json)"
fi
if [[ "$(jq -r '.plugins[]? | select(.id == "parallel") | .enabled' <<<"$PLUGIN_JSON" | head -n1)" != "true" ]]; then
  "$OPENCLAW" plugins enable parallel
fi
"$OPENCLAW" plugins inspect parallel --runtime --json | jq -e . >/dev/null

"$OPENCLAW" config schema | tee "$SCHEMA_PATH" | jq -e . >/dev/null
"$PYTHON" -m clawfedora.cli --root "$REPO_ROOT" agents deploy --runtime-root "$RUNTIME_ROOT"
"$PYTHON" -m clawfedora.cli --root "$REPO_ROOT" openclaw render \
  --runtime-root "$RUNTIME_ROOT" --backend "$BACKEND" --output "$PATCH_PATH"

if [[ "$BACKEND" == "ollama-vulkan" ]]; then
  curl -fsS --max-time 5 'http://127.0.0.1:11434/api/tags' >/dev/null
else
  PROVIDER="intel-vulkan"
  [[ "$BACKEND" == "llama-cpp-sycl" ]] && PROVIDER="intel-sycl"
  BASE_URL="$(jq -r --arg provider "$PROVIDER" '.models.providers[$provider].baseUrl' "$PATCH_PATH")"
  curl -fsS --max-time 10 "$BASE_URL/models?reload=1" | jq -e . >/dev/null
fi

"$OPENCLAW" config patch --file "$PATCH_PATH" --dry-run
"$OPENCLAW" config patch --file "$PATCH_PATH"
"$OPENCLAW" config validate --json | jq -e . >/dev/null
AGENTS_JSON="$($OPENCLAW agents list --json)"
[[ "$(jq '[.[]?] | length' <<<"$AGENTS_JSON")" -eq 8 ]] || {
  echo "ERREUR: OpenClaw n'expose pas exactement 8 agents après application." >&2
  exit 2
}

echo "OPENCLAW_CONFIG_RESULT=PASS backend=$BACKEND agents=8"
