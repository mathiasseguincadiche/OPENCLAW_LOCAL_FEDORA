"""Build a review-only rationalization plan from evidence in one Notion wiki."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from clawfedora import notion_duplicates as dup
from clawfedora import notion_inventory_diff as nd
from clawfedora import notion_references as refs
from clawfedora import notion_source_truth as truth
from clawfedora import notion_write as nw

MAX_ISSUES = 1500
SEVERITY = {"high": 0, "medium": 1, "low": 2}


@dataclass(frozen=True)
class Rule:
    severity: str
    action: str
    impact: str
    check: str


DUPLICATE = Rule(
    "low", "Examiner les usages et proposer un renvoi si les contenus remplissent le même rôle.",
    "Navigation et accès aux explications.",
    "Vérifier le parcours du lecteur et la présence des répétitions utiles.",
)
PROTECTED = Rule(
    "low", "Documenter le rôle de la répétition ou du bloc protégé.",
    "Compréhension du lecteur et conservation de l'historique.",
    "Vérifier les rappels, archives, blocs synchronisés et sections d'installation concernés.",
)
LINK_REPAIR = Rule(
    "high", "Identifier la destination correcte et préparer une correction ciblée du lien.",
    "Accès à la destination et continuité du parcours.",
    "Contrôler la destination, l'ancre et les autres liens du bloc concerné.",
)
LINK_REVIEW = Rule(
    "medium", "Vérifier la destination et les droits existants avec l'opérateur.",
    "Accessibilité et visibilité de la ressource.",
    "Relever le résultat de la vérification et contrôler les permissions existantes.",
)
LINK_TEMPORARY = Rule(
    "low", "Relire les métadonnées de la pièce jointe pour vérifier sa disponibilité.",
    "Accès à la pièce jointe.",
    "Vérifier la disponibilité du fichier et la conservation de la pièce jointe.",
)
LINK_RULES = {
    "broken_confirmed_public": LINK_REPAIR, "broken_confirmed_manual": LINK_REPAIR,
    "obsolete_confirmed": LINK_REPAIR, "block_anchor_page_mismatch": LINK_REPAIR,
    "access_restricted": LINK_REVIEW, "absence_unconfirmed": LINK_REVIEW,
    "outside_observed_inventory": LINK_REVIEW, "network_or_server_limited": LINK_REVIEW,
    "http_redirect_unverified": LINK_REVIEW, "temporary_url_expired": LINK_TEMPORARY,
}
AUTHORITY = Rule(
    "high", "Faire désigner une source de vérité pour le sujet avec l'opérateur.",
    "Référence utilisée pour les mises à jour futures.",
    "Vérifier la désignation dans le registre et la conservation des autres versions.",
)
DIVERGENCE = Rule(
    "medium", "Relire l'écart et préparer un alignement ciblé si la variante est involontaire.",
    "Contenu ou progression des copies déclarées.",
    "Vérifier l'écart ciblé et les variantes pédagogiques à préserver.",
)
CANDIDATE = Rule(
    "low", "Qualifier le rôle du candidat et compléter les preuves avant de choisir une correction.",
    "Périmètre de comparaison et interprétation de l'écart.",
    "Vérifier le rôle, la couverture et les limites du comparateur.",
)
POINTER = Rule(
    "low", "Corriger le rôle dans le registre après avoir vérifié la destination du renvoi.",
    "Exactitude du registre des sources et copies.",
    "Vérifier le renvoi et sa classification dans le registre.",
)
TRUTH_STATUSES = {
    "divergent_observable_evidence", "different_order", "insufficient_observable_evidence",
}
ROLLBACK = [
    "Avant toute modification future, conserver le contenu complet, les pièces jointes "
    "et les éléments nécessaires à la restauration de l'ordre et des liens.",
    "Si la relecture échoue, interrompre la série, restaurer les éléments concernés "
    "à partir de cette référence et vérifier de nouveau l'état observé.",
]
PRESERVE = [
    "Conserver les procédures d'installation, rappels de sécurité, répétitions pédagogiques, "
    "archives et blocs synchronisés.",
    "Préserver les bases, leurs données, la navigation et les autorisations hors du "
    "périmètre approuvé.",
]
APPROVALS = [
    "Faire valider le constat, le périmètre exact et les contenus à préserver par l'opérateur.",
    "Pour toute écriture ultérieure, obtenir une approbation distincte de l'opérateur "
    "et utiliser un mécanisme d'écriture contrôlé adapté à l'action.",
]
REGRESSION = [
    "Comparer les captures réalisées avant et après une éventuelle modification.",
    "Vérifier les écarts attendus, les liens, l'ordre, les sources de données "
    "et les éléments protégés.",
]


def _key(row: dict[str, Any]) -> nd.Key:
    return row["category"], row["id"]


def _issue(
    root: str, report: dict[str, Any], signal: str, rule: Rule, locations: list[dict[str, Any]],
    detail: dict[str, Any],
) -> dict[str, Any]:
    targets = sorted({(row["category"], row["id"]) for row in locations})
    return {
        "issue_id": nw._digest([
            root, report["assessment"], signal, targets, detail.get("subject"),
            detail.get("reference_id"), detail.get("signal"),
        ]),
        "signal": signal, "severity": rule.severity,
        "locations": locations,
        "proof": {"assessment": report["assessment"], "report_sha256": report["report_sha256"],
                  "observation": detail},
        "proposed_action": rule.action, "impact": rule.impact,
        "follow_up_check": rule.check,
    }


def _duplicate_issues(root: str, report: dict[str, Any]) -> list[dict[str, Any]]:
    issues = []
    for group in report["findings"]:
        rule = PROTECTED if group["status"] == "protected_context" else DUPLICATE
        detail = {key: value for key, value in group.items() if key != "objects"}
        issues.append(_issue(
            root, report, f"duplicate_{group['family']}", rule, group["objects"], detail,
        ))
    return issues


def _reference_issues(
    root: str, report: dict[str, Any], rows: nd.Rows,
) -> list[dict[str, Any]]:
    issues = []
    for entry in report["references"]:
        status = entry["status"]
        if status not in LINK_RULES:
            continue
        location = nd._location(rows[entry["source_category"], entry["source_id"]])
        detail = {
            key: entry[key] for key in ("reference_id", "slot", "index", "kind", "status",
                                        "target_id", "url_sha256", "page_id", "expires_at",
                                        "observation")
        }
        issues.append(_issue(root, report, status, LINK_RULES[status], [location], detail))
    return issues


def _truth_issues(
    root: str, report: dict[str, Any], rows: nd.Rows,
) -> list[dict[str, Any]]:
    issues = []
    for subject in report["subjects"]:
        canonical = subject["canonical"]
        context = {"subject": subject["key"], "authority": subject["authority"],
                   "comparison": subject["comparison"], "canonical": canonical}
        if subject["authority"] != "declared":
            objects = canonical + subject["comparisons"] or [nd._location(rows["page", root])]
            issues.append(_issue(root, report, f"authority_{subject['authority']}",
                                 AUTHORITY, objects, context))
        for result in subject["comparisons"]:
            status = result["status"]
            if status not in TRUTH_STATUSES:
                continue
            rule = DIVERGENCE if (
                result["role"] == "copy" and status != "insufficient_observable_evidence"
            ) else CANDIDATE
            detail = {**context, "result": result}
            issues.append(_issue(root, report, status, rule, [result], detail))
        for pointer in subject["pointers"]:
            if pointer["declared_as_copy"]:
                issues.append(_issue(root, report, "pointer_declared_as_copy", POINTER,
                                     [pointer], context))
    return issues


def _complete_issue(
    issue: dict[str, Any], rows: nd.Rows, protected: dict[nd.Key, list[str]],
) -> dict[str, Any]:
    locations = [nd._location(rows[_key(row)]) for row in issue["locations"]]
    proof = issue["proof"]["observation"]
    canonical = proof.get("canonical", [])
    keys = {_key(row) for row in locations + canonical}
    preserve = [{**nd._location(rows[key]), "context": protected.get(key, []),
                 "sha256": rows[key]["sha256"]} for key in sorted(keys)]
    return {
        **issue, "locations": locations, "content_to_preserve": preserve,
        "preconditions": [
            "Vérifier que les identifiants et empreintes correspondent à une nouvelle lecture.",
            "Confirmer le constat et définir la modification attendue avec l'opérateur.",
        ],
        "required_approvals": APPROVALS,
        "rollback": ROLLBACK,
        "non_regression_checks": [issue["follow_up_check"], *REGRESSION],
    }


def _comparison(before: object, current: object, root: str) -> dict[str, Any] | None:
    if before is None:
        return None
    report = nd.compare(before, current, root_page=root)
    return {
        "report_sha256": report["report_sha256"],
        "before_structure_sha256": report["before"]["structure_sha256"],
        "counts": {key: len(report[key]) for key in ("added", "absent", "modified", "reordered")},
        "use": "contexte de comparaison à examiner avant tout changement",
    }


def _audit_links(
    bundle: dict[str, Any], inventory: dict[str, Any], root: str,
    observations: object, as_of: datetime | None,
) -> dict[str, Any]:
    captured = bundle.get("inventory")
    if (
        not isinstance(captured, dict)
        or captured.get("structure_sha256") != inventory["structure_sha256"]
    ):
        raise nw.NotionWriteError("capture des liens issue d'un autre état d'inventaire")
    when = as_of if as_of is not None else refs._utc(captured.get("captured_at"))
    return refs.audit(bundle, root_page=root, as_of=when, observations=observations)


def plan(
    snapshot: object, *, root_page: str, before: object = None, annotations: object = None,
    registry: object = None, reference_capture: dict[str, Any] | None = None,
    observations: object = None, as_of: datetime | None = None,
) -> dict[str, Any]:
    root = nw._id(root_page)
    inventory, rows = nd._validated(snapshot, root)
    drafts = []
    evidence_reports: dict[str, Any] = {}
    duplicates = dup.analyze(snapshot, root_page=root, evidence=annotations)
    drafts.extend(_duplicate_issues(root, duplicates))
    evidence_reports["duplicates"] = {"report_sha256": duplicates["report_sha256"],
                                      "coverage": duplicates["coverage"]}
    protected = {_key(row): row["context"] for row in duplicates["protected_objects"]}
    if reference_capture is not None:
        links = _audit_links(reference_capture, inventory, root, observations, as_of)
        drafts.extend(_reference_issues(root, links, rows))
        evidence_reports["references"] = {key: links[key] for key in (
            "report_sha256", "capture_sha256", "as_of", "counts_by_status", "audit_limitations",
        )}
    elif observations is not None or as_of is not None:
        raise nw.NotionWriteError("capture des liens requise pour les observations ou leur date")
    if registry is not None or duplicates["coverage"]["annotated_fields"].get("truth_key"):
        sources = truth.audit(snapshot, root_page=root, registry=registry,
                              annotations=annotations, reference_capture=reference_capture)
        drafts.extend(_truth_issues(root, sources, rows))
        evidence_reports["sources"] = {key: sources[key] for key in (
            "report_sha256", "counts_by_authority", "counts_by_comparison",
        )}
    if len(drafts) > MAX_ISSUES:
        raise nw.NotionWriteError("trop de constats dans le périmètre du plan")
    ordered = sorted(drafts, key=lambda issue: (SEVERITY[issue["severity"]], issue["issue_id"]))
    ids = [issue["issue_id"] for issue in ordered]
    if len(set(ids)) != len(ids):
        raise nw.NotionWriteError("identifiants de constats répétés")
    issues = [_complete_issue(issue, rows, protected) for issue in ordered]
    result = {
        "schema": 1, "root_page": root, "classification": "private_local_only",
        "assessment": "NATIVE_RATIONALIZATION_PLAN_REVIEW_REQUIRED",
        "remote_write": False, "executable": False,
        "inventory_structure_sha256": inventory["structure_sha256"],
        "inventory_captured_at": inventory["captured_at"],
        "evidence_reports": evidence_reports,
        "baseline_comparison": _comparison(before, snapshot, root),
        "inventory_limitations": inventory["limitations"],
        "protected_objects": duplicates["protected_objects"],
        "preservation_requirements": PRESERVE,
        "counts_by_severity": dict(sorted(Counter(issue["severity"] for issue in issues).items())),
        "issues": issues,
    }
    report = {**result, "plan_sha256": nw._digest(result)}
    if len(json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")) + 1 > nd.MAX_BYTES:
        raise nw.NotionWriteError("plan trop volumineux")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Préparer un plan de rationalisation Notion privé")
    parser.add_argument("--page", required=True)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--before", type=Path)
    parser.add_argument("--annotations", type=Path)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--reference-capture", type=Path)
    parser.add_argument("--observations", type=Path)
    parser.add_argument("--as-of")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        output = nd._private_path(args.output)
        if output.exists():
            raise nw.NotionWriteError("la destination doit être un nouveau fichier")
        capture = truth._optional_json(args.reference_capture)
        current = truth._optional_json(args.inventory)
        if current is None and capture is not None:
            current = capture.get("inventory")
        if current is None:
            raise nw.NotionWriteError("inventaire ou capture des liens requis")
        report = plan(
            current, root_page=args.page, before=truth._optional_json(args.before),
            annotations=truth._optional_json(args.annotations),
            registry=truth._optional_json(args.registry), reference_capture=capture,
            observations=truth._optional_json(args.observations),
            as_of=refs._utc(args.as_of) if args.as_of is not None else None,
        )
        nd._write_private_report(output, report)
    except nw.NotionWriteError as exc:
        print(f"NOTION_RATIONALIZATION=REFUSED {exc}")
        return 2
    except (OSError, ValueError, RecursionError):
        print("NOTION_RATIONALIZATION=REFUSED entrée ou destination illisible")
        return 2
    print(f"NOTION_RATIONALIZATION=REVIEW_REQUIRED constats={len(report['issues'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
