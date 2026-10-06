#!/usr/bin/env bash
set -Eeuo pipefail

claw_repo_root() {
  cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd -P
}

claw_runtime_root() {
  printf '%s\n' "${OPENCLAW_LOCAL_FEDORA_ROOT:-/srv/openclaw-local}"
}

claw_extract_openclaw_version() {
  local output="${1:-}"
  if [[ "$output" =~ (^|[^0-9])([0-9]{4}\.[0-9]+\.[0-9]+)([^0-9.]|$) ]]; then
    printf '%s\n' "${BASH_REMATCH[2]}"
    return 0
  fi
  return 1
}

claw_extract_ollama_version() {
  local output="${1:-}"
  if [[ "$output" =~ (^|[^0-9.])([0-9]+\.[0-9]+\.[0-9]+)([^0-9.]|$) ]]; then
    printf '%s\n' "${BASH_REMATCH[2]}"
    return 0
  fi
  return 1
}

claw_python() {
  local runtime_root repo_root system_python
  runtime_root="$(claw_runtime_root)"
  repo_root="$(claw_repo_root)"

  if [[ -x "$runtime_root/runtime/venv/bin/python" ]]; then
    printf '%s\n' "$runtime_root/runtime/venv/bin/python"
    return 0
  fi
  if [[ -x "$repo_root/.venv/bin/python" ]]; then
    printf '%s\n' "$repo_root/.venv/bin/python"
    return 0
  fi
  if system_python="$(command -v python3 2>/dev/null)" && [[ -n "$system_python" ]]; then
    printf '%s\n' "$system_python"
    return 0
  fi

  echo "ERREUR: aucun Python géré ni python3 système disponible." >&2
  return 127
}

claw_openclaw_state() {
  printf '%s/state/openclaw\n' "$(claw_runtime_root)"
}

claw_pin() {
  local section="$1" key="$2" repo_root python
  repo_root="$(claw_repo_root)"
  python="$(claw_python)"
  # Runs before bootstrap: parse only the contract's quoted scalar pins with stdlib.
  "$python" -I -S - "$repo_root/config/runtime_versions.yaml" "$section" "$key" <<'PY'
import re, sys
from pathlib import Path
section, key = sys.argv[2:]
text = Path(sys.argv[1]).read_text(encoding="utf-8")
block = re.search(r"(?m)^" + re.escape(section) + r":\n((?:[ \t].*\n|\n)*)", text)
if block is None:
    raise SystemExit("Section de version absente: " + section)
match = re.search(r'(?m)^  ' + re.escape(key) + r': "([^"\n]+)"(?:[ \t]*(?:#.*)?)$', block[1])
if match is None:
    raise SystemExit("Version scalaire citée absente: " + section + "." + key)
print(match[1])
PY
}

claw_lock_worker() {
  local runtime_root lock_path expected_identity inherited_identity
  runtime_root="$(claw_runtime_root)"
  lock_path="$runtime_root/state/worker.lock"
  [[ -f "$runtime_root/.openclaw-fedora-runtime" ]] || { echo "ERREUR: runtime géré requis" >&2; return 2; }
  [[ ! -L "$runtime_root" && ! -L "$runtime_root/state" && ! -L "$lock_path" ]] || { echo "ERREUR: verrou lié interdit" >&2; return 2; }
  mkdir -p "$runtime_root/state"
  expected_identity="$(stat -Lc '%d:%i' "$lock_path" 2>/dev/null || true)"
  inherited_identity="$(stat -Lc '%d:%i' "/proc/$$/fd/9" 2>/dev/null || true)"
  # A migration passes the already-locked descriptor to child installers.
  # flock on that same open description verifies/reuses ownership without deadlock.
  if [[ -z "$expected_identity" || "$expected_identity" != "$inherited_identity" ]]; then
    exec 9>"$lock_path"
  fi
  flock -n 9 || { echo "ERREUR: tâche ou discussion active; attendre sa fin avant la maintenance" >&2; return 2; }
}
