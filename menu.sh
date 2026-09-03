#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
LINUX="$REPO_ROOT/scripts/linux"
# shellcheck source=scripts/linux/lib/runtime.sh
# shellcheck disable=SC1091
source "$LINUX/lib/runtime.sh"

ACTION="status"
APPLY=0
BACKEND="ollama-vulkan"
PURGE_DATA=0

usage() {
  cat <<'EOF'
OPENCLAW_LOCAL_FEDORA — centre de contrôle

Usage: ./menu.sh --action ACTION [--apply] [--backend BACKEND] [--purge-data]

Cycle de vie:
  install                Installation complète; dry-run, --apply pour appliquer
  models                 Plan/provision des 3 modèles; --apply pour télécharger
  health                 Santé produit complète
  backup                 Sauvegarde state/projects/proofs/workspaces
  repair                 Backup + doctor + reconfiguration + health
  uninstall              Désinstallation conservatrice; --apply requis
  lifecycle-validate     Valide le contrat de cycle de vie

Plateforme et qualification:
  status                 Contrats + cycle de vie + audit non bloquant
  validate               Valide les contrats du dépôt + cycle de vie
  bootstrap              Prépare Fedora; dry-run par défaut
  audit                  Audit Fedora/B580 non bloquant
  audit-strict           Audit historique strict
  hardware-l2            Gate L2 Fedora/GNOME/hardware + preuve JSON
  hardware-l3            Gate L3 B580/xe/Mesa/Vulkan + preuve JSON
  gpu                    Alias historique du gate B580
  performance            Profil performance; dry-run, --apply pour l'activer
  agents                 Déploie les 8 workspaces agents gérés
  configure-openclaw     Configure OpenClaw; dry-run, --apply pour appliquer
  project-selftest       Cycle projet synthétique complet hors matériel
  e2e-dry-run            Plan du gate L4 OpenClaw sans appel modèle
  e2e                    Gate L4 réel
  qualification-dry-run  Valide le plan HARD-40M
  qualification          Gate L5 réel HARD-40M

Backends OpenClaw:
  ollama-vulkan          baseline
  llama-cpp-vulkan       candidat Linux
  llama-cpp-sycl         candidat Linux optionnel
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
    --purge-data) PURGE_DATA=1 ;;
    --backend)
      shift
      [[ $# -gt 0 ]] || { echo "ERREUR: --backend exige une valeur" >&2; exit 2; }
      BACKEND="$1"
      ;;
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
run_ops() {
  if "$PYTHON" -c 'import clawfedora' >/dev/null 2>&1; then
    "$PYTHON" -m clawfedora.ops_cli --root "$REPO_ROOT" "$@"
  else
    PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
      "$PYTHON" -m clawfedora.ops_cli --root "$REPO_ROOT" "$@"
  fi
}

printf '%s\n' '==============================================================================='
printf '%s\n' ' OPENCLAW_LOCAL_FEDORA — FEDORA 44 / GNOME 50 / INTEL ARC B580'
printf '%s\n' '=============================================================================='
printf '%s\n' ' Kernel baseline : Fedora officiel'
printf '%s\n' ' Kernel 7.2.3    : candidat uniquement, jamais promotion automatique'
printf '%s\n' ' GPU nominal     : xe + Mesa/Vulkan'
printf '%s\n' ' Runtime baseline: Ollama Vulkan'
printf '%s\n' ' Modèles         : Qwen 3.5 9B / Gemma 3 12B / Qwen 2.5 Coder 14B'
printf '%s\n' ' Qualification  : HARD-40M / 30 cas / suspension inhibée'
printf '%s\n' ' Cloud           : explicite uniquement, jamais fallback silencieux'

case "$ACTION" in
  lifecycle-validate) run_ops validate-lifecycle ;;
  install)
    if ((APPLY == 1)); then
      "$LINUX/10_install_full.sh" --apply
    else
      "$LINUX/10_install_full.sh"
    fi
    ;;
  models)
    if ((APPLY == 1)); then
      "$LINUX/09_provision_models.sh" --apply
    else
      "$LINUX/09_provision_models.sh"
    fi
    ;;
  health) "$LINUX/11_health.sh" ;;
  backup) "$LINUX/12_backup_restore.sh" backup ;;
  repair)
    if ((APPLY == 1)); then
      "$LINUX/13_repair.sh" --apply
    else
      "$LINUX/13_repair.sh"
    fi
    ;;
  uninstall)
    args=()
    ((APPLY == 1)) && args+=(--apply)
    ((PURGE_DATA == 1)) && args+=(--purge-data)
    "$LINUX/14_uninstall.sh" "${args[@]}"
    ;;
  validate)
    run_cli validate
    run_ops validate-lifecycle
    ;;
  audit) "$LINUX/01_audit_host.sh" ;;
  audit-strict) "$LINUX/01_audit_host.sh" --strict ;;
  hardware-l2) "$LINUX/05_hardware_gates.sh" l2 ;;
  hardware-l3) "$LINUX/05_hardware_gates.sh" l3 ;;
  gpu) "$LINUX/02_verify_gpu.sh" ;;
  performance)
    args=(--profile performance)
    ((APPLY == 1)) && args+=(--apply)
    "$LINUX/08_power_profile.sh" "${args[@]}"
    ;;
  agents) "$LINUX/03_deploy_agents.sh" ;;
  project-selftest) run_cli project selftest ;;
  e2e-dry-run) "$LINUX/06_openclaw_e2e.sh" --backend "$BACKEND" --dry-run ;;
  e2e) "$LINUX/06_openclaw_e2e.sh" --backend "$BACKEND" ;;
  qualification-dry-run) "$LINUX/07_run_qualification.sh" --dry-run ;;
  qualification) "$LINUX/07_run_qualification.sh" ;;
  configure-openclaw)
    args=(--backend "$BACKEND")
    ((APPLY == 1)) && args+=(--apply)
    "$LINUX/04_configure_openclaw.sh" "${args[@]}"
    ;;
  bootstrap)
    if ((APPLY == 1)); then
      "$LINUX/00_bootstrap.sh" --apply
    else
      "$LINUX/00_bootstrap.sh"
    fi
    ;;
  status)
    run_cli validate
    run_ops validate-lifecycle
    "$LINUX/01_audit_host.sh"
    ;;
  *) echo "ERREUR: action inconnue: $ACTION" >&2; usage >&2; exit 2 ;;
esac
