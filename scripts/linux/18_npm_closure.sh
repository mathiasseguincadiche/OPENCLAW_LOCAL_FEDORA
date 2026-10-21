#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=scripts/linux/lib/runtime.sh
source "$SCRIPT_DIR/lib/runtime.sh"

[[ "${1:-}" == --apply || $# -eq 0 ]] || {
  echo "Usage: 18_npm_closure.sh [--apply]" >&2
  exit 2
}
[[ $# -le 1 ]] || { echo "Arguments supplémentaires refusés" >&2; exit 2; }
REPO_ROOT="$(claw_repo_root)"
RUNTIME_ROOT="$(claw_runtime_root)"
LOCK_ROOT="$REPO_ROOT/config/npm-runtime"
PREFIX="$HOME/.openclaw"
OPENCLAW_PIN="$(claw_pin openclaw version)"
echo "NPM_CLOSURE_PLAN version=$OPENCLAW_PIN method=npm-ci integrity=sha512 prefix=$PREFIX"

[[ "${1:-}" == --apply ]] || { echo "NPM_CLOSURE_DRY_RUN=PASS"; exit 0; }
((EUID != 0)) || { echo "NPM_CLOSURE_RESULT=REFUSED root interdit" >&2; exit 2; }
claw_require_storage "$RUNTIME_ROOT"
command -v npm >/dev/null 2>&1 || { echo "npm requis" >&2; exit 127; }
command -v node >/dev/null 2>&1 || { echo "node requis" >&2; exit 127; }
PYTHON="$(claw_python)"
"$PYTHON" "$REPO_ROOT/scripts/validation/check_dependency_artifact_locks.py"

# Reuse the user prefix of the historical verified global installation.
# npm GLOBAL mode does not honour a project lockfile, so use local npm ci in
# a private staging folder and move the fully verified node_modules tree.
[[ ! -L "$PREFIX" && ! -L "$PREFIX/lib" && ! -L "$PREFIX/bin" ]] || {
  echo "NPM_CLOSURE_RESULT=REFUSED préfixe lié" >&2; exit 2;
}
install -d -m 0700 "$PREFIX" "$PREFIX/lib" "$PREFIX/bin"
LIVE="$PREFIX/lib/node_modules"
[[ ! -L "$LIVE" ]] || { echo "NPM_CLOSURE_RESULT=REFUSED arbre npm lié" >&2; exit 2; }
STAGE="$(mktemp -d "$PREFIX/lib/.clawfedora-npm-XXXXXXXX")"
OLD=""
SWAPPED=0
cleanup() {
  local rc="$?"
  if ((rc != 0 && SWAPPED == 1)); then
    rm -rf -- "$LIVE"
    if [[ -n "$OLD" && -d "$OLD" ]]; then mv -- "$OLD" "$LIVE"; fi
  fi
  rm -rf -- "$STAGE"
  if ((rc == 0)) && [[ -n "$OLD" && -d "$OLD" ]]; then rm -rf -- "$OLD"; fi
}
trap cleanup EXIT

install -m 0600 "$LOCK_ROOT/package.json" "$STAGE/package.json"
install -m 0600 "$LOCK_ROOT/package-lock.json" "$STAGE/package-lock.json"
npm ci --prefix "$STAGE" --ignore-scripts --no-audit --no-fund --engine-strict
npm ls --all --prefix "$STAGE" >/dev/null
STAGED_CLI="$STAGE/node_modules/.bin/openclaw"
[[ -x "$STAGED_CLI" ]] || { echo "NPM_CLOSURE_RESULT=REFUSED CLI absent" >&2; exit 2; }
VER="$("$STAGED_CLI" --version 2>/dev/null | head -n1)"
ACTUAL="$(claw_extract_openclaw_version "$VER" || true)"
[[ "$ACTUAL" == "$OPENCLAW_PIN" ]] || {
  echo "NPM_CLOSURE_RESULT=REFUSED version OpenClaw incorrecte" >&2; exit 2;
}
[[ -d "$STAGE/node_modules/@openclaw/parallel-plugin" ]] || {
  echo "NPM_CLOSURE_RESULT=REFUSED plugin Parallel absent" >&2; exit 2;
}

if [[ -e "$LIVE" ]]; then
  OLD="$PREFIX/lib/.clawfedora-previous-$PPID-$$"
  [[ ! -e "$OLD" ]] || { echo "NPM_CLOSURE_RESULT=REFUSED sauvegarde existante" >&2; exit 2; }
  mv -- "$LIVE" "$OLD"
fi
SWAPPED=1
mv -- "$STAGE/node_modules" "$LIVE"
if [[ -L "$PREFIX/bin/openclaw" ]]; then
  [[ "$(readlink "$PREFIX/bin/openclaw")" == "../lib/node_modules/.bin/openclaw" ]] ||
    rm -- "$PREFIX/bin/openclaw"
elif [[ -e "$PREFIX/bin/openclaw" ]]; then
  echo "NPM_CLOSURE_RESULT=REFUSED CLI existante non liée" >&2
  exit 2
fi
[[ -e "$PREFIX/bin/openclaw" ]] ||
  ln -s ../lib/node_modules/.bin/openclaw "$PREFIX/bin/openclaw"
npm ls --global --all --prefix "$PREFIX" >/dev/null
VER="$("$PREFIX/bin/openclaw" --version 2>/dev/null | head -n1)"
ACTUAL="$(claw_extract_openclaw_version "$VER" || true)"
[[ "$ACTUAL" == "$OPENCLAW_PIN" ]] || {
  echo "NPM_CLOSURE_RESULT=REFUSED mauvaise version après installation" >&2; exit 2;
}
echo "NPM_CLOSURE_RESULT=PASS version=$ACTUAL integrity=registry-lock"
