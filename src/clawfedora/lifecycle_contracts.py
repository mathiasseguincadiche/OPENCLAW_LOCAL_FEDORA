from __future__ import annotations

from pathlib import Path
from typing import Any

from clawfedora.core_config import root_contract


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def validate_lifecycle_contracts(repo_root: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    failures: list[str] = []
    warnings: list[str] = []
    try:
        policy = root_contract(repo_root, "lifecycle_policy.yaml")
    except (FileNotFoundError, ValueError) as exc:
        return (f"lifecycle: {exc}",), ()

    installation = _mapping(policy.get("installation"))
    if installation.get("dry_run_by_default") is not True:
        failures.append("lifecycle: dry-run par défaut requis")
    if int(installation.get("fedora_release", 0)) != 44:
        failures.append("lifecycle: Fedora 44 requis")
    if installation.get("require_selinux_enforcing") is not True:
        failures.append("lifecycle: SELinux Enforcing requis")
    if installation.get("require_user_systemd") is not True:
        failures.append("lifecycle: systemd utilisateur requis")
    if installation.get("implicit_model_downloads") is not False:
        failures.append("lifecycle: téléchargements implicites interdits")
    if installation.get("explicit_model_provisioning") is not True:
        failures.append("lifecycle: provisioning modèles explicite requis")

    service = _mapping(policy.get("service"))
    if service.get("manager") != "systemd-user":
        failures.append("lifecycle: service systemd-user requis")
    if int(service.get("restart_prevent_exit_status", 0)) != 78:
        failures.append("lifecycle: RestartPreventExitStatus=78 requis")
    if service.get("bind") != "loopback":
        failures.append("lifecycle: Gateway loopback requis")

    backup = _mapping(policy.get("backup"))
    if backup.get("manifest_sha256") is not True:
        failures.append("lifecycle: manifest SHA-256 backup requis")
    if backup.get("restore_requires_empty_destination") is not True:
        failures.append("lifecycle: restauration vers destination vide requise")
    if backup.get("restore_overwrite_allowed") is not False:
        failures.append("lifecycle: restauration avec écrasement interdite")

    uninstall = _mapping(policy.get("uninstall"))
    for key in ("preserve_projects", "preserve_models", "preserve_proofs"):
        if uninstall.get(key) is not True:
            failures.append(f"lifecycle: uninstall.{key}=true requis")
    if uninstall.get("purge_data_requires_explicit_flag") is not True:
        failures.append("lifecycle: purge explicite obligatoire")
    if uninstall.get("never_delete_outside_runtime_root") is not True:
        failures.append("lifecycle: suppression hors runtime interdite")

    telemetry = _mapping(policy.get("telemetry"))
    if telemetry.get("local_only") is not True:
        failures.append("lifecycle: télémétrie locale uniquement")
    finops = _mapping(policy.get("finops"))
    if finops.get("local_only") is not True or finops.get("explicit_cloud_only") is not True:
        failures.append("lifecycle: FinOps local et cloud explicite requis")
    if finops.get("manual_override") is not False:
        failures.append("lifecycle: override FinOps manuel interdit")

    if not failures:
        warnings.append("cycle de vie logiciel prêt; aucune validation matérielle implicite")
    return tuple(failures), tuple(warnings)
