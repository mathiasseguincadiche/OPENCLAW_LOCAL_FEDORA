#!/usr/bin/env bash
set -Eeuo pipefail

claw_repo_root() {
  cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd -P
}

claw_runtime_root() {
  printf '%s\n' "${OPENCLAW_LOCAL_FEDORA_ROOT:-/srv/openclaw-local}"
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
