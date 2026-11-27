"""Prepare an offline, byte-bound GitHub documentary correction review."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from clawfedora import github_document_inventory as inv
from clawfedora import github_pr as pr
from clawfedora.notion_inventory_diff import _load_snapshot, _private_path, _write_private_report
from clawfedora.notion_write import NotionWriteError, _digest

INVENTORY = "GIT_DOCUMENTARY_METADATA_REVIEW_REQUIRED"
REPORTS = {
    "links": ("GIT_DOCUMENTARY_LINKS_REVIEW_REQUIRED", "findings"),
    "coherence": ("GIT_DOCUMENTARY_COHERENCE_REVIEW_REQUIRED", "checks"),
    "ci": ("GITHUB_CI_EVIDENCE_REVIEW_REQUIRED", "document_references"),
    "boundaries": ("GIT_DOCUMENTARY_BOUNDARIES_REVIEW_REQUIRED", "findings"),
}
BINDING = ("repository", "commit", "git_tree", "inventory_sha256")
LOCATION = re.compile(r"(links|coherence|ci|boundaries):([1-9][0-9]{0,3})")
LINK_FINDINGS = {"missing_path", "missing_anchor", "path_case_mismatch", "outside_repository"}
BOUNDARY_FINDINGS = {
    "identical_documents", "repeated_normalized_passage", "private_literal_in_public_document",
    "restricted_target_reference", "public_blob_matches_private_path",
}
COHERENCE_PATH_FINDINGS = {"mention_not_observed", "missing_technical_path"}
MAX_SELECTIONS = 120


def _checked(value: object, assessment: str, key: str) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or type(value.get("schema")) is not int
        or value["schema"] != 1
        or value.get("assessment") != assessment
        or value.get("classification") != inv.CLASSIFICATION
    ):
        raise inv.InventoryError("type ou classification de rapport invalide")
    digest = value.get(key)
    if digest != _digest({name: item for name, item in value.items() if name != key}):
        raise inv.InventoryError("empreinte d'un rapport invalide")
    return value


def _inventory_files(inventory: dict[str, Any]) -> dict[str, str]:
    if not isinstance(inventory.get("git_tree"), str):
        raise inv.InventoryError("arbre Git d'inventaire invalide")
    pr._valid_sha(inventory["git_tree"])
    rows = inventory.get("files")
    if not isinstance(rows, list) or len(rows) > inv.MAX_ENTRIES:
        raise inv.InventoryError("liste de fichiers d'inventaire invalide")
    seen: set[str] = set()
    editable: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise inv.InventoryError("entrée d'inventaire invalide")
        path, blob = row.get("path"), row.get("git_blob")
        if not isinstance(path, str) or path in seen or not isinstance(blob, str):
            raise inv.InventoryError("identité de fichier d'inventaire invalide")
        seen.add(path)
        pr._valid_sha(blob)
        relative, _ = inv._path(path)
        if (
            relative is not None
            and row.get("mode") == "100644"
            and row.get("category") == "documentation"
            and relative.suffix.casefold() == ".md"
            and (len(relative.parts) == 1 or relative.parts[0] == "docs")
            and not any(part.startswith(".") for part in relative.parts)
        ):
            editable[path] = blob
    return editable


def _paths(family: str, row: dict[str, Any]) -> list[object]:
    status = row.get("status")
    if family == "links" and isinstance(status, str) and status in LINK_FINDINGS:
        return [row.get("path")]
    if family == "ci" and status == "different_revision":
        return [row.get("path")]
    if family == "boundaries":
        code, locations = row.get("code"), row.get("locations")
        if isinstance(code, str) and code in BOUNDARY_FINDINGS and isinstance(locations, list):
            return [item.get("path") for item in locations if isinstance(item, dict)]
    if family == "coherence":
        if isinstance(status, str) and status in COHERENCE_PATH_FINDINGS:
            return [row.get("document")]
        if status == "version_drift" and isinstance(row.get("declarations"), list):
            return [
                item.get("path") for item in row["declarations"]
                if isinstance(item, dict) and item.get("comparison") == "version_drift"
            ]
    return []


def _findings(
    inventory: dict[str, Any], reports: Sequence[object], selections: list[str],
    edited: set[str],
) -> list[dict[str, Any]]:
    if (
        not 1 <= len(selections) <= MAX_SELECTIONS
        or len(set(selections)) != len(selections)
        or not 1 <= len(reports) <= len(REPORTS)
    ):
        raise inv.InventoryError("sélection de constats ou nombre de rapports invalide")
    indexed: dict[str, dict[str, Any]] = {}
    for value in reports:
        assessment = value.get("assessment") if isinstance(value, dict) else None
        family = next((name for name, spec in REPORTS.items() if spec[0] == assessment), "")
        if not family or family in indexed:
            raise inv.InventoryError("famille de rapport inconnue ou répétée")
        verified = _checked(value, REPORTS[family][0], "report_sha256")
        if any(key not in verified or verified[key] != inventory[key] for key in BINDING):
            raise inv.InventoryError("rapport rattaché à une autre révision ou à un autre inventaire")
        indexed[family] = verified
    used: set[str] = set()
    linked: set[str] = set()
    findings: list[dict[str, Any]] = []
    for selection in sorted(selections):
        match = LOCATION.fullmatch(selection)
        if match is None:
            raise inv.InventoryError("référence de constat invalide")
        family, number = match[1], int(match[2])
        report = indexed.get(family)
        if report is None:
            raise inv.InventoryError("rapport manquant pour un constat sélectionné")
        rows = report.get(REPORTS[family][1])
        if not isinstance(rows, list) or number > len(rows) or not isinstance(rows[number - 1], dict):
            raise inv.InventoryError("constat absent du rapport")
        paths = sorted({path for path in _paths(family, rows[number - 1])
                        if isinstance(path, str) and path in edited})
        if not paths:
            raise inv.InventoryError("constat non exploitable sur les documents proposés")
        used.add(family)
        linked.update(paths)
        findings.append({"reference": selection, "report_sha256": report["report_sha256"],
                         "edited_paths": paths})
    if linked != edited or used != indexed.keys():
        raise inv.InventoryError("chaque fichier et chaque rapport doivent étayer la proposition")
    return findings


def prepare(
    *, repo: str, base: str, base_sha: str, branch: str, changes: Path,
    inventory: object, reports: list[object], selections: list[str],
) -> dict[str, Any]:
    """Preview reviewed Markdown bytes with the existing draft publisher's manifest."""
    manifest = _checked(inventory, INVENTORY, "inventory_sha256")
    if (
        manifest.get("repository") != pr._valid_repo(repo)
        or manifest.get("commit") != pr._valid_sha(base_sha)
    ):
        raise inv.InventoryError("inventaire GitHub requis pour le dépôt et le SHA de base exacts")
    originals = _inventory_files(manifest)
    plan = pr.make_plan(
        repo=repo, base=base, base_sha=base_sha, branch=branch,
        changes=changes, allow_workflows=False,
    )
    snapshot = pr.collect_files(changes, allow_workflows=False)
    if len(snapshot) != len(plan["files"]):
        raise inv.InventoryError("dossier de proposition modifié pendant la lecture")
    edits: list[dict[str, str]] = []
    for (path, content), entry in zip(snapshot, plan["files"], strict=True):
        if path != entry["path"] or hashlib.sha256(content).hexdigest() != entry["sha256"]:
            raise inv.InventoryError("dossier de proposition modifié pendant la lecture")
        if path not in originals:
            raise inv.InventoryError("seuls les documents Markdown existants du périmètre sont admis")
        proposed = hashlib.sha1(
            f"blob {len(content)}\0".encode() + content, usedforsecurity=False,
        ).hexdigest()
        if proposed == originals[path]:
            raise inv.InventoryError("un document proposé a déjà ce contenu au SHA de base")
        edits.append({"path": path, "base_git_blob": originals[path], "proposed_git_blob": proposed})
    findings = _findings(manifest, reports, selections, {edit["path"] for edit in edits})
    body = {
        "schema": 1, "classification": inv.CLASSIFICATION,
        "assessment": "GITHUB_DOCUMENTARY_CORRECTIONS_REVIEW_REQUIRED",
        "inventory_sha256": manifest["inventory_sha256"],
        "base_git_tree": manifest["git_tree"],
        "publication_preview": plan,
        "edits": edits,
        "findings": findings,
        "limits": ["offline_preview", "upstream_reports_require_trusted_provenance",
                   "correction_effectiveness_not_checked", "human_review_required"],
    }
    return {**body, "report_sha256": _digest(body)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Préparer une revue de corrections Markdown")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--base", default="main")
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--changes", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--report", required=True, action="append", type=Path)
    parser.add_argument("--finding", required=True, action="append")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        output = _private_path(args.output)
        if output.is_relative_to(args.changes.resolve()):
            raise inv.InventoryError("le rapport privé doit rester hors du dossier à publier")
        if len(args.report) > len(REPORTS):
            raise inv.InventoryError("trop de rapports fournis")
        result = prepare(
            repo=args.repo, base=args.base, base_sha=args.base_sha, branch=args.branch,
            changes=args.changes, inventory=_load_snapshot(args.inventory),
            reports=[_load_snapshot(path) for path in args.report], selections=args.finding,
        )
        _write_private_report(output, result)
    except (inv.InventoryError, pr.PublicationError, NotionWriteError) as exc:
        print(json.dumps({"status": "refused", "message": str(exc)}, ensure_ascii=False))
        return 2
    except (OSError, RecursionError, ValueError):
        print(json.dumps({"status": "refused", "message": "Entrées ou destination invalides."}))
        return 2
    print(json.dumps({"status": "review_required", "report_sha256": result["report_sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
