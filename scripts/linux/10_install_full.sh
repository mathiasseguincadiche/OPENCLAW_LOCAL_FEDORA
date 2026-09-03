#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
LINUX="$REPO_ROOT/scripts/linux"
# shellcheck source=scripts/linux/lib/runtime.sh
source "$LINUX/lib/runtime.sh"

APPLY=0
[[ "${1:-}" == "--apply" ]] && APPLY=1
OPENCLAW_PIN="2026.7.1-2"
RUNTIME_ROOT="$(claw_runtime_root)"

cat <<EOF
INSTALL_PLAN Fedora=44 runtime=$RUNTIME_ROOT
  1. bootstrap Fedora + GPU/KVM/Podman dependencies
  2. install/start Ollama if missing
  3. install OpenClaw $OPENCLAW_PIN if missing/wrong version
  4. explicitly provision the three nominal models
  5. deploy agent workspaces and apply OpenClaw config
  6. install/enable the OpenClaw systemd user gateway
  7. run product health check
EOF

if ((APPLY == 0)); then
  echo "INSTALL_DRY_RUN=PASS"
  exit 0
fi

if ((EUID == 0)); then
  echo "INSTALL_RESULT=FAIL run as the Fedora desktop user, not root" >&2
  exit 2
fi

"$LINUX/00_bootstrap.sh" --apply --enable-linger --runtime-root "$RUNTIME_ROOT"

if ! command -v ollama >/dev/null 2>&1; then
  tmp_ollama="$(mktemp)"
  trap 'rm -f "$tmp_ollama" "${tmp_openclaw:-}"' EXIT
  curl -fsSL --proto '=https' --tlsv1.2 https://ollama.com/install.sh -o "$tmp_ollama"
  sh "$tmp_ollama"
fi
if systemctl list-unit-files ollama.service >/dev/null 2>&1; then
  sudo systemctl enable --now ollama.service
fi

export PATH="$HOME/.openclaw/bin:$HOME/.local/bin:$PATH"
OPENCLAW_VERSION="$(openclaw --version 2>/dev/null | head -n1 || true)"
if [[ "$OPENCLAW_VERSION" != *"$OPENCLAW_PIN"* ]]; then
  tmp_openclaw="$(mktemp)"
  trap 'rm -f "${tmp_ollama:-}" "$tmp_openclaw"' EXIT
  curl -fsSL --proto '=https' --tlsv1.2 https://openclaw.ai/install-cli.sh -o "$tmp_openclaw"
  bash "$tmp_openclaw" --version "$OPENCLAW_PIN" --no-onboard
  export PATH="$HOME/.openclaw/bin:$HOME/.local/bin:$PATH"
fi

OPENCLAW_VERSION="$(openclaw --version 2>/dev/null | head -n1 || true)"
[[ "$OPENCLAW_VERSION" == *"$OPENCLAW_PIN"* ]] || {
  echo "INSTALL_RESULT=FAIL OpenClaw pin mismatch: ${OPENCLAW_VERSION:-absent}" >&2
  exit 2
}

"$LINUX/09_provision_models.sh" --apply
"$LINUX/04_configure_openclaw.sh" --apply --backend ollama-vulkan

export OPENCLAW_STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/openclaw-local"
openclaw gateway install
systemctl --user enable --now openclaw-gateway.service
openclaw gateway status --json >/dev/null

PYTHON="$(claw_python)"
if "$PYTHON" -c 'import clawfedora' >/dev/null 2>&1; then
  "$PYTHON" -m clawfedora.ops_cli --root "$REPO_ROOT" --runtime-root "$RUNTIME_ROOT" health
else
  PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
    "$PYTHON" -m clawfedora.ops_cli --root "$REPO_ROOT" --runtime-root "$RUNTIME_ROOT" health
fi

echo "INSTALL_RESULT=PASS"
