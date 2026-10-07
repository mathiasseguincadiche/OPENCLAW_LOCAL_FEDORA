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
Atelier IA local — Infrastructure & OPS · centre de contrôle

Usage: ./menu.sh --action ACTION [--apply] [--backend BACKEND] [--purge-data]

Usage quotidien:
  install                Installation complète; dry-run, --apply pour appliquer
  health                 Santé produit complète
  context-probe          Mesurer si le contexte quotidien tient sur le GPU; --apply requis
  gaming                 Libérer le GPU pour jouer; --apply pour arrêter les services
  daily                  Reprendre les services IA; --apply obligatoire
  dashboard              Tableau de bord local : projets, recherche et ressources
  webui-install          Installer Open WebUI slim personnel; --apply requis
  webui-start|webui-stop  Démarrer/arrêter les discussions; --apply requis
  webui-seal             Fermer les inscriptions après le premier compte; --apply requis
  webui-status           État des interfaces locales
  backup                 Sauvegarde state/projects/proofs/workspaces
  upgrade                Migration sauvegardée vers les versions du dépôt; --apply requis
  repair                 Backup + doctor + reconfiguration + health
  uninstall              Désinstallation conservatrice; --apply requis

Diagnostic:
  status                 Contrats + cycle de vie + audit non bloquant
  validate               Valide tous les contrats + cycle de vie
  audit                  Audit Fedora/B580 non bloquant
  audit-strict           Audit historique strict
  hardware-l2            Contrôle Fedora/GNOME/matériel + preuve JSON
  hardware-l3            Contrôle B580/xe/Mesa/Vulkan + preuve JSON
  gpu                    Alias historique du contrôle B580
  models                 Plan/provision de Qwen quotidien; --apply pour télécharger
  bootstrap              Prépare Fedora; dry-run par défaut
  agents                 Déploie les 7 workspaces agents gérés
  configure-openclaw     Configure OpenClaw; dry-run, --apply pour appliquer
  lifecycle-validate     Valide le contrat de cycle de vie
  project-selftest       Cycle projet synthétique complet hors matériel

Expérimental — facultatif, inutile pour se servir de l'atelier au quotidien:
  performance            Profil performance; dry-run, --apply pour l'activer
  e2e-dry-run            Plan du gate L4 OpenClaw sans appel modèle
  e2e                    Gate L4 réel
  qualification-dry-run  Valide le plan HARD-40M
  qualification          Gate L5 réel HARD-40M
  challenger-model       Plan/provision Granite challenger hors routage; --apply explicite
  golden-dry-run         Valide le plan L7 sans exécuter les projets
  golden                 Exécute les 5 Golden Projects + projet représentatif
  release-readiness-dry-run  Valide le framework L8 sans lire les preuves réelles
  release-readiness      Agrège et revalide les preuves L0-L7; jamais d'approbation automatique
  L'approbation L8 n'est volontairement pas exposée comme action menu.
  Utiliser clawfedora-l8 approve avec --report, --approver et --acknowledge-v1.

Backends OpenClaw:
  ollama-vulkan          baseline
  llama-cpp-vulkan       candidat Linux expérimental
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
run_golden() {
  if "$PYTHON" -c 'import clawfedora' >/dev/null 2>&1; then
    "$PYTHON" -m clawfedora.golden_cli --root "$REPO_ROOT" "$@"
  else
    PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
      "$PYTHON" -m clawfedora.golden_cli --root "$REPO_ROOT" "$@"
  fi
}
run_l6() {
  if "$PYTHON" -c 'import clawfedora' >/dev/null 2>&1; then
    "$PYTHON" -m clawfedora.optimization_cli --root "$REPO_ROOT" "$@"
  else
    PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
      "$PYTHON" -m clawfedora.optimization_cli --root "$REPO_ROOT" "$@"
  fi
}
run_l8() {
  if "$PYTHON" -c 'import clawfedora' >/dev/null 2>&1; then
    "$PYTHON" -m clawfedora.release_readiness_cli --root "$REPO_ROOT" "$@"
  else
    PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
      "$PYTHON" -m clawfedora.release_readiness_cli --root "$REPO_ROOT" "$@"
  fi
}

printf '%s\n' '=============================================================================='
printf '%s\n' ' OPENCLAW_LOCAL_FEDORA — FEDORA 44 / GNOME 50 / INTEL ARC B580'
printf '%s\n' '=============================================================================='
printf '%s\n' ' Noyau           : celui de la distribution, jamais modifié par ce projet'
printf '%s\n' ' GPU nominal     : xe + Mesa/Vulkan'
printf '%s\n' ' Runtime baseline: Ollama Vulkan'
printf '%s\n' ' Modèle quotidien: Qwen 3.5 9B (exactement 1), contexte 32768, sortie 4096'
printf '%s\n' ' Expérimental    : Gemma 4 12B / Ministral 3 14B Reasoning / Granite 4.2 8B hors routage'
printf '%s\n' ' Cloud           : aucun routage LLM cloud nominal, jamais fallback silencieux'

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
  upgrade)
    if ((APPLY == 1)); then "$LINUX/22_upgrade_daily.sh" --apply; else "$LINUX/22_upgrade_daily.sh"; fi
    ;;
  gaming)
    if ((APPLY == 1)); then "$LINUX/21_daily_profile.sh" gaming --apply; else "$LINUX/21_daily_profile.sh" gaming; fi
    ;;
  daily)
    if ((APPLY == 1)); then "$LINUX/21_daily_profile.sh" daily --apply; else "$LINUX/21_daily_profile.sh" daily; fi
    ;;
  health) "$LINUX/11_health.sh" ;;
  context-probe)
    args=(--runtime-root "$(claw_runtime_root)" context-probe)
    ((APPLY == 1)) && args+=(--apply)
    run_ops "${args[@]}"
    ;;
  dashboard) run_cli dashboard --serve ;;
  webui-install|webui-start|webui-stop|webui-seal|webui-status)
    args=("${ACTION#webui-}")
    ((APPLY == 1)) && args+=(--apply)
    "$LINUX/23_openwebui.sh" "${args[@]}"
    ;;
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
  challenger-model)
    args=(provision-challenger)
    ((APPLY == 1)) && args+=(--apply)
    run_l6 "${args[@]}"
    ;;
  golden-dry-run) run_golden --dry-run ;;
  golden) run_golden ;;
  release-readiness-dry-run) run_l8 dry-run ;;
  release-readiness) run_l8 check ;;
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
