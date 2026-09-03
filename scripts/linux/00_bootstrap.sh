#!/usr/bin/env bash
set -Eeuo pipefail

APPLY=0
ENABLE_LINGER=0
RUNTIME_ROOT="/srv/openclaw-local"
RUNTIME_MARKER=".openclaw-fedora-runtime"

usage() {
  cat <<'EOF'
Usage: 00_bootstrap.sh [--apply] [--enable-linger] [--runtime-root PATH]

Par défaut, le script est un dry-run. --apply est obligatoire pour modifier le système.
Le script peut être lancé comme utilisateur normal (recommandé) ou via sudo ; dans ce cas,
l'utilisateur appelant est conservé pour les groupes, le runtime et le lingering.
EOF
}

while (($#)); do
  case "$1" in
    --apply) APPLY=1 ;;
    --enable-linger) ENABLE_LINGER=1 ;;
    --runtime-root)
      shift
      [[ $# -gt 0 ]] || { echo "ERREUR: --runtime-root exige une valeur" >&2; exit 2; }
      RUNTIME_ROOT="$1"
      ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERREUR: argument inconnu: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"

if [[ ! -r /etc/os-release ]]; then
  echo "ERREUR: /etc/os-release absent" >&2
  exit 2
fi
# shellcheck disable=SC1091
source /etc/os-release
if [[ "${ID:-}" != "fedora" || "${VERSION_ID:-}" != "44" ]]; then
  echo "ERREUR: Fedora 44 requis; détecté ID=${ID:-?} VERSION_ID=${VERSION_ID:-?}" >&2
  exit 2
fi

TARGET_USER="${SUDO_USER:-${USER:-}}"
if [[ -z "$TARGET_USER" ]]; then
  TARGET_USER="$(id -un)"
fi
if [[ "$TARGET_USER" == "root" ]]; then
  echo "ERREUR: utilisateur cible root interdit; lancer depuis le compte utilisateur Fedora." >&2
  exit 2
fi
if ! id "$TARGET_USER" >/dev/null 2>&1; then
  echo "ERREUR: utilisateur cible introuvable: $TARGET_USER" >&2
  exit 2
fi
TARGET_GROUP="$(id -gn "$TARGET_USER")"

as_root() {
  if ((EUID == 0)); then
    "$@"
  else
    sudo "$@"
  fi
}

as_target() {
  if [[ "$(id -un)" == "$TARGET_USER" ]]; then
    "$@"
  else
    runuser -u "$TARGET_USER" -- "$@"
  fi
}

PACKAGES=(
  git curl wget rsync jq tar unzip pciutils usbutils lm_sensors
  python3 python3-pip python3-virtualenv
  gcc gcc-c++ make cmake ninja-build pkgconf-pkg-config
  vulkan-tools mesa-vulkan-drivers igt-gpu-tools
  podman
  qemu-kvm libvirt virt-install virt-manager edk2-ovmf
  shellcheck
)

printf 'BOOTSTRAP_PLAN Fedora=%s runtime=%s user=%s group=%s\n' \
  "$VERSION_ID" "$RUNTIME_ROOT" "$TARGET_USER" "$TARGET_GROUP"
printf '  packages: %s\n' "${PACKAGES[*]}"
printf '  groups: render video libvirt\n'
printf '  managed venv: %s/runtime/venv\n' "$RUNTIME_ROOT"
printf '  runtime dirs: models workspaces projects proofs benchmarks state backups\n'
printf '  managed marker: %s/%s\n' "$RUNTIME_ROOT" "$RUNTIME_MARKER"
printf '  GPU stack: xe + Mesa/Vulkan\n'
printf '  SELinux: must remain Enforcing\n'
printf '  kernel: Fedora package stays baseline; 7.2.3 is NOT installed here\n'

if ((APPLY == 0)); then
  echo "DRY_RUN=PASS -- aucune modification effectuée; relancer avec --apply pour appliquer."
  exit 0
fi

if [[ "$(getenforce 2>/dev/null || true)" != "Enforcing" ]]; then
  echo "ERREUR: SELinux doit être Enforcing avant bootstrap." >&2
  exit 2
fi

as_root dnf install -y "${PACKAGES[@]}"

for group in render video libvirt; do
  if getent group "$group" >/dev/null 2>&1; then
    as_root usermod -aG "$group" "$TARGET_USER"
  fi
done

as_root install -d -m 0750 -o "$TARGET_USER" -g "$TARGET_GROUP" "$RUNTIME_ROOT"
as_target install -d -m 0750 \
  "$RUNTIME_ROOT/runtime" \
  "$RUNTIME_ROOT/models" \
  "$RUNTIME_ROOT/workspaces" \
  "$RUNTIME_ROOT/projects" \
  "$RUNTIME_ROOT/proofs" \
  "$RUNTIME_ROOT/benchmarks" \
  "$RUNTIME_ROOT/state" \
  "$RUNTIME_ROOT/backups"
as_target touch "$RUNTIME_ROOT/$RUNTIME_MARKER"
as_target chmod 0600 "$RUNTIME_ROOT/$RUNTIME_MARKER"

VENV="$RUNTIME_ROOT/runtime/venv"
if [[ ! -x "$VENV/bin/python" ]]; then
  as_target python3 -m venv "$VENV"
fi
as_target "$VENV/bin/python" -m pip install --upgrade pip setuptools wheel
as_target "$VENV/bin/python" -m pip install -e "${REPO_ROOT}[dev]"

if systemctl list-unit-files virtqemud.socket >/dev/null 2>&1; then
  as_root systemctl enable --now virtqemud.socket
elif systemctl list-unit-files libvirtd.service >/dev/null 2>&1; then
  as_root systemctl enable --now libvirtd.service
fi

if ((ENABLE_LINGER == 1)); then
  as_root loginctl enable-linger "$TARGET_USER"
fi

echo "BOOTSTRAP_RESULT=PASS"
echo "IMPORTANT: déconnecte/reconnecte la session pour appliquer les nouveaux groupes render/video/libvirt."
