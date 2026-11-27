"""Verify whether reviewed documentary bytes and audit outcomes reached a Git snapshot."""
from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from clawfedora import github_document_boundaries as boundaries
from clawfedora import github_document_corrections as corrections
from clawfedora import github_document_inventory as inv
from clawfedora import github_pr as pr
from clawfedora.notion_inventory_diff import _load_snapshot, _private_path, _write_private_report
from clawfedora.notion_write import NotionWriteError, _digest

CONFIRMED = "confirmed"
OPEN = "still_open"
UNCERTAIN = "not_verified"
MATCHED = "exact_blob_present"


def _objects(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise inv.InventoryError("liste de constats ou de fichiers invalide")
    return value


def _strings(value: object) -> set[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise inv.InventoryError("périmètre documentaire ou couverture invalide")
    return set(value)


def _application(
    plan: dict[str, Any], before: dict[str, Any], after: dict[str, Any],
) -> dict[str, str]:
    preview = plan.get("publication_preview")
    if (
        not isinstance(preview, dict) or preview.get("draft_only") is not True
        or preview.get("repository") != before["repository"]
        or preview.get("expected_base_sha") != before["commit"]
        or plan.get("base_git_tree") != before["git_tree"]
        or plan.get("inventory_sha256") != before["inventory_sha256"]
    ):
        raise inv.InventoryError("revue rattachée à un autre dépôt ou inventaire de base")
    base_files = corrections._inventory_files(before)
    observed_files = corrections._inventory_files(after)
    edits, planned_files = _objects(plan.get("edits")), _objects(preview.get("files"))
    if not 1 <= len(edits) <= pr.MAX_FILES or len(edits) != len(planned_files):
        raise inv.InventoryError("nombre de fichiers approuvés invalide")
    application: dict[str, str] = {}
    for edit, file in zip(edits, planned_files, strict=True):
        path, initial, proposed = (edit.get(key) for key in
                                   ("path", "base_git_blob", "proposed_git_blob"))
        if (
            not isinstance(path, str) or not isinstance(proposed, str)
            or path in application or path not in base_files or path != file.get("path")
            or initial != base_files[path] or initial == proposed
        ):
            raise inv.InventoryError("identité des fichiers approuvés incohérente")
        pr._valid_sha(proposed)
        actual = observed_files.get(path)
        if actual is None:
            application[path] = "document_absent_or_ineligible"
        else:
            application[path] = MATCHED if actual == proposed else "different_blob"
    return application


def _effect(
    family: str, old: dict[str, Any], new: dict[str, Any], selected: dict[str, Any],
    paths: set[str],
) -> str:
    key = corrections.REPORTS[family][1]
    rows = _objects(new.get(key))
    if family == "coherence":
        if any(not old.get(key) or old[key] != new.get(key)
               for key in ("contract_path", "contract_blob")):
            return UNCERTAIN
        rules = [row for row in rows if row.get("id") == selected.get("id")]
        if len(rules) != 1 or rules[0].get("kind") != selected.get("kind"):
            return UNCERTAIN
        status = rules[0].get("status")
        if status == "match":
            return CONFIRMED
        if status in ("version_drift", "mention_not_observed", "missing_technical_path"):
            return OPEN
        return UNCERTAIN
    if family == "boundaries":
        coverage = new.get("coverage")
        if not isinstance(coverage, dict):
            return UNCERTAIN
        if any(paths.intersection(corrections._paths(family, row)) for row in rows):
            return OPEN
        checked = paths
        if selected["code"] == "repeated_normalized_passage":
            checked = paths | {item["path"] for item in _objects(selected.get("locations"))}
        return CONFIRMED if checked <= _strings(coverage.get("documents_checked")) else UNCERTAIN
    if family == "links":
        if _strings(old.get("scopes")) != _strings(new.get("scopes")):
            return UNCERTAIN
        inspected, blocking, accepted = "markdown_inspected", corrections.LINK_FINDINGS, set()
    else:
        inspected = "documents_inspected"
        blocking, accepted = {"different_revision", "observed_non_success"}, {"observed_success"}
    if not paths <= _strings(new.get(inspected)):
        return UNCERTAIN
    statuses = {row["status"] for row in rows if row.get("path") in paths
                and isinstance(row.get("status"), str)}
    if any(row.get("path") in paths and not isinstance(row.get("status"), str) for row in rows):
        return UNCERTAIN
    if blocking & statuses:
        return OPEN
    return CONFIRMED if statuses <= accepted else UNCERTAIN


def verify(
    *, repo: str, commit: str, expected_review: str, review: object,
    before_inventory: object, after_inventory: object, before_reports: Sequence[object],
    after_reports: Sequence[object], boundary_scopes: list[str] | None = None,
    boundary_policy: object = None,
) -> dict[str, Any]:
    """Bind observed files and audit results to the approved report and exact target SHA."""
    plan = corrections._checked(review, corrections.ASSESSMENT, "report_sha256")
    if plan["report_sha256"] != expected_review:
        raise inv.InventoryError("empreinte de revue approuvée différente")
    before = corrections._checked(before_inventory, corrections.INVENTORY, "inventory_sha256")
    after = corrections._checked(after_inventory, corrections.INVENTORY, "inventory_sha256")
    if before.get("repository") != pr._valid_repo(repo) or after.get("repository") != repo:
        raise inv.InventoryError("inventaires GitHub requis pour le dépôt sélectionné")
    initial = before.get("commit")
    if (
        not isinstance(initial, str) or after.get("commit") != pr._valid_sha(commit)
        or initial == commit
    ):
        raise inv.InventoryError("SHA de vérification incorrect ou identique à la base")
    pr._valid_sha(initial)
    application = _application(plan, before, after)
    baseline = corrections._reports(before, before_reports)
    observed = corrections._reports(after, after_reports)
    if not observed.keys() <= baseline.keys() or "boundaries" in observed:
        raise inv.InventoryError("rapport après correction inattendu pour les constats retenus")
    approval_findings = _objects(plan.get("findings"))
    references: list[str] = []
    for item in approval_findings:
        reference = item.get("reference")
        if not isinstance(reference, str):
            raise inv.InventoryError("référence de constat approuvé invalide")
        references.append(reference)
    findings = corrections._findings(baseline, references, set(application))
    if findings != approval_findings:
        raise inv.InventoryError("constats de la revue différents des rapports d'origine")

    if boundary_scopes is not None:
        if "boundaries" not in baseline:
            raise inv.InventoryError("aucun constat de frontière à revérifier")
        original = boundaries.audit_github(
            repo, before["commit"], boundary_scopes, policy=boundary_policy,
            expected_inventory=before["inventory_sha256"],
        )
        if original["report_sha256"] != baseline["boundaries"]["report_sha256"]:
            raise inv.InventoryError("l'audit de frontière ne reproduit pas la référence d'origine")
        result = boundaries.audit_github(
            repo, commit, boundary_scopes, policy=boundary_policy,
            expected_inventory=after["inventory_sha256"],
        )
        observed.update(corrections._reports(after, [result]))

    outcomes: list[dict[str, Any]] = []
    for finding in findings:
        family, index = finding["reference"].split(":")
        paths = set(finding["edited_paths"])
        latest = observed.get(family)
        status = UNCERTAIN
        if latest is not None and all(application[path] == MATCHED for path in paths):
            old = baseline[family]
            selected = old[corrections.REPORTS[family][1]][int(index) - 1]
            status = _effect(family, old, latest, selected, paths)
        outcomes.append({**finding, "status": status,
                         "observed_report_sha256": latest["report_sha256"] if latest else None})
    verified = all(value == MATCHED for value in application.values()) and all(
        item["status"] == CONFIRMED for item in outcomes
    )
    body = {
        "schema": 1, "classification": inv.CLASSIFICATION,
        "assessment": "GITHUB_DOCUMENTARY_CORRECTIONS_VERIFICATION",
        "status": "verified" if verified else "review_required",
        "repository": repo, "base_commit": before["commit"], "verified_commit": commit,
        "before_inventory_sha256": before["inventory_sha256"],
        "after_inventory_sha256": after["inventory_sha256"],
        "approved_review_sha256": expected_review,
        "files": [{"path": path, "status": status} for path, status in application.items()],
        "findings": outcomes,
        "limits": ["git_blobs_on_selected_commit", "audit_signals_only",
                   "no_pr_merge_or_ancestry_verification", "no_editorial_or_runtime_certification"],
    }
    return {**body, "report_sha256": _digest(body)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Vérifier les corrections sur un commit GitHub")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--review", required=True, type=Path)
    parser.add_argument("--review-sha256", required=True)
    parser.add_argument("--before-inventory", required=True, type=Path)
    parser.add_argument("--after-inventory", required=True, type=Path)
    parser.add_argument("--before-report", required=True, action="append", type=Path)
    parser.add_argument("--after-report", default=[], action="append", type=Path)
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--boundary-scope", action="append")
    scope.add_argument("--boundary-public-tree", action="store_true")
    parser.add_argument("--boundary-policy", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        output = _private_path(args.output)
        if output.exists():
            raise inv.InventoryError("le rapport doit être un nouveau fichier")
        if max(len(args.before_report), len(args.after_report)) > len(corrections.REPORTS):
            raise inv.InventoryError("trop de rapports fournis")
        scopes = [] if args.boundary_public_tree else args.boundary_scope
        if args.boundary_policy is not None and scopes is None:
            raise inv.InventoryError("périmètre public requis pour la politique de frontière")
        policy = _load_snapshot(args.boundary_policy) if args.boundary_policy is not None else None
        if args.boundary_policy is not None and not isinstance(policy, dict):
            raise inv.InventoryError("objet JSON de politique privée requis")
        result = verify(
            repo=args.repo, commit=args.commit, expected_review=args.review_sha256,
            review=_load_snapshot(args.review),
            before_inventory=_load_snapshot(args.before_inventory),
            after_inventory=_load_snapshot(args.after_inventory),
            before_reports=[_load_snapshot(path) for path in args.before_report],
            after_reports=[_load_snapshot(path) for path in args.after_report],
            boundary_scopes=scopes, boundary_policy=policy,
        )
        _write_private_report(output, result)
    except (inv.InventoryError, pr.PublicationError, NotionWriteError) as exc:
        print(json.dumps({"status": "refused", "message": str(exc)}, ensure_ascii=False))
        return 2
    except (OSError, RecursionError, TypeError, ValueError):
        print(json.dumps({"status": "refused", "message": "Entrées ou destination invalides."}))
        return 2
    print(json.dumps({"status": result["status"], "report_sha256": result["report_sha256"]}))
    return 0 if result["status"] == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
