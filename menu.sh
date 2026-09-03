#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
LINUX="$REPO_ROOT/scripts/linux"
# shellcheck source=scripts/linux/lib/runtime.sh
source "$LINUX/lib/runtime.sh"

ACTION="status"
APPLY=0

usage() {
  cat <<'EOF'
OPENCLAW_LOCAL_FEDORA — centre de contrôle

Usage: ./menu.sh --action ACTION [--apply]

Actions:
  status        Valide les contrats puis effectue un audit non bloquant
  validate      Valide uniquement les contrats du dépôt
  bootstrap     Prépare Fedora; dry-run par défaut, --apply pour modifier
  audit         Audit Fedora/B580 non bloquant
  audit-strict  Gate matériel Fedora/B580 strict
  gpu           Gate B580/Vulkan/Level Zero strict
EOF
}

while (($#)); do
  case "$1" in
    --action)
      shift
      [[ $# -gt 0 ]] || { echo "ERREUR: --action exige une valeur" >&2; exit 2; }
      ACTION="$1"
      ;;
    --apply) APPLY=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERREUR: argument inconnu: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

PYTHON="$(claw_python)"
run_cli() {
  if "$PYTHON" -c 'import clawfedora' >/dev/null 2>&1; then
    "$PYTHON" -m clawfedora.cli --root "$REPO_ROOT" "$@"
  else
    PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
      "$PYTHON" -m clawfedora.cli --root "$REPO_ROOT" "$@"
  fi
}

printf '%s\n' '==============================================================================='
printf '%s\n' ' OPENCLAW_LOCAL_FEDORA — FEDORA 44 / GNOME 50 / INTEL ARC B580'
printf '%s\n' '=============================================================================='
printf '%s\n' ' Baseline kernel : Fedora officiel'
printf '%s\n' ' Kernel 7.2.3    : candidat uniquement, jamais promotion automatique'
printf '%s\n' ' GPU baseline    : Vulkan/Mesa'
printf '%s\n' ' GPU candidat    : llama.cpp SYCL/Level Zero'
printf '%s\n' ' Cloud           : explicite uniquement, jamais fallback silencieux'

case "$ACTION" in
  validate) run_cli validate ;;
  audit) "$LINUX/01_audit_host.sh" ;;
  audit-strict) "$LINUX/01_audit_host.sh" --strict ;;
  gpu) "$LINUX/02_verify_gpu.sh" ;;
  bootstrap)
    if ((APPLY == 1)); then
      "$LINUX/00_bootstrap.sh" --apply
    else
      "$LINUX/00_bootstrap.sh"
    fi
    ;;
  status)
    run_cli validate
    "$LINUX/01_audit_host.sh"
    ;;
  *) echo "ERREUR: action inconnue: $ACTION" >&2; usage >&2; exit 2 ;;
esac
