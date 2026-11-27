"""Find duplicate candidates in a validated, private Notion inventory."""
from __future__ import annotations

import argparse
import re
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any

from clawfedora import notion_inventory_diff as nd
from clawfedora import notion_native_inventory as ni
from clawfedora import notion_write as nw

MAX_ANNOTATIONS = 300
MAX_TEXTS = 80
MAX_TEXT_LENGTH = 4000
MIN_DISTINCT_WORDS = 6
MIN_SIMILARITY = 65
WORD = re.compile(r"[^\W_]+")
LABEL = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
PROTECTED = {"archive", "installation", "security_reminder", "synced_copy", "teaching_repetition"}
LABEL_FIELDS = {
    "semantic_key": "semantic",
    "function_key": "functional",
    "organization_key": "organizational",
    "truth_key": "source_of_truth",
}
FIELDS = {
    "context", "text", "navigation_target", "diagram_sha256", *LABEL_FIELDS,
}
Evidence = dict[nd.Key, dict[str, Any]]
Buckets = dict[tuple[str, str, str], list[nd.Key]]


def _evidence_key(raw: dict[str, Any], rows: nd.Rows) -> nd.Key:
    category = raw.get("category")
    ident = raw.get("id")
    if not isinstance(category, str) or not nd._matches(ident, nd.IDENTIFIER):
        raise nw.NotionWriteError("identité d'annotation invalide")
    key: nd.Key = (category, ident)
    if key not in rows:
        raise nw.NotionWriteError("annotation hors périmètre")
    return key


def _validate_evidence(
    evidence: object, snapshot: dict[str, Any], rows: nd.Rows,
) -> Evidence:
    if (
        not isinstance(evidence, dict)
        or set(evidence) != {"schema", "root_page", "structure_sha256", "entries"}
        or type(evidence["schema"]) is not int or evidence["schema"] != 1
        or evidence["root_page"] != snapshot["root_page"]
        or evidence["structure_sha256"] != snapshot["structure_sha256"]
    ):
        raise nw.NotionWriteError("annotations incompatibles avec l'inventaire")
    entries = evidence["entries"]
    if not isinstance(entries, list) or len(entries) > MAX_ANNOTATIONS:
        raise nw.NotionWriteError("liste d'annotations invalide ou trop longue")
    indexed: Evidence = {}
    for entry in entries:
        if not isinstance(entry, dict) or not set(entry) <= FIELDS | {"id", "category"}:
            raise nw.NotionWriteError("champs d'annotation invalides")
        key = _evidence_key(entry, rows)
        if key in indexed or len(entry) <= 2:
            raise nw.NotionWriteError("annotation vide ou répétée")
        _validate_fields(entry, rows[key], rows)
        indexed[key] = entry
    if sum("text" in entry for entry in indexed.values()) > MAX_TEXTS:
        raise nw.NotionWriteError("trop de textes pour une comparaison bornée")
    return indexed


def _validate_fields(entry: dict[str, Any], row: dict[str, Any], rows: nd.Rows) -> None:
    if "context" in entry:
        contexts = entry["context"]
        if (
            not isinstance(contexts, list) or not 1 <= len(contexts) <= len(PROTECTED)
            or any(not isinstance(value, str) or value not in PROTECTED for value in contexts)
            or len(set(contexts)) != len(contexts)
        ):
            raise nw.NotionWriteError("contexte de protection invalide")
    if any(not nd._matches(entry[field], LABEL) for field in LABEL_FIELDS.keys() & entry.keys()):
        raise nw.NotionWriteError("identifiant de groupe annoté invalide")
    if "text" in entry:
        text = entry["text"]
        if (
            not isinstance(text, str) or not 1 <= len(text) <= MAX_TEXT_LENGTH
            or ni.normalized_text_sha256(text) != row.get("text_sha256")
            or row.get("text_sha256") is None
        ):
            raise nw.NotionWriteError("texte annoté divergent de l'empreinte d'inventaire")
    if "navigation_target" in entry:
        target = entry["navigation_target"]
        if (
            row["category"] != "block" or not isinstance(target, dict)
            or set(target) != {"id", "category"}
            or target["category"] not in ("page", "database", "block")
        ):
            raise nw.NotionWriteError("destination de navigation invalide")
        _evidence_key(target, rows)
    if "diagram_sha256" in entry and (
        row.get("type") not in {"image", "file", "embed", "pdf"}
        or not nd._matches(entry["diagram_sha256"], nd.SHA)
    ):
        raise nw.NotionWriteError("empreinte de fichier de schéma invalide")


def _context(key: nd.Key, rows: nd.Rows, evidence: Evidence) -> list[str]:
    flags: set[str] = set()
    while True:
        row = rows[key]
        flags.update(evidence.get(key, {}).get("context", []))
        if row.get("type") == "synced_block":
            flags.add("synced_block")
        parent = row["parent_id"]
        if parent is None:
            return sorted(flags)
        key = nd._parent_key(key[0], parent, rows)


def _database_profiles(rows: nd.Rows) -> dict[str, list[str]]:
    profiles: dict[str, list[str]] = defaultdict(list)
    nonempty: set[str] = set()
    for row in rows.values():
        if row["category"] == "data_source":
            parent = row["parent_id"]
            profiles[parent].append(nw._digest(row["property_types"]))
            if row["property_types"]:
                nonempty.add(parent)
    return {parent: profiles[parent] for parent in nonempty}


def _buckets(
    rows: nd.Rows, evidence: Evidence, profiles: dict[str, list[str]],
) -> Buckets:
    groups: Buckets = defaultdict(list)
    for key, row in rows.items():
        if row.get("text_sha256") and row.get("type") != "synced_block":
            groups["exact", "normalized_text_and_block_type",
                   nw._digest([row["type"], row["text_sha256"]])].append(key)
    for ident, sources in profiles.items():
        groups["database", "matching_source_property_type_profiles",
               nw._digest(sorted(sources))].append(("database", ident))
    for key, entry in evidence.items():
        for field, family in LABEL_FIELDS.items():
            if field in entry:
                groups[family, "operator_annotated_equivalence", entry[field]].append(key)
        if "navigation_target" in entry:
            groups["navigation", "operator_annotated_destination",
                   nw._digest(entry["navigation_target"])].append(key)
        if "diagram_sha256" in entry:
            groups["diagram", "operator_annotated_asset_sha256", entry["diagram_sha256"]].append(key)
    return groups


def _semantic_pairs(
    evidence: Evidence, rows: nd.Rows,
) -> list[tuple[nd.Key, nd.Key, int]]:
    words = {
        key: set(WORD.findall(entry["text"].casefold()))
        for key, entry in evidence.items() if "text" in entry
    }
    pairs = combinations(sorted(key for key, tokens in words.items()
                                if len(tokens) >= MIN_DISTINCT_WORDS), 2)
    similar = []
    for left, right in pairs:
        if rows[left]["text_sha256"] == rows[right]["text_sha256"]:
            continue
        score = 100 * len(words[left] & words[right]) // len(words[left] | words[right])
        if score >= MIN_SIMILARITY:
            similar.append((left, right, score))
    return similar


def _finding(
    family: str, signal: str, keys: list[nd.Key], rows: nd.Rows,
    contexts: dict[nd.Key, list[str]],
) -> dict[str, Any]:
    return {
        "family": family, "signal": signal,
        "status": "protected_context" if any(contexts[key] for key in keys) else "review_required",
        "objects": [{**nd._location(rows[key]), "context": contexts[key]} for key in keys],
    }


def analyze(
    snapshot: object, *, root_page: str, evidence: object | None = None,
) -> dict[str, Any]:
    """Assess duplicates as review signals within a single selected inventory."""
    root_page = nw._id(root_page)
    validated, rows = nd._validated(snapshot, root_page)
    annotations = _validate_evidence(evidence, validated, rows) if evidence is not None else {}
    contexts = {key: _context(key, rows, annotations) for key in rows}
    profiles = _database_profiles(rows)
    findings = []
    for (family, signal, _), keys in sorted(_buckets(rows, annotations, profiles).items()):
        if len(keys) > 1:
            findings.append(_finding(family, signal, sorted(keys), rows, contexts))
    for left, right, score in _semantic_pairs(annotations, rows):
        finding = _finding("semantic", "lexical_similarity", [left, right], rows, contexts)
        finding["similarity_percent"] = score
        findings.append(finding)
    annotated_fields = Counter(
        field for entry in annotations.values() for field in FIELDS & entry.keys()
    )
    report: dict[str, Any] = {
        "schema": 1, "classification": "private_local_only", "root_page": root_page,
        "assessment": "NATIVE_DUPLICATE_SIGNALS_REVIEW_REQUIRED",
        "structure_sha256": validated["structure_sha256"],
        "evidence_sha256": nw._digest(evidence) if evidence is not None else None,
        "coverage": {
            "inventory_objects": len(rows),
            "normalized_text_blocks": sum(bool(row.get("text_sha256")) for row in rows.values()),
            "databases_with_property_profiles": len(profiles),
            "annotated_fields": dict(sorted(annotated_fields.items())),
            "annotation_based_families": {
                family: ("annotated_subset" if any(annotated_fields[field] for field in fields)
                         else "not_examined")
                for family, fields in {
                    "semantic": ("text", "semantic_key"),
                    "functional": ("function_key",),
                    "navigation": ("navigation_target",),
                    "organizational": ("organization_key",),
                    "source_of_truth": ("truth_key",),
                    "diagram": ("diagram_sha256",),
                }.items()
            },
            "qualified_as_exhaustive": False,
        },
        "capture_limitations": validated["limitations"],
        "findings": findings,
        "protected_objects": [
            {**nd._location(rows[key]), "context": contexts[key]}
            for key in sorted(contexts) if contexts[key]
        ],
        "remote_write": False,
    }
    report["report_sha256"] = nw._digest(report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Relever les doublons possibles dans un wiki Notion")
    parser.add_argument("--page", required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        output = nd._private_path(args.output)
        if output.exists():
            raise nw.NotionWriteError("le rapport doit être un nouveau fichier")
        snapshot = nd._load_snapshot(args.inventory)
        evidence = nd._load_snapshot(args.evidence) if args.evidence is not None else None
        if args.evidence is not None and evidence is None:
            raise nw.NotionWriteError("annotations JSON absentes")
        report = analyze(snapshot, root_page=args.page, evidence=evidence)
        nd._write_private_report(output, report)
    except nw.NotionWriteError as exc:
        print(f"NOTION_DUPLICATES=REFUSED {exc}")
        return 2
    except (OSError, ValueError, RecursionError):
        print("NOTION_DUPLICATES=REFUSED inventaire, annotations ou destination illisibles")
        return 2
    print("NOTION_DUPLICATES=REVIEW_REQUIRED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
