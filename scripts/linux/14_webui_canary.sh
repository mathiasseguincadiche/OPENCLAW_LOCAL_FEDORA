#!/usr/bin/env bash
# Isolated Open WebUI v0.12.0 migration canary. Never touches the running WebUI volume.
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=scripts/linux/lib/runtime.sh
source "$SCRIPT_DIR/lib/runtime.sh"

IMAGE="ghcr.io/open-webui/open-webui:v0.12.0-slim"
RUNTIME_ROOT="$(claw_runtime_root)"
APPLY=0
WITH_DB=0
for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=1 ;;
    --with-db-copy) WITH_DB=1 ;;
    *) echo "Usage: $0 [--apply] [--with-db-copy]" >&2; exit 2 ;;
  esac
done
printf 'WEBUI_CANARY image=%s copy_db=%s no_host_mutation=true\\n' "$IMAGE" "$WITH_DB"
if (( APPLY == 0 )); then
  echo 'DRY_RUN=PASS (aucune image tirée, aucun conteneur démarré)'
  exit 0
fi

(( EUID != 0 )) || { echo 'Compte utilisateur requis, pas root' >&2; exit 2; }
command -v podman >/dev/null || { echo 'Podman requis' >&2; exit 2; }
[[ "$(podman info --format '{{.Host.Security.Rootless}}')" == true ]] || {
  echo 'Podman rootless requis' >&2; exit 2;
}
[[ -f "$RUNTIME_ROOT/.openclaw-fedora-runtime" ]] || {
  echo 'Installation gérée absente' >&2; exit 2;
}

TMP="$(mktemp -d -p "${TMPDIR:-/tmp}" clawfedora-webui-canary-XXXXXXXX)"
NAME="clawfedora-webui-canary-$$"
cleanup() {
  podman stop --ignore --time 5 "$NAME" >/dev/null 2>&1 || true
  rm -rf -- "$TMP"
}
trap cleanup EXIT
chmod 700 "$TMP"
mkdir -m 700 "$TMP/data"
if (( WITH_DB )); then
  SRC="$RUNTIME_ROOT/state/webui/data/webui.db"
  [[ -f "$SRC" && ! -L "$SRC" ]] || {
    echo 'Base WebUI réelle absente ou liée ; canary refusé' >&2; exit 2;
  }
  # SQLite's online backup gives a consistent copy while the original service runs.
  python3 - "$SRC" "$TMP/data/webui.db" <<'PY'
import sqlite3
import sys
with sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True) as original:
    with sqlite3.connect(sys.argv[2]) as target:
        original.backup(target)
PY
  chmod 600 "$TMP/data/webui.db"
fi

podman pull "$IMAGE"
DIGEST="$(podman image inspect "$IMAGE" --format '{{index .RepoDigests 0}}')"
if [[ ! "$DIGEST" =~ ^ghcr.io/open-webui/open-webui@sha256:[a-f0-9]{64}$ ]]; then
  echo 'Impossible de déterminer une empreinte immuable vérifiable' >&2
  exit 2
fi
printf 'CANDIDATE_IMAGE=%s\\n' "$DIGEST"

# Network-free, throwaway container; host WebUI uses a different name/volume.
podman run --rm --detach --name "$NAME" --network none \
  --cap-drop ALL --security-opt no-new-privileges --pids-limit 256 \
  --memory 3g --cpus 2 \
  -e OFFLINE_MODE=true -e ENABLE_OLLAMA_API=false \
  -e ENABLE_OPENAI_API=false -e ENABLE_PLUGINS=true \
  -e ENABLE_FUNCTIONS=true -e ENABLE_TOOLS=false \
  -e ENABLE_TOOL_SERVERS=false -e ENABLE_SIGNUP=false \
  -e WEBUI_AUTH=true -e HOST=127.0.0.1 -e PORT=8080 \
  -e WEBUI_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')" \
  --volume "$TMP/data:/app/backend/data:Z" "$DIGEST" >/dev/null

READY=0
for _ in {1..45}; do
  if podman exec "$NAME" python -c \
      'from urllib.request import urlopen; urlopen("http://127.0.0.1:8080/health", timeout=2)' \
      >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 2
done
if (( READY == 0 )); then
  podman logs --tail 30 "$NAME" >&2 || true
  echo 'WEBUI_CANARY_RESULT=FAIL (démarrage ou /health)' >&2
  exit 1
fi
python3 - "$TMP/data/webui.db" <<'PY'
import sqlite3
import sys
with sqlite3.connect(sys.argv[1]) as db:
    cols = {r[1] for r in db.execute('PRAGMA table_info("function")')}
required = {
    "id", "user_id", "name", "type", "content", "meta",
    "valves", "is_active", "is_global", "updated_at", "created_at",
}
missing = required - cols
if missing:
    raise SystemExit("WEBUI_CANARY_RESULT=FAIL, colonnes manquantes: " + str(sorted(missing)))
print("WEBUI_CANARY_SCHEMA=PASS")
PY
echo 'WEBUI_CANARY_RESULT=PASS (préqualification conteneur, pas validation navigateur)'
echo "Aucun digest du déploiement principal n'a été modifié."
