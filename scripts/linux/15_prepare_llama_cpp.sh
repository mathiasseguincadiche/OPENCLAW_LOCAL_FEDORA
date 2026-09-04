#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=scripts/linux/lib/runtime.sh
source "$SCRIPT_DIR/lib/runtime.sh"

BACKEND="vulkan"
APPLY=0
LLAMA_TAG="b10516"
LLAMA_COMMIT="b95502ba9aa0eb73a2f4fc8878d7fbe6a847a0b9"

usage() {
  cat <<'EOF'
Usage: 15_prepare_llama_cpp.sh --backend vulkan|sycl [--apply]

Dry-run par défaut. --apply clone/fixe llama.cpp sur le commit L6 exact puis construit
uniquement llama-server. SYCL reste optionnel et exige un environnement oneAPI Linux actif.
EOF
}

while (($#)); do
  case "$1" in
    --backend)
      shift
      [[ $# -gt 0 ]] || { echo "ERREUR: --backend exige une valeur" >&2; exit 2; }
      BACKEND="$1"
      ;;
    --apply) APPLY=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERREUR: argument inconnu: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

case "$BACKEND" in
  vulkan|sycl) ;;
  *) echo "ERREUR: backend L6 invalide: $BACKEND" >&2; exit 2 ;;
esac

RUNTIME_ROOT="$(claw_runtime_root)"
SOURCE_ROOT="$RUNTIME_ROOT/runtime/src/llama.cpp"
BUILD_ROOT="$RUNTIME_ROOT/runtime/llama.cpp/$BACKEND"

printf 'L6_LLAMA_PLAN backend=%s tag=%s commit=%s\n' "$BACKEND" "$LLAMA_TAG" "$LLAMA_COMMIT"
printf '  source=%s\n  build=%s\n' "$SOURCE_ROOT" "$BUILD_ROOT"
printf '  network=explicit-prepare-only model_downloads=never\n'
if [[ "$BACKEND" == "vulkan" ]]; then
  printf '  Fedora deps=vulkan-loader-devel glslc libshaderc-devel\n'
else
  printf '  toolchain=/opt/intel/oneapi/setvars.sh + icx/icpx (required, not auto-installed)\n'
fi

if ((APPLY == 0)); then
  echo "L6_LLAMA_PREPARE_DRY_RUN=PASS"
  exit 0
fi

command -v git >/dev/null 2>&1 || { echo "ERREUR: git requis" >&2; exit 127; }
command -v cmake >/dev/null 2>&1 || { echo "ERREUR: cmake requis" >&2; exit 127; }
command -v ninja >/dev/null 2>&1 || { echo "ERREUR: ninja requis" >&2; exit 127; }

if [[ "$BACKEND" == "vulkan" ]]; then
  if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    source /etc/os-release
  fi
  [[ "${ID:-}" == "fedora" && "${VERSION_ID:-}" == "44" ]] || {
    echo "ERREUR: build Vulkan nominal supporté sur Fedora 44 uniquement" >&2
    exit 2
  }
  sudo dnf install -y vulkan-loader-devel glslc libshaderc-devel
else
  if [[ -r /opt/intel/oneapi/setvars.sh ]]; then
    set +u
    # shellcheck disable=SC1091
    source /opt/intel/oneapi/setvars.sh >/dev/null
    set -u
  fi
  command -v icx >/dev/null 2>&1 || {
    echo "ERREUR: SYCL optionnel: icx absent. Installer Intel oneAPI/Deep Learning Essentials puis relancer." >&2
    exit 3
  }
  command -v icpx >/dev/null 2>&1 || {
    echo "ERREUR: SYCL optionnel: icpx absent. Installer Intel oneAPI/Deep Learning Essentials puis relancer." >&2
    exit 3
  }
fi

mkdir -p "$(dirname -- "$SOURCE_ROOT")" "$BUILD_ROOT"
if [[ ! -d "$SOURCE_ROOT/.git" ]]; then
  git clone --filter=blob:none https://github.com/ggml-org/llama.cpp.git "$SOURCE_ROOT"
fi

git -C "$SOURCE_ROOT" remote set-url origin https://github.com/ggml-org/llama.cpp.git
git -C "$SOURCE_ROOT" fetch --force --tags origin "$LLAMA_TAG"
git -C "$SOURCE_ROOT" checkout --detach "$LLAMA_COMMIT"
ACTUAL_COMMIT="$(git -C "$SOURCE_ROOT" rev-parse HEAD)"
[[ "$ACTUAL_COMMIT" == "$LLAMA_COMMIT" ]] || {
  echo "ERREUR: llama.cpp SHA divergent: $ACTUAL_COMMIT" >&2
  exit 2
}

CMAKE_ARGS=(
  -S "$SOURCE_ROOT"
  -B "$BUILD_ROOT"
  -G Ninja
  -DCMAKE_BUILD_TYPE=Release
  -DLLAMA_CURL=OFF
  -DLLAMA_BUILD_SERVER=ON
  -DGGML_BUILD_TESTS=OFF
  -DGGML_BUILD_EXAMPLES=OFF
)
if [[ "$BACKEND" == "vulkan" ]]; then
  CMAKE_ARGS+=( -DGGML_VULKAN=ON )
else
  CMAKE_ARGS+=(
    -DGGML_SYCL=ON
    -DGGML_SYCL_F16=ON
    -DGGML_SYCL_TARGET=INTEL
    -DCMAKE_C_COMPILER=icx
    -DCMAKE_CXX_COMPILER=icpx
  )
fi

cmake "${CMAKE_ARGS[@]}"
cmake --build "$BUILD_ROOT" --config Release --target llama-server -j "$(nproc)"
SERVER="$BUILD_ROOT/bin/llama-server"
[[ -x "$SERVER" ]] || { echo "ERREUR: llama-server construit absent: $SERVER" >&2; exit 2; }
"$SERVER" --version >/dev/null
printf '%s\n' "$LLAMA_COMMIT" > "$BUILD_ROOT/OPENCLAW_BUILD_COMMIT"
echo "L6_LLAMA_PREPARE_RESULT=PASS backend=$BACKEND server=$SERVER"
