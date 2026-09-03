#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd -P)"
# shellcheck source=scripts/linux/lib/runtime.sh
source "$SCRIPT_DIR/lib/runtime.sh"

BACKEND="ollama-vulkan"
KIND="runtime"
CANDIDATE_ID="ollama-vulkan"
OUTPUT=""

usage() {
  cat <<'EOF'
Usage: 18_l6_snapshot.sh --backend BACKEND --kind runtime|kernel \
       --candidate-id ID [--output FILE]

BACKEND: ollama-vulkan | llama-cpp-vulkan | llama-cpp-sycl
Le run est toujours local, sans téléchargement, sous systemd-inhibit.
EOF
}

while (($#)); do
  case "$1" in
    --backend) shift; BACKEND="${1:-}" ;;
    --kind) shift; KIND="${1:-}" ;;
    --candidate-id) shift; CANDIDATE_ID="${1:-}" ;;
    --output) shift; OUTPUT="${1:-}" ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERREUR: argument inconnu: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

case "$BACKEND" in
  ollama-vulkan) ENDPOINT="http://127.0.0.1:11434" ;;
  llama-cpp-vulkan) ENDPOINT="http://127.0.0.1:8081/v1" ;;
  llama-cpp-sycl) ENDPOINT="http://127.0.0.1:8080/v1" ;;
  *) echo "ERREUR: backend invalide: $BACKEND" >&2; exit 2 ;;
esac
case "$KIND" in runtime|kernel) ;; *) echo "ERREUR: kind invalide: $KIND" >&2; exit 2 ;; esac

RUNTIME_ROOT="$(claw_runtime_root)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
if [[ -z "$OUTPUT" ]]; then
  OUTPUT="$RUNTIME_ROOT/proofs/l6/${KIND}-${CANDIDATE_ID}-${STAMP}.json"
fi
PYTHON="$(claw_python)"

run_snapshot() {
  local -a args=(
    --root "$REPO_ROOT"
    --runtime-root "$RUNTIME_ROOT"
    snapshot
    --backend "$BACKEND"
    --endpoint "$ENDPOINT"
    --kind "$KIND"
    --candidate-id "$CANDIDATE_ID"
    --output "$OUTPUT"
  )
  export OPENCLAW_LOCAL_CLOUD_ENABLED=false
  if "$PYTHON" -c 'import clawfedora' >/dev/null 2>&1; then
    "$PYTHON" -m clawfedora.optimization_cli "${args[@]}"
  else
    PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
      "$PYTHON" -m clawfedora.optimization_cli "${args[@]}"
  fi
}

if [[ "${OPENCLAW_LOCAL_FEDORA_SLEEP_INHIBITED:-}" == "1" ]]; then
  run_snapshot
  exit $?
fi
command -v systemd-inhibit >/dev/null 2>&1 || {
  echo "ERREUR: systemd-inhibit requis pour L6" >&2
  exit 2
}
export -f run_snapshot
export REPO_ROOT RUNTIME_ROOT BACKEND ENDPOINT KIND CANDIDATE_ID OUTPUT PYTHON
export OPENCLAW_LOCAL_FEDORA_SLEEP_INHIBITED=1
systemd-inhibit --what=sleep --mode=block --why="OPENCLAW_LOCAL_FEDORA L6 snapshot" \
  bash -c run_snapshot
