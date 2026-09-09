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
Usage: 15_prepare_llama_cpp.sh [--backend vulkan] [--apply]

Dry-run par défaut. --apply clone/fixe llama.cpp sur le commit L6 exact puis construit
uniquement llama-server avec le backend Vulkan Fedora/Mesa.
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

[[ "$BACKEND" == "vulkan" ]] || {
  echo "ERREUR: seul le backend Vulkan est supporté" >&2
  exit 2
}

RUNTIME_ROOT="$(claw_runtime_root)"
SOURCE_ROOT="$RUNTIME_ROOT/runtime/src/llama.cpp"
BUILD_ROOT="$RUNTIME_ROOT/runtime/llama.cpp/vulkan"

printf 'L6_LLAMA_PLAN backend=vulkan tag=%s commit=%s\n' "$LLAMA_TAG" "$LLAMA_COMMIT"
printf '  source=%s\n  build=%s\n' "$SOURCE_ROOT" "$BUILD_ROOT"
printf '  Fedora deps=vulkan-loader-devel glslc libshaderc-devel\n'
printf '  network=explicit-prepare-only model_downloads=never\n'

if ((APPLY == 0)); then
  echo "L6_LLAMA_PREPARE_DRY_RUN=PASS"
  exit 0
fi

command -v git >/dev/null 2>&1 || { echo "ERREUR: git requis" >&2; exit 127; }
command -v cmake >/dev/null 2>&1 || { echo "ERREUR: cmake requis" >&2; exit 127; }
command -v ninja >/dev/null 2>&1 || { echo "ERREUR: ninja requis" >&2; exit 127; }

if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  source /etc/os-release
fi
[[ "${ID:-}" == "fedora" && "${VERSION_ID:-}" == "44" ]] || {
  echo "ERREUR: build Vulkan supporté sur Fedora 44 uniquement" >&2
  exit 2
}
sudo dnf install -y vulkan-loader-devel glslc libshaderc-devel

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
  -DGGML_VULKAN=ON
)

cmake "${CMAKE_ARGS[@]}"
cmake --build "$BUILD_ROOT" --config Release --target llama-server -j "$(nproc)"
SERVER="$BUILD_ROOT/bin/llama-server"
[[ -x "$SERVER" ]] || { echo "ERREUR: llama-server construit absent: $SERVER" >&2; exit 2; }
"$SERVER" --version >/dev/null
printf '%s\n' "$LLAMA_COMMIT" > "$BUILD_ROOT/OPENCLAW_BUILD_COMMIT"
echo "L6_LLAMA_PREPARE_RESULT=PASS backend=vulkan server=$SERVER"
