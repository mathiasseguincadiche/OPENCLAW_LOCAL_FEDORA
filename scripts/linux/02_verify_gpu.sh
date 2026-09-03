#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
"$SCRIPT_DIR/01_audit_host.sh" --strict

GPU_LINE="$(lspci -Dnn | grep -Ei 'Intel.*(Arc|B580)|VGA.*Intel' | grep -i 'B580' | head -n1 || true)"
if [[ -z "$GPU_LINE" ]]; then
  echo "FAIL gpu: Intel Arc B580 introuvable via lspci" >&2
  exit 2
fi
GPU_BDF="${GPU_LINE%% *}"

echo "GPU_BDF=$GPU_BDF"
REBAR="$(lspci -s "$GPU_BDF" -vv 2>/dev/null | grep -A8 -i 'Resizable BAR' || true)"
if [[ -z "$REBAR" ]]; then
  echo "WARN rebar: capacité non lisible; vérifier le BIOS/UEFI et lspci -vv manuellement"
elif grep -Eqi 'current size: [0-9]+(GB|MB)' <<<"$REBAR"; then
  echo "PASS rebar: Resizable BAR observé"
else
  echo "WARN rebar: capacité détectée mais taille courante non confirmée"
fi

if command -v clinfo >/dev/null 2>&1; then
  clinfo -l || { echo "FAIL OpenCL/compute runtime" >&2; exit 2; }
fi

if command -v sycl-ls >/dev/null 2>&1; then
  if sycl-ls | grep -Eqi 'level_zero.*gpu.*(Arc|B580)|Arc.*B580'; then
    echo "PASS sycl: B580 exposée via Level Zero"
  else
    echo "WARN sycl: runtime présent mais B580 Level Zero non confirmée"
  fi
else
  echo "WARN sycl: non installé; Vulkan reste le baseline nominal"
fi

echo "GPU_VERIFY_RESULT=PASS"
