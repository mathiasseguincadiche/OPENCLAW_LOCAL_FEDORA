#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=scripts/linux/lib/runtime.sh
source "$SCRIPT_DIR/lib/runtime.sh"

APPLY=0
OPENCLAW_PIN="$(claw_pin openclaw version)"
PARALLEL_PIN="$OPENCLAW_PIN"

usage() {
  cat <<'EOF'
Usage: 03_configure_openclaw.sh [--apply]

Dry-run par défaut. --apply exécute la validation et l'application du patch OpenClaw.
EOF
}

while (($#)); do
  case "$1" in
    --apply) APPLY=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERREUR: argument inconnu: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

REPO_ROOT="$(claw_repo_root)"
RUNTIME_ROOT="$(claw_runtime_root)"
PYTHON="$(claw_python)"
STATE_ROOT="$(claw_openclaw_state)"
GENERATED_ROOT="$RUNTIME_ROOT/runtime/generated"
SYSTEM_WORKSPACE="$RUNTIME_ROOT/workspaces/system"
PATCH_PATH="$GENERATED_ROOT/openclaw.patch.json"
SCHEMA_PATH="$GENERATED_ROOT/openclaw.schema.json"

contains_model() {
  local needle="${1,,}"
  shift
  local model
  for model in "$@"; do
    [[ "${model,,}" == "$needle" ]] && return 0
  done
  return 1
}

require_daily_model() {
  local inventory_json="$1"
  local -a expected actual
  mapfile -t expected < <(jq -r '.models.providers.ollama.models[]?.id' "$PATCH_PATH")
  mapfile -t actual < <(jq -r '.models[]? | (.model // .name // empty)' <<<"$inventory_json")
  [[ "${#expected[@]}" -eq 1 ]] || {
    echo "ERREUR: la configuration n'expose pas exactement un modèle quotidien." >&2
    return 2
  }
  contains_model "${expected[0]}" "${actual[@]}" || {
    echo "ERREUR: modèle requis absent d'Ollama: ${expected[0]}" >&2
    return 2
  }
}

printf 'OPENCLAW_CONFIG_PLAN runtime=%s state=%s\n' "$RUNTIME_ROOT" "$STATE_ROOT"
printf '  openclaw exact pin: %s\n' "$OPENCLAW_PIN"
printf '  parallel pin: %s\n' "$PARALLEL_PIN"
printf '  workspaces: %s\n' "$RUNTIME_ROOT/workspaces"
printf '  patch: %s\n' "$PATCH_PATH"
printf '  schema: %s\n' "$SCHEMA_PATH"
printf '  sequence: version -> plugin -> schema -> agents -> render -> model-present -> patch-dry-run -> apply -> validate -> agents-list\n'

if ((APPLY == 0)); then
  echo "DRY_RUN=PASS -- aucune configuration OpenClaw modifiée."
  exit 0
fi

OPENCLAW="$(command -v openclaw || true)"
[[ -n "$OPENCLAW" ]] || { echo "ERREUR: openclaw absent du PATH." >&2; exit 127; }
command -v jq >/dev/null 2>&1 || { echo "ERREUR: jq requis." >&2; exit 127; }
command -v curl >/dev/null 2>&1 || { echo "ERREUR: curl requis." >&2; exit 127; }

OPENCLAW_VERSION_TEXT="$($OPENCLAW --version 2>/dev/null | head -n1)"
OPENCLAW_VERSION="$(claw_extract_openclaw_version "$OPENCLAW_VERSION_TEXT" || true)"
[[ "$OPENCLAW_VERSION" == "$OPENCLAW_PIN" ]] || {
  echo "ERREUR: OpenClaw exactement $OPENCLAW_PIN requis; détecté: ${OPENCLAW_VERSION_TEXT:-inconnu}" >&2
  exit 2
}

"$PYTHON" -m clawfedora.ops_cli --root "$REPO_ROOT" --runtime-root "$RUNTIME_ROOT" backup
mkdir -p "$STATE_ROOT" "$GENERATED_ROOT" "$SYSTEM_WORKSPACE"
unset OPENCLAW_CONFIG_PATH
export OPENCLAW_STATE_DIR="$STATE_ROOT"
export OPENCLAW_LOCAL_FEDORA_ROOT="$RUNTIME_ROOT"
export OLLAMA_API_KEY="ollama-local"

if [[ ! -f "$STATE_ROOT/openclaw.json" ]]; then
  "$OPENCLAW" setup --baseline --workspace "$SYSTEM_WORKSPACE"
fi

if ! "$OPENCLAW" config validate --json >/dev/null; then
  "$OPENCLAW" doctor --fix --non-interactive
  "$OPENCLAW" config validate --json >/dev/null
fi

PLUGIN_JSON="$($OPENCLAW plugins list --json)"
if ! jq -e '.plugins[]? | select(.id == "parallel")' >/dev/null <<<"$PLUGIN_JSON"; then
  "$OPENCLAW" plugins install "npm:@openclaw/parallel-plugin@$PARALLEL_PIN" --pin
else
  "$OPENCLAW" plugins update "@openclaw/parallel-plugin@$PARALLEL_PIN"
fi
PLUGIN_JSON="$($OPENCLAW plugins list --json)"
if [[ "$(jq -r '.plugins[]? | select(.id == "parallel") | .enabled' <<<"$PLUGIN_JSON" | head -n1)" != "true" ]]; then
  "$OPENCLAW" plugins enable parallel
fi
"$OPENCLAW" plugins inspect parallel --runtime --json | jq -e . >/dev/null

# Deploy only our reviewed, dependency-free plugin to a private managed path.
"$PYTHON" - "$REPO_ROOT" "$RUNTIME_ROOT" <<'PYCODE'
import shutil, sys
from pathlib import Path
source = Path(sys.argv[1]) / "plugins/clawfedora-toolkit"
destination = Path(sys.argv[2]) / "runtime/extensions/clawfedora-toolkit"
for path in [destination, *destination.parents]:
    if path.is_symlink(): raise SystemExit("Plugin lié interdit")
destination.mkdir(parents=True, exist_ok=True)
destination.chmod(0o750)
for name in ("package.json", "openclaw.plugin.json", "index.mjs"):
    target = destination / name
    if target.is_symlink(): raise SystemExit("Fichier plugin lié interdit")
    shutil.copyfile(source / name, target)
    target.chmod(0o640)
PYCODE

"$OPENCLAW" config schema | tee "$SCHEMA_PATH" | jq -e . >/dev/null
"$PYTHON" -m clawfedora.cli --root "$REPO_ROOT" agents deploy --runtime-root "$RUNTIME_ROOT"
"$PYTHON" -m clawfedora.cli --root "$REPO_ROOT" openclaw render \
  --runtime-root "$RUNTIME_ROOT" --output "$PATCH_PATH"

# Preserve retired entries temporarily: the native SDK removes only their config records.
"$PYTHON" - "$PATCH_PATH" <<'PYCODE'
import json, sys
from pathlib import Path
from clawfedora.openclaw_config import prepare_migration_patch
path = Path(sys.argv[1])
payload = prepare_migration_patch(json.loads(path.read_text()))
path.write_text(json.dumps(payload, indent=2) + "\n")
PYCODE

OLLAMA_JSON="$(curl -fsS --max-time 5 'http://127.0.0.1:11434/api/tags')"
require_daily_model "$OLLAMA_JSON"

"$OPENCLAW" config patch --file "$PATCH_PATH" --dry-run
"$OPENCLAW" config patch --file "$PATCH_PATH"
node "$REPO_ROOT/scripts/linux/retire_managed_agents.mjs" "$OPENCLAW"
"$OPENCLAW" config validate --json | jq -e . >/dev/null
"$OPENCLAW" plugins inspect clawfedora-toolkit --runtime --json | jq -e '
  .plugin.enabled == true and .plugin.status == "loaded" and
  (.plugin.toolNames | sort) ==
  (["clawfedora_search", "clawfedora_outline", "clawfedora_diagram", "clawfedora_check", "clawfedora_lint", "clawfedora_tool_status"] | sort)
' >/dev/null
AGENTS_JSON="$($OPENCLAW agents list --json)"
AGENT_COUNT="$(
  jq -r '
    if type == "array" then length
    elif (.agents? | type) == "array" then (.agents | length)
    elif (.list? | type) == "array" then (.list | length)
    else 0
    end
  ' <<<"$AGENTS_JSON"
)"
[[ "$AGENT_COUNT" -eq 7 ]] || {
  echo "ERREUR: OpenClaw n'expose pas exactement 7 agents après application (count=$AGENT_COUNT)." >&2
  exit 2
}

echo "OPENCLAW_CONFIG_RESULT=PASS agents=7 openclaw=$OPENCLAW_VERSION"
