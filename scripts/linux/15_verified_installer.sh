#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=scripts/linux/lib/runtime.sh
source "$SCRIPT_DIR/lib/runtime.sh"
KIND="${1:-}"
MODE="${2:-}"
[[ "$KIND" == openclaw || "$KIND" == ollama ]] || { echo "Usage: 15_verified_installer.sh openclaw|ollama [--apply]" >&2; exit 2; }
[[ -z "$MODE" || "$MODE" == --apply ]] || { echo "Usage: 15_verified_installer.sh openclaw|ollama [--apply]" >&2; exit 2; }
[[ $# -le 2 ]] || { echo "Arguments supplémentaires refusés" >&2; exit 2; }
PIN="$(claw_pin "$KIND" version)"
REPO_ROOT="$(claw_repo_root)"
VERIFY="$REPO_ROOT/scripts/validation/verify_install_artifact.py"
PYTHON="$(claw_python)"
URL="$("$PYTHON" "$VERIFY" url "$KIND" "$PIN")"
echo "VERIFIED_INSTALL_PLAN kind=$KIND exact_version=$PIN source=$URL sha_required=true"
[[ "$MODE" == --apply ]] || { echo "VERIFIED_INSTALL_DRY_RUN=PASS"; exit 0; }
((EUID != 0)) || { echo "Installateur vérifié: lancer en utilisateur non root" >&2; exit 2; }
claw_require_storage "$(claw_runtime_root)"
command -v curl >/dev/null || { echo "curl requis" >&2; exit 127; }
[[ "$(uname -m)" == x86_64 ]] || { echo "Architecture x86_64 exigée par le manifeste" >&2; exit 2; }
umask 077
TMP="$(mktemp -d -p "${TMPDIR:-/tmp}" clawfedora-verified-release-XXXXXXXX)"
trap 'rm -rf -- "$TMP"' EXIT
if [[ "$KIND" == openclaw ]]; then
  ARCHIVE="$TMP/openclaw-$PIN.tgz"
else
  ARCHIVE="$TMP/ollama-linux-amd64.tar.zst"
fi
# A redirect cannot lower TLS to HTTP. Content is ALWAYS verified against the pinned digest.
curl --fail --location --silent --show-error --proto '=https' --proto-redir '=https' \
  --connect-timeout 15 --max-time 900 --output "$ARCHIVE" "$URL"
"$PYTHON" "$VERIFY" verify "$KIND" "$PIN" "$ARCHIVE"
if [[ "$KIND" == openclaw ]]; then
  command -v npm >/dev/null || { echo "npm requis pour OpenClaw" >&2; exit 127; }
  # No unreviewed installer script is executed. The core package tarball is verified.
  # npm transitive dependencies remain registry-managed and require further lockfile review.
  # npm local installs link binaries into node_modules/.bin, not prefix/bin.
  # Use user-scoped GLOBAL mode to match the executable used by all services.
  npm install --global --prefix "$HOME/.openclaw" --ignore-scripts \
    --no-audit --no-fund "$ARCHIVE"
# A verified top-level archive does not guarantee a consistent dependency tree.
  # Refuse a missing/invalid npm transitive dependency before touching services.
  if ! npm ls --global --all --prefix "$HOME/.openclaw" >/dev/null; then
    echo "Arbre de dépendances npm OpenClaw incomplet ou incohérent" >&2
    exit 2
  fi
  [[ -x "$HOME/.openclaw/bin/openclaw" ]] || { echo "CLI npm OpenClaw introuvable" >&2; exit 2; }
  TOOL="$HOME/.openclaw/bin/openclaw"
else
  command -v zstd >/dev/null || { echo "zstd requis pour Ollama" >&2; exit 127; }
  command -v sudo >/dev/null || { echo "sudo requis pour Ollama" >&2; exit 127; }
  # Extract into /usr/local (isolated from distribution-owned /usr).
  sudo tar --zstd --no-same-owner --no-same-permissions -xf "$ARCHIVE" -C /usr/local
  TOOL="/usr/local/bin/ollama"
  [[ -x "$TOOL" ]] || { echo "Binaire Ollama extrait absent" >&2; exit 2; }
  if ! id ollama >/dev/null 2>&1; then
    sudo useradd -r -s /usr/sbin/nologin -U -m -d /usr/share/ollama ollama
  fi
  # Only create the unit if none is present; never overwrite the operator's unit.
  if ! systemctl cat ollama.service >/dev/null 2>&1; then
    sudo install -d -m 0755 /etc/systemd/system
    sudo tee /etc/systemd/system/ollama.service >/dev/null <<'UNIT'
[Unit]
Description=Ollama local model server
After=network-online.target
[Service]
ExecStart=/usr/local/bin/ollama serve
User=ollama
Group=ollama
Restart=on-failure
RestartSec=3
[Install]
WantedBy=multi-user.target
UNIT
    sudo systemctl daemon-reload
  fi
fi
VERSION_TEXT="$("$TOOL" --version 2>&1)"
if [[ "$KIND" == openclaw ]]; then
  ACTUAL="$(claw_extract_openclaw_version "$VERSION_TEXT" || true)"
else
  ACTUAL="$(claw_extract_ollama_version "$VERSION_TEXT" || true)"
fi
[[ "$ACTUAL" == "$PIN" ]] || { echo "VERSION_MISMATCH: attendu=$PIN détecté=$VERSION_TEXT" >&2; exit 2; }
echo "VERIFIED_INSTALL_RESULT=PASS kind=$KIND exact_version=$PIN"
