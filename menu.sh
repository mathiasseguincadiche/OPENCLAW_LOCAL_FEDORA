#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
LINUX="$REPO_ROOT/scripts/linux"
# shellcheck source=scripts/linux/lib/runtime.sh
# shellcheck disable=SC1091
source "$LINUX/lib/runtime.sh"

ACTION="status"
APPLY=0
PURGE_DATA=0
CONTEXT=""
VALUE=""

usage() {
  cat <<'EOF_USAGE'
Atelier IA local — Infrastructure & OPS · centre de contrôle

Usage: ./menu.sh --action ACTION [--apply] [--purge-data] [--context N] [--value N]

Sans --apply, une action qui modifie le système affiche seulement ce qu'elle ferait.

Installer et utiliser:
  install                Installation complète
  health                 Vérifier que tout fonctionne
  context-probe          Mesurer si le contexte tient sur le GPU, et la vitesse
                         (--context 8192|16384|32768 pour comparer une autre taille)
  webui-install          Installer le chat Open WebUI
  webui-seal             Fermer les inscriptions après le premier compte
  webui-start|webui-stop Démarrer ou arrêter le chat
  webui-status           État du chat et de l'atelier
  cloud-status           État du cloud optionnel, de la clé et du budget du mois
  cloud-set-key          Enregistrer la clé OpenRouter (saisie masquée)
  cloud-enable           Contrôler puis activer le cloud (--value = limite de la clé en $)
  cloud-disable          Désactiver le cloud et arrêter la passerelle
  cloud-reconcile        Enregistrer le montant réellement facturé (--value = euros)
  dashboard              Ouvrir l'atelier Projets dans ce terminal
  gaming                 Libérer le GPU pour jouer
  daily                  Reprendre les services IA

Entretenir:
  backup                 Sauvegarder l'état, les projets et les workspaces
  upgrade                Passer aux versions prévues par le dépôt
  repair                 Sauvegarde, reconfiguration et vérification
  uninstall              Désinstaller; --purge-data supprime aussi les données

Diagnostiquer:
  status                 Fichiers de configuration + audit du poste
  validate               Vérifier la cohérence des fichiers de configuration
  audit                  Audit Fedora et B580, non bloquant
  check-system           Contrôle Fedora, GNOME et matériel
  check-gpu              Contrôle B580, pilote xe et Vulkan

Étapes d'installation, utiles séparément pour dépanner:
  bootstrap              Paquets Fedora, dossiers et environnement Python
  models                 Télécharger le modèle Qwen
  agents                 Déployer les consignes des sept rôles
  configure-openclaw     Appliquer la configuration OpenClaw
EOF_USAGE
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
    --context)
      shift
      [[ $# -gt 0 ]] || { echo "ERREUR: --context exige une valeur" >&2; exit 2; }
      CONTEXT="$1"
      ;;
    --value)
      shift
      [[ $# -gt 0 ]] || { echo "ERREUR: --value exige une valeur" >&2; exit 2; }
      VALUE="$1"
      ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERREUR: argument inconnu: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

PYTHON="$(claw_python)"
run_module() {
  local module="$1"
  shift
  if "$PYTHON" -c 'import clawfedora' >/dev/null 2>&1; then
    "$PYTHON" -m "clawfedora.$module" --root "$REPO_ROOT" "$@"
  else
    PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
      "$PYTHON" -m "clawfedora.$module" --root "$REPO_ROOT" "$@"
  fi
}
run_cli() { run_module cli "$@"; }
run_ops() { run_module ops_cli "$@"; }

# Run a script, adding --apply only when it was requested.
with_apply() {
  local script="$1"
  shift
  local -a args=("$@")
  ((APPLY == 1)) && args+=(--apply)
  "$LINUX/$script" "${args[@]}"
}

case "$ACTION" in
  install) with_apply 06_install.sh ;;
  health) "$LINUX/07_health.sh" ;;
  context-probe)
    args=(--runtime-root "$(claw_runtime_root)" context-probe)
    [[ -z "$CONTEXT" ]] || args+=(--context "$CONTEXT")
    ((APPLY == 1)) && args+=(--apply)
    run_ops "${args[@]}"
    ;;
  webui-install|webui-start|webui-stop|webui-seal|webui-status)
    with_apply 13_openwebui.sh "${ACTION#webui-}"
    ;;
  cloud-status|cloud-set-key|cloud-enable|cloud-disable|cloud-reconcile)
    args=()
    [[ -z "$VALUE" ]] || args+=(--value "$VALUE")
    with_apply 14_cloud.sh "${ACTION#cloud-}" "${args[@]}"
    ;;
  dashboard) run_cli dashboard --serve ;;
  gaming) with_apply 11_daily_profile.sh gaming ;;
  daily) with_apply 11_daily_profile.sh daily ;;
  backup) "$LINUX/08_backup_restore.sh" backup ;;
  upgrade) with_apply 12_upgrade.sh ;;
  repair) with_apply 09_repair.sh ;;
  uninstall)
    args=()
    ((PURGE_DATA == 1)) && args+=(--purge-data)
    with_apply 10_uninstall.sh "${args[@]}"
    ;;
  status)
    run_cli validate
    run_ops validate-lifecycle
    "$LINUX/01_audit_host.sh"
    ;;
  validate)
    run_cli validate
    run_ops validate-lifecycle
    ;;
  audit) "$LINUX/01_audit_host.sh" ;;
  check-system) "$LINUX/04_check_hardware.sh" system ;;
  check-gpu) "$LINUX/04_check_hardware.sh" gpu ;;
  bootstrap) with_apply 00_bootstrap.sh ;;
  models) with_apply 05_provision_models.sh ;;
  agents) "$LINUX/02_deploy_agents.sh" ;;
  configure-openclaw) with_apply 03_configure_openclaw.sh ;;
  *) echo "ERREUR: action inconnue: $ACTION" >&2; usage >&2; exit 2 ;;
esac
