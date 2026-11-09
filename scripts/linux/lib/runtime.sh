#!/usr/bin/env bash
# Rôle       : bibliothèque commune (chemins, stockage /data, versions épinglées, verrou worker).
# Usage      : `source` depuis les scripts ; ne pas l'exécuter directement.
# Effets     : définit des fonctions claw_* ; aucune modification au chargement.
set -Eeuo pipefail

# Node.js for OpenClaw. Fedora 45's default `nodejs` is Node 22, refused by OpenClaw's
# engine; nodejs24 (24.18.0) is accepted. The -bin packages provide plain `node`/`npm`.
# Single source for 00_bootstrap.sh and the Fedora 45 CI job.
# shellcheck disable=SC2034
CLAW_NODE_PACKAGES=(nodejs24 nodejs24-npm nodejs24-bin nodejs24-npm-bin)

claw_repo_root() {
  cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd -P
}

# Use the system standard library even before the managed venv exists.
claw_storage() {
  local python
  python="$(command -v python3 2>/dev/null)" || {
    echo "ERREUR: python3 requis pour vérifier le stockage." >&2; return 127;
  }
  "$python" -I -S "$(claw_repo_root)/src/clawfedora/storage.py" "$@"
}

claw_runtime_root() { claw_storage root; }
claw_mountpoint() { claw_storage mount; }

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

# The CLI installed by 15_verified_installer.sh, found even from a fresh terminal whose PATH
# never received ~/.openclaw/bin. Managed locations win over whatever the PATH inherited.
claw_openclaw_bin() {
  local candidate
  for candidate in "$HOME/.openclaw/bin/openclaw" "$HOME/.local/bin/openclaw"; do
    if [[ -x "$candidate" && ! -d "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  command -v openclaw 2>/dev/null || return 1
}

# Something still accepts connections on the loopback gateway port.
claw_port_listening() {
  (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null
}

# Stop the managed OpenClaw Gateway, PROVE it is stopped, then remove its service definition.
# Always the managed CLI with the managed state directory: an inherited OPENCLAW_STATE_DIR or
# OPENCLAW_CONFIG_PATH would target another instance. Returns 2 before any removal when the
# stop cannot be confirmed, so callers must not delete anything after a failure.
# Usage: claw_uninstall_gateway STATE_DIR [PORT]   (port: config/platform.yaml default_port)
claw_uninstall_gateway() {
  local state_dir="$1" port="${2:-18789}" unit="openclaw-gateway.service"
  local cli="" unit_known=0 cli_rc=0 waited=0
  local wait_limit="${CLAW_GATEWAY_STOP_WAIT:-10}"
  local drop_in="$HOME/.config/systemd/user/$unit.d/openclaw-daily.conf"
  cli="$(claw_openclaw_bin || true)"
  if systemctl --user cat "$unit" >/dev/null 2>&1; then unit_known=1; fi
  if [[ -z "$cli" && "$unit_known" == 0 ]]; then
    if claw_port_listening "$port"; then
      echo "ERREUR: port $port actif sans service ni CLI OpenClaw géré; arrêt non confirmé" >&2
      return 2
    fi
    echo "GATEWAY_STOP=ABSENT aucun service ni CLI OpenClaw géré"
    return 0
  fi
  if [[ -n "$cli" ]]; then
    env -u OPENCLAW_CONFIG_PATH OPENCLAW_STATE_DIR="$state_dir" "$cli" gateway stop || cli_rc=$?
  fi
  if ((unit_known == 1)); then
    systemctl --user stop "$unit" || {
      echo "ERREUR: arrêt de $unit refusé par systemd; rien n'a été supprimé" >&2
      return 2
    }
    if systemctl --user is-active --quiet "$unit"; then
      echo "ERREUR: $unit encore actif; rien n'a été supprimé" >&2
      return 2
    fi
  fi
  while claw_port_listening "$port"; do
    if ((waited >= wait_limit * 2)); then
      echo "ERREUR: le port $port répond encore après l'arrêt; rien n'a été supprimé" >&2
      return 2
    fi
    sleep 0.5
    waited=$((waited + 1))
  done
  ((cli_rc == 0)) || echo "WARN: openclaw gateway stop a échoué ($cli_rc) mais l'arrêt est vérifié" >&2
  echo "GATEWAY_STOP=CONFIRMED"
  if [[ -n "$cli" ]]; then
    env -u OPENCLAW_CONFIG_PATH OPENCLAW_STATE_DIR="$state_dir" "$cli" gateway uninstall || {
      echo "ERREUR: définition du Gateway non retirée; service arrêté, données intactes" >&2
      return 2
    }
  elif ((unit_known == 1)); then
    systemctl --user disable "$unit" || true
    echo "WARN: CLI OpenClaw introuvable; service arrêté et désactivé, définition conservée" >&2
  fi
  # Drop-in written by 11_daily_profile.sh configure-gateway: ours to remove, nothing else.
  if [[ -f "$drop_in" && ! -L "$drop_in" ]]; then
    rm -f -- "$drop_in"
    rmdir -- "$(dirname -- "$drop_in")" 2>/dev/null || true
  fi
  systemctl --user daemon-reload || true
  echo "GATEWAY_UNINSTALL=PASS"
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
  claw_require_storage "$runtime_root"
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

# The guard covers every explicit root, not only the preferred path.
claw_require_storage() {
  claw_storage check --runtime-root "${1:-$(claw_runtime_root)}"
}

claw_podman() {
  local runtime_root config
  runtime_root="$(claw_runtime_root)"
  config="$runtime_root/runtime/generated/webui-storage.conf"
  [[ -f "$config" && ! -L "$config" ]] || {
    echo "ERREUR: stockage Podman WebUI non préparé" >&2; return 2;
  }
  TMPDIR="$runtime_root/runtime/podman/tmp" \
    CONTAINERS_STORAGE_CONF="$config" command podman --remote=false "$@"
}
