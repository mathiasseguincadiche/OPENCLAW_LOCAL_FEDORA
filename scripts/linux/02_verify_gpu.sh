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
  echo "WARN rebar: capacité non lisible; vérifier le firmware et lspci -vv manuellement"
elif grep -Eqi 'current size: [0-9]+(GB|MB)' <<<"$REBAR"; then
  echo "PASS rebar: Resizable BAR observé"
else
  echo "WARN rebar: capacité détectée mais taille courante non confirmée"
fi

if ! vulkaninfo --summary 2>&1 | grep -Eqi 'Intel|B580'; then
  echo "FAIL vulkan: la B580 n'est pas exposée correctement par Mesa/Vulkan" >&2
  exit 2
fi

echo "PASS vulkan: Intel Arc B580 exposée par Mesa/Vulkan"
echo "GPU_VERIFY_RESULT=PASS"
