#!/usr/bin/env bash
set -Eeuo pipefail

APPLY=0
ENABLE_LINGER=0
WITH_DEV=0
WITH_KVM=0
RUNTIME_ROOT="${OPENCLAW_LOCAL_FEDORA_ROOT:-/IA/Openclaw}"
RUNTIME_MARKER=".openclaw-fedora-runtime"

usage() {
  cat <<'EOF'
Usage: 00_bootstrap.sh [--apply] [--enable-linger] [--with-dev] [--with-kvm] [--runtime-root PATH]

Par défaut, le script est un dry-run. --apply est obligatoire pour modifier le système.
Le script peut être lancé comme utilisateur normal (recommandé) ou via sudo ; dans ce cas,
l'utilisateur appelant est conservé pour les groupes, le runtime et le lingering.
EOF
}

while (($#)); do
  case "$1" in
    --apply) APPLY=1 ;;
    --enable-linger) ENABLE_LINGER=1 ;;
    --with-dev) WITH_DEV=1 ;;
    --with-kvm) WITH_KVM=1 ;;
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
# shellcheck source=scripts/linux/lib/runtime.sh
source "$REPO_ROOT/scripts/linux/lib/runtime.sh"

if [[ ! -r /etc/os-release ]]; then
  echo "ERREUR: /etc/os-release absent" >&2
  exit 2
fi
# shellcheck disable=SC1091
source /etc/os-release
if [[ "${ID:-}" != "fedora" || "${VERSION_ID:-}" != "45" ]]; then
  echo "ERREUR: Fedora 45 requis; détecté ID=${ID:-?} VERSION_ID=${VERSION_ID:-?}" >&2
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

if command -v dnf5 >/dev/null 2>&1; then
  DNF=(dnf5)
else
  DNF=(dnf)
fi

PACKAGES=(
  git curl wget rsync jq tar zstd unzip nodejs npm pciutils usbutils lm_sensors poppler-utils shellcheck gitleaks
  python3 python3-pip python3-virtualenv python3.13 python3.13-devel
  vulkan-tools mesa-vulkan-drivers
  firewalld policycoreutils-python-utils acl openssl lsof procps-ng util-linux
)

if ((WITH_DEV == 1)); then
  PACKAGES+=(gcc gcc-c++ make cmake ninja-build pkgconf-pkg-config podman)
fi
if ((WITH_KVM == 1)); then
  PACKAGES+=(qemu-kvm libvirt virt-install virt-manager edk2-ovmf)
fi

printf 'BOOTSTRAP_PLAN Fedora=%s runtime=%s user=%s group=%s\n' \
  "$VERSION_ID" "$RUNTIME_ROOT" "$TARGET_USER" "$TARGET_GROUP"
printf '  package manager: %s\n' "${DNF[*]}"
printf '  packages: %s\n' "${PACKAGES[*]}"
printf '  diagrams: native editable Draw.io XML and local SVG; no extra package\n'
printf '  groups: render video libvirt\n'
printf '  managed venv: %s/runtime/venv\n' "$RUNTIME_ROOT"
printf '  secondary mount required: /IA (before --apply)\n'
printf '  runtime dirs: models workspaces projects proofs state backups\n'
printf '  managed marker: %s/%s\n' "$RUNTIME_ROOT" "$RUNTIME_MARKER"
printf '  GPU stack: xe + Mesa/Vulkan\n'
printf '  SELinux: must remain Enforcing\n'
printf '  firewalld: installed and enabled; LLM/Gateway remain loopback\n'
printf '  development/Podman: optional with-dev=%s\n' "$WITH_DEV"
printf '  virtualization: optional with-kvm=%s\n' "$WITH_KVM"
printf '  kernel: distribution kernel kept as is; this project never builds or installs one\n'

if ((APPLY == 0)); then
  echo "DRY_RUN=PASS -- aucune modification effectuée; relancer avec --apply pour appliquer."
  exit 0
fi

# A Fedora 45 Beta/development image is not the officially released workstation.
# Do not let an early pre-release quietly become the user's live installation.
if [[ "${RELEASE_TYPE:-stable}" != "stable" ]]; then
  echo "ERREUR: Fedora 45 stable requis; RELEASE_TYPE=${RELEASE_TYPE:-inconnu}" >&2
  exit 2
fi

# A new installation is intended for GNOME 51 on Wayland, not a GNOME 50
# upgrade or a headless container. Dry-runs remain safe for CI containers.
GNOME_VERSION="$(gnome-shell --version 2>/dev/null || true)"
if [[ ! "$GNOME_VERSION" =~ ^GNOME[[:space:]]Shell[[:space:]]51([.]|$) ]]; then
  echo "ERREUR: GNOME Shell 51 requis; détecté ${GNOME_VERSION:-absent}" >&2
  exit 2
fi
if [[ "${XDG_SESSION_TYPE:-}" != "wayland" ]]; then
  echo "ERREUR: session GNOME Wayland requise (XDG_SESSION_TYPE)" >&2
  exit 2
fi

if [[ "${VARIANT_ID:-}" != "workstation" ]]; then
  echo "ERREUR: édition Fedora Workstation requise; VARIANT_ID=${VARIANT_ID:-absent}" >&2
  exit 2
fi

if [[ "$(getenforce 2>/dev/null || true)" != "Enforcing" ]]; then
  echo "ERREUR: SELinux doit être Enforcing avant bootstrap." >&2
  exit 2
fi

claw_require_storage "$RUNTIME_ROOT"
as_root "${DNF[@]}" install -y "${PACKAGES[@]}"

GROUPS_TO_ADD=(render video)
((WITH_KVM == 0)) || GROUPS_TO_ADD+=(libvirt)
for group in "${GROUPS_TO_ADD[@]}"; do
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
  "$RUNTIME_ROOT/state" \
  "$RUNTIME_ROOT/backups"
as_target touch "$RUNTIME_ROOT/$RUNTIME_MARKER"
as_target chmod 0600 "$RUNTIME_ROOT/$RUNTIME_MARKER"

# Conserver les contextes SELinux canoniques plutôt que désactiver la politique.
as_root restorecon -RF "$RUNTIME_ROOT" || true

VENV="$RUNTIME_ROOT/runtime/venv"
if [[ ! -x "$VENV/bin/python" ]]; then
  # Fedora 45 uses Python 3.15 for the OS. The optional speech engine
  # ctranslate2 currently lacks cp315 artifacts. Keep the atelier isolated in
  # a Fedora-packaged Python 3.13 venv, without changing system Python.
  as_target python3.13 -m venv "$VENV"
fi
# Keep Fedora's isolated venv pip: an unbounded upgrade of pip/setuptools/wheel
# made a reviewed bootstrap unexpectedly install newer build tooling each run.
# PEP 517 may still resolve build requirements; lock that closure separately.
as_target "$VENV/bin/python" -m pip --version
as_target "$VENV/bin/python" -c 'import sys; assert sys.version_info[:2] == (3, 13), "Python 3.13 requis"'
# Production is wheel-only: verify every artifact digest, including the
# PEP 517 editable build backend. Refuse source packages needing unpinned build
# isolation. The repository source itself is reviewed by the Git commit.
as_target "$VENV/bin/python" "$REPO_ROOT/scripts/validation/check_dependency_artifact_locks.py"
as_target "$VENV/bin/python" -m pip install --require-hashes --only-binary=:all: \
  -r "$REPO_ROOT/config/python-build-hashes.txt"
as_target "$VENV/bin/python" -m pip install --require-hashes --only-binary=:all: \
  -r "$REPO_ROOT/config/python-runtime-hashes.txt"
if ((WITH_DEV == 1)); then
  # Developer extras are intentionally out of the production hash scope.
  as_target "$VENV/bin/python" -m pip install \
    --constraint "$REPO_ROOT/config/python-runtime-constraints.txt" \
    -e "${REPO_ROOT}[dev]"
else
  # Prevent a second, unhashed resolver from pulling hidden production deps.
  as_target "$VENV/bin/python" -m pip install --no-build-isolation --no-deps -e "$REPO_ROOT"
fi

# Fail before enabling runtime services if the installed Python environment is inconsistent.
as_target "$VENV/bin/python" -m pip check
# Report any drift in the reviewed production Python dependency pins.
as_target "$VENV/bin/python" "$REPO_ROOT/scripts/validation/check_python_lock.py" --root "$REPO_ROOT"

as_root systemctl enable --now firewalld.service
if ! as_root systemctl is-active --quiet firewalld.service; then
  echo "ERREUR: firewalld n'est pas actif après bootstrap." >&2
  exit 2
fi

if ((WITH_KVM == 1)) && systemctl list-unit-files virtqemud.socket >/dev/null 2>&1; then
  as_root systemctl enable --now virtqemud.socket
elif ((WITH_KVM == 1)) && systemctl list-unit-files libvirtd.service >/dev/null 2>&1; then
  as_root systemctl enable --now libvirtd.service
fi

if ((ENABLE_LINGER == 1)); then
  as_root loginctl enable-linger "$TARGET_USER"
fi

echo "BOOTSTRAP_RESULT=PASS"
echo "SELINUX=$(getenforce)"
echo "FIREWALLD=$(as_root systemctl is-active firewalld.service)"
echo "IMPORTANT: déconnecte/reconnecte la session pour appliquer les nouveaux groupes render/video/libvirt."
