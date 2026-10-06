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
