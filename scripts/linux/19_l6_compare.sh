#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd -P)"
# shellcheck source=scripts/linux/lib/runtime.sh
source "$SCRIPT_DIR/lib/runtime.sh"

KIND=""
OUTPUT=""
BASELINE=()
CANDIDATE=()

usage() {
  cat <<'EOF'
Usage: 19_l6_compare.sh --kind runtime|kernel|challenger \
       --baseline FILE --baseline FILE --baseline FILE \
       --candidate FILE --candidate FILE --candidate FILE \
       --output DECISION.json

Le comparateur exige au moins 3 runs par série et n'effectue aucune promotion automatique.
EOF
}

while (($#)); do
  case "$1" in
    --kind) shift; KIND="${1:-}" ;;
    --baseline) shift; BASELINE+=("${1:-}") ;;
    --candidate) shift; CANDIDATE+=("${1:-}") ;;
    --output) shift; OUTPUT="${1:-}" ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERREUR: argument inconnu: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

case "$KIND" in
  runtime) COMMAND="compare-runtime" ;;
  kernel) COMMAND="compare-kernel" ;;
  challenger) COMMAND="compare-challenger" ;;
  *) echo "ERREUR: --kind requis" >&2; exit 2 ;;
esac
[[ "${#BASELINE[@]}" -ge 3 && "${#CANDIDATE[@]}" -ge 3 ]] || {
  echo "ERREUR: au moins 3 preuves baseline et 3 candidat requises" >&2
  exit 2
}
[[ -n "$OUTPUT" ]] || { echo "ERREUR: --output requis" >&2; exit 2; }

PYTHON="$(claw_python)"
ARGS=(--root "$REPO_ROOT" --runtime-root "$(claw_runtime_root)" "$COMMAND")
for path in "${BASELINE[@]}"; do ARGS+=(--baseline "$path"); done
for path in "${CANDIDATE[@]}"; do ARGS+=(--candidate "$path"); done
ARGS+=(--output "$OUTPUT")

if "$PYTHON" -c 'import clawfedora' >/dev/null 2>&1; then
  exec "$PYTHON" -m clawfedora.optimization_cli "${ARGS[@]}"
fi
PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
  exec "$PYTHON" -m clawfedora.optimization_cli "${ARGS[@]}"
