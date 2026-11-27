"""Locate canonical Notion sources and compare the evidence of their copies."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from clawfedora import notion_duplicates as duplicates
from clawfedora import notion_inventory_diff as nd
from clawfedora import notion_references as refs
from clawfedora import notion_write as nw

MAX_SUBJECTS = 100
MAX_DECLARATIONS = 1000
COMPARISONS = {"normalized_text", "ordered_direct_text", "property_type_profile"}


@dataclass
class Subject:
    comparison: str | None = None
    canonical: set[nd.Key] = field(default_factory=set)
    copies: set[nd.Key] = field(default_factory=set)
    candidates: set[nd.Key] = field(default_factory=set)


def _members(raw: object, rows: nd.Rows) -> set[nd.Key]:
    if not isinstance(raw, list) or len(raw) > MAX_DECLARATIONS:
        raise nw.NotionWriteError("liste de références déclarées invalide")
    members: set[nd.Key] = set()
    for entry in raw:
        if not isinstance(entry, dict) or set(entry) != {"category", "id"}:
            raise nw.NotionWriteError("champs d'une référence déclarée invalides")
        key = duplicates._evidence_key(entry, rows)
        if key in members:
            raise nw.NotionWriteError("référence déclarée en double")
        members.add(key)
    return members


def _subjects(raw: object, inventory: dict[str, Any], rows: nd.Rows) -> dict[str, Subject]:
    if raw is None:
        return {}
    if (
        not isinstance(raw, dict) or set(raw) != {"schema", "root_page", "structure_sha256", "topics"}
        or type(raw["schema"]) is not int or raw["schema"] != 1
        or raw["root_page"] != inventory["root_page"]
        or raw["structure_sha256"] != inventory["structure_sha256"]
        or not isinstance(raw["topics"], list) or len(raw["topics"]) > MAX_SUBJECTS
    ):
        raise nw.NotionWriteError("registre de références incompatible")
    subjects: dict[str, Subject] = {}
    assignments = 0
    for entry in raw["topics"]:
        if not isinstance(entry, dict) or set(entry) != {"key", "comparison", "canonical", "copies"}:
            raise nw.NotionWriteError("champs d'un sujet invalides")
        label = entry["key"]
        mode = entry["comparison"]
        if not isinstance(label, str) or not duplicates.LABEL.fullmatch(label) or label in subjects:
            raise nw.NotionWriteError("identifiant de sujet invalide ou répété")
        if not isinstance(mode, str) or mode not in COMPARISONS:
            raise nw.NotionWriteError("type de preuve de comparaison invalide")
        canonical = _members(entry["canonical"], rows)
        copies = _members(entry["copies"], rows)
        if canonical & copies or not (canonical or copies):
            raise nw.NotionWriteError("rôles des références incohérents")
        assignments += len(canonical) + len(copies)
        if assignments > MAX_DECLARATIONS:
            raise nw.NotionWriteError("trop de références déclarées")
        subjects[label] = Subject(mode, canonical, copies)
    return subjects


def _direct_text(rows: nd.Rows) -> dict[nd.Key, list[str]]:
    groups: dict[nd.Key, list[tuple[int, str]]] = defaultdict(list)
    for row in rows.values():
        fingerprint = row.get("text_sha256")
        if fingerprint is not None:
            parent = nd._parent_key("block", row["parent_id"], rows)
            groups[parent].append((row["position"], fingerprint))
    return {key: [value for _, value in sorted(group)] for key, group in groups.items()}


def _evidence(
    key: nd.Key, mode: str | None, rows: nd.Rows, children: dict[nd.Key, list[str]],
) -> str | list[str] | dict[str, int] | None:
    row = rows[key]
    if mode == "normalized_text" and key[0] == "block":
        fingerprint = row.get("text_sha256")
        return fingerprint if isinstance(fingerprint, str) else None
    if mode == "ordered_direct_text" and key[0] in {"page", "block"}:
        return children.get(key)
    if mode == "property_type_profile" and key[0] == "data_source":
        types = row["property_types"]
        return types if isinstance(types, dict) and types else None
    return None


def _pointers(
    bundle: dict[str, Any] | None, inventory: dict[str, Any], rows: nd.Rows,
) -> dict[nd.Key, set[nd.Key]]:
    if bundle is None:
        return {}
    captured, _, references = refs._validated_bundle(bundle, inventory["root_page"])
    if captured["structure_sha256"] != inventory["structure_sha256"]:
        raise nw.NotionWriteError("références issues d'un autre état de l'inventaire")
    pointers: dict[nd.Key, set[nd.Key]] = defaultdict(set)
    for row in references.values():
        key = row["source_category"], row["source_id"]
        if rows[key].get("type") != "link_to_page":
            continue
        target = row["kind"], row["target_id"]
        if target in rows:
            pointers[target].add(key)
    return pointers


def _proof(value: str | list[str] | dict[str, int] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, str):
        return {"sha256": value, "items": 1}
    return {"sha256": nw._digest(value), "items": len(value)}


def _comparison_status(
    authority: str, source: str | list[str] | dict[str, int] | None,
    candidate: str | list[str] | dict[str, int] | None,
) -> str:
    if authority != "declared":
        return "no_unique_authority"
    if source is None or candidate is None:
        return "insufficient_observable_evidence"
    if source == candidate:
        return "matching_observable_evidence"
    if (
        isinstance(source, list) and isinstance(candidate, list)
        and Counter(source) == Counter(candidate)
    ):
        return "different_order"
    return "divergent_observable_evidence"


def _subject_report(
    label: str, subject: Subject, rows: nd.Rows, children: dict[nd.Key, list[str]],
    links: dict[nd.Key, set[nd.Key]], protected: dict[nd.Key, list[str]],
) -> dict[str, Any]:
    count = len(subject.canonical)
    authority = "missing" if count == 0 else "declared" if count == 1 else "conflicting"
    chosen = next(iter(subject.canonical)) if count == 1 else None
    baseline = _evidence(chosen, subject.comparison, rows, children) if chosen is not None else None
    candidates = subject.candidates - subject.copies - subject.canonical
    members = subject.copies | candidates
    pointers = links.get(chosen, set()) & members if chosen is not None else set()
    assessments = []
    for key in sorted(members - pointers):
        evidence = _evidence(key, subject.comparison, rows, children)
        assessments.append({
            **nd._location(rows[key]), "role": "copy" if key in subject.copies else "candidate",
            "status": _comparison_status(authority, baseline, evidence),
            "evidence": _proof(evidence), "protected_context": protected.get(key, []),
        })
    return {
        "key": label, "authority": authority, "comparison": subject.comparison,
        "canonical": [
            {**nd._location(rows[key]), "evidence": _proof(
                _evidence(key, subject.comparison, rows, children)
            )} for key in sorted(subject.canonical)
        ],
        "comparisons": assessments,
        "pointers": [
            {**nd._location(rows[key]), "declared_as_copy": key in subject.copies}
            for key in sorted(pointers)
        ],
    }


def audit(
    snapshot: object, *, root_page: str, registry: object = None, annotations: object = None,
    reference_capture: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root_page = nw._id(root_page)
    inventory, rows = nd._validated(snapshot, root_page)
    subjects = _subjects(registry, inventory, rows)
    evidence = (
        duplicates._validate_evidence(annotations, inventory, rows) if annotations is not None else {}
    )
    for key, entry in evidence.items():
        if "truth_key" in entry:
            subjects.setdefault(entry["truth_key"], Subject()).candidates.add(key)
    if not 1 <= len(subjects) <= MAX_SUBJECTS:
        raise nw.NotionWriteError("aucun sujet à contrôler ou limite de sujets dépassée")
    children = _direct_text(rows)
    pointers = _pointers(reference_capture, inventory, rows)
    checked = {key for subject in subjects.values() for key in subject.copies | subject.candidates}
    protected = {key: duplicates._context(key, rows, evidence) for key in checked}
    result = [_subject_report(label, subject, rows, children, pointers, protected)
              for label, subject in sorted(subjects.items())]
    report = {
        "schema": 1, "root_page": root_page, "classification": "private_local_only",
        "assessment": "NATIVE_CANONICAL_SOURCES_REVIEW_REQUIRED", "remote_write": False,
        "structure_sha256": inventory["structure_sha256"],
        "registry_sha256": nw._digest(registry) if registry is not None else None,
        "annotations_sha256": nw._digest(annotations) if annotations is not None else None,
        "reference_capture_sha256": reference_capture["capture_sha256"]
        if reference_capture is not None else None,
        "counts_by_authority": dict(sorted(Counter(item["authority"] for item in result).items())),
        "counts_by_comparison": dict(sorted(Counter(
            finding["status"] for item in result for finding in item["comparisons"]
        ).items())),
        "limitations": inventory["limitations"],
        "subjects": result,
    }
    return {**report, "report_sha256": nw._digest(report)}


def _optional_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    obj = nd._load_snapshot(path)
    if not isinstance(obj, dict):
        raise nw.NotionWriteError("fichier JSON de preuve non objet")
    return obj


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Contrôler les sources de vérité d'un wiki Notion")
    parser.add_argument("--page", required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--annotations", type=Path)
    parser.add_argument("--reference-capture", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        output = nd._private_path(args.output)
        if output.exists():
            raise nw.NotionWriteError("la destination doit être un nouveau fichier")
        reference_capture = _optional_json(args.reference_capture)
        report = audit(
            nd._load_snapshot(args.inventory), root_page=args.page,
            registry=_optional_json(args.registry), annotations=_optional_json(args.annotations),
            reference_capture=reference_capture,
        )
        nd._write_private_report(output, report)
    except nw.NotionWriteError as exc:
        print(f"NOTION_SOURCE_TRUTH=REFUSED {exc}")
        return 2
    except (OSError, ValueError, RecursionError):
        print("NOTION_SOURCE_TRUTH=REFUSED source, registre ou destination illisible")
        return 2
    print("NOTION_SOURCE_TRUTH=REVIEW_REQUIRED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
