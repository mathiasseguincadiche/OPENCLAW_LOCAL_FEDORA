#!/usr/bin/env bash
# Read-only Fedora 45 Live USB preflight. No sudo, pip, dnf or disk mutations.
set -Eeuo pipefail
REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
if ((EUID == 0)); then
  echo "LIVE_USB_RESULT=REFUSED: ne pas lancer avec sudo/root" >&2
  exit 2
fi
command -v python3 >/dev/null || {
  echo "LIVE_USB_RESULT=REFUSED: python3 absent de la session Live" >&2
  exit 2
}
exec python3 "$REPO_ROOT/scripts/validation/live_usb_preflight.py" "$@"
