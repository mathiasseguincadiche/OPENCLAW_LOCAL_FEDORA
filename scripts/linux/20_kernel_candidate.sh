#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=scripts/linux/lib/runtime.sh
source "$SCRIPT_DIR/lib/runtime.sh"

APPLY=0
INSTALL=0
KERNEL_VERSION="7.2.3"
KERNEL_SHA256="8ba259e8e7b13ec6ef0941c8a39ad90b24bd4a4d6c0010ba6bafb794550ecd03"
KERNEL_URL="https://www.kernel.org/pub/linux/kernel/v7.x/linux-7.2.3.tar.xz"

usage() {
  cat <<'EOF'
Usage: 20_kernel_candidate.sh [--apply] [--install]

Dry-run par défaut.
--apply   télécharge avec HTTPS, vérifie SHA-256 et construit des RPM du kernel 7.2.3.
--install implique --apply, installe les RPM candidats puis restaure explicitement le
kernel Fedora qui était le défaut avant l'installation. Aucune promotion automatique.
EOF
}

while (($#)); do
  case "$1" in
    --apply) APPLY=1 ;;
    --install) APPLY=1; INSTALL=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERREUR: argument inconnu: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

RUNTIME_ROOT="$(claw_runtime_root)"
SOURCE_DIR="$RUNTIME_ROOT/runtime/src/kernel-$KERNEL_VERSION"
ARCHIVE="$RUNTIME_ROOT/runtime/src/linux-$KERNEL_VERSION.tar.xz"
BUILD_ROOT="$RUNTIME_ROOT/runtime/kernel/$KERNEL_VERSION"
RPM_ROOT="$BUILD_ROOT/rpms"
CURRENT_KERNEL="$(uname -r)"

cat <<EOF
L6_KERNEL_PLAN candidate=$KERNEL_VERSION current=$CURRENT_KERNEL
  source=$KERNEL_URL
  sha256=$KERNEL_SHA256
  source_dir=$SOURCE_DIR
  rpm_dir=$RPM_ROOT
  install=$INSTALL
  policy=Fedora kernel preserved + minimum 2 bootable kernels + no auto promotion
EOF

if ((APPLY == 0)); then
  echo "L6_KERNEL_DRY_RUN=PASS"
  exit 0
fi

[[ -r /etc/os-release ]] || { echo "ERREUR: /etc/os-release absent" >&2; exit 2; }
# shellcheck disable=SC1091
source /etc/os-release
[[ "${ID:-}" == "fedora" && "${VERSION_ID:-}" == "44" ]] || {
  echo "ERREUR: Fedora 44 requis pour le candidat kernel" >&2
  exit 2
}
[[ "$(getenforce 2>/dev/null || true)" == "Enforcing" ]] || {
  echo "ERREUR: SELinux doit rester Enforcing" >&2
  exit 2
}
[[ "$CURRENT_KERNEL" == *"fc44"* ]] || {
  echo "ERREUR: construire le candidat depuis la baseline kernel Fedora 44, détecté $CURRENT_KERNEL" >&2
  exit 2
}

sudo dnf install -y \
  rpm-build bc bison flex openssl-devel elfutils-libelf-devel dwarves perl rsync

mkdir -p "$(dirname -- "$ARCHIVE")" "$BUILD_ROOT" "$RPM_ROOT"
if [[ ! -f "$ARCHIVE" ]]; then
  curl -fL --proto '=https' --tlsv1.2 "$KERNEL_URL" -o "$ARCHIVE"
fi
printf '%s  %s\n' "$KERNEL_SHA256" "$ARCHIVE" | sha256sum -c -

rm -rf "$SOURCE_DIR"
mkdir -p "$SOURCE_DIR"
tar --extract --xz --file "$ARCHIVE" --strip-components=1 --directory "$SOURCE_DIR"

CONFIG="/boot/config-$CURRENT_KERNEL"
[[ -r "$CONFIG" ]] || { echo "ERREUR: config baseline absente: $CONFIG" >&2; exit 2; }
cp "$CONFIG" "$SOURCE_DIR/.config"
# Les certificats Fedora embarqués ne sont pas disponibles dans l'arbre upstream.
sed -i \
  -e 's/^CONFIG_SYSTEM_TRUSTED_KEYS=.*/CONFIG_SYSTEM_TRUSTED_KEYS=""/' \
  -e 's/^CONFIG_SYSTEM_REVOCATION_KEYS=.*/CONFIG_SYSTEM_REVOCATION_KEYS=""/' \
  "$SOURCE_DIR/.config"

make -C "$SOURCE_DIR" olddefconfig
mkdir -p "$BUILD_ROOT/rpmbuild"
export RPM_BUILD_ROOT="$BUILD_ROOT/rpmbuild"
export RPMOPTS="--define _topdir $BUILD_ROOT/rpmbuild"
make -C "$SOURCE_DIR" -j"$(nproc)" \
  LOCALVERSION=-openclaw-l6 \
  KBUILD_BUILD_USER=openclaw-local-fedora \
  KBUILD_BUILD_HOST=fedora44-b580 \
  binrpm-pkg

find "$BUILD_ROOT/rpmbuild/RPMS" -type f -name '*.rpm' -print0 | \
  while IFS= read -r -d '' rpm; do cp -f "$rpm" "$RPM_ROOT/"; done
RPM_COUNT="$(find "$RPM_ROOT" -maxdepth 1 -type f -name '*.rpm' | wc -l)"
[[ "$RPM_COUNT" -gt 0 ]] || { echo "ERREUR: aucun RPM kernel produit" >&2; exit 2; }

cat > "$BUILD_ROOT/BUILD_MANIFEST.txt" <<EOF
kernel_version=$KERNEL_VERSION
source_sha256=$KERNEL_SHA256
baseline_kernel=$CURRENT_KERNEL
built_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
rpm_count=$RPM_COUNT
automatic_promotion=false
EOF

echo "L6_KERNEL_BUILD_RESULT=PASS rpms=$RPM_COUNT path=$RPM_ROOT"
if ((INSTALL == 0)); then
  exit 0
fi

command -v grubby >/dev/null 2>&1 || { echo "ERREUR: grubby requis pour rollback du défaut" >&2; exit 2; }
DEFAULT_BEFORE="$(grubby --default-kernel)"
[[ -n "$DEFAULT_BEFORE" && -e "$DEFAULT_BEFORE" ]] || {
  echo "ERREUR: kernel Fedora par défaut introuvable avant installation" >&2
  exit 2
}
mapfile -t RPMS < <(find "$RPM_ROOT" -maxdepth 1 -type f -name '*.rpm' -print | sort)
sudo dnf install -y "${RPMS[@]}"
sudo grubby --set-default "$DEFAULT_BEFORE"
DEFAULT_AFTER="$(grubby --default-kernel)"
[[ "$DEFAULT_AFTER" == "$DEFAULT_BEFORE" ]] || {
  echo "ERREUR CRITIQUE: défaut boot divergent après installation: $DEFAULT_AFTER" >&2
  exit 2
}
BOOTABLE_COUNT="$(find /boot -maxdepth 1 -type f -name 'vmlinuz-*' | wc -l)"
[[ "$BOOTABLE_COUNT" -ge 2 ]] || {
  echo "ERREUR: moins de deux kernels bootables détectés" >&2
  exit 2
}

echo "L6_KERNEL_INSTALL_RESULT=PASS candidate=$KERNEL_VERSION default_preserved=$DEFAULT_AFTER bootable=$BOOTABLE_COUNT"
echo "ACTION MANUELLE: sélectionner temporairement 7.2.3-openclaw-l6 au boot pour les 3 runs L6; ne pas changer le défaut avant décision humaine."
