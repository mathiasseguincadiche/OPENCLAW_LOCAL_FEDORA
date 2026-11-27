"""Verify the observable effects of an approved Notion text edit, offline."""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from typing import Any

from clawfedora import notion_duplicates as dup
from clawfedora import notion_inventory_diff as nd
from clawfedora import notion_native_inventory as ni
from clawfedora import notion_references as refs
from clawfedora import notion_write as nw

MAX_EDITS = 5
CAPTURE_FIELDS = {"schema", "references", "text_witnesses"}
EXPECTATION_FIELDS = {
    "schema", "root_page", "page_id", "before_sha256", "manifest_sha256", "edits", "protected",
}
WITNESS_FIELDS = {"id", "text_sha256", "surroundings_sha256"}
EDIT_FIELDS = {"id", "type", "before_text_sha256", "after_text_sha256", "surroundings_sha256"}


def _seal(body: dict[str, Any], field: str) -> dict[str, Any]:
    return {**body, field: nw._digest(body)}


def _check(value: object, fields: set[str], digest: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields | {digest}:
        raise nw.NotionWriteError("format de preuve de non-régression invalide")
    if (
        type(value["schema"]) is not int or value["schema"] != 1
        or value[digest] != nw._digest({field: value[field] for field in fields})
    ):
        raise nw.NotionWriteError("empreinte ou schéma de preuve de non-régression invalide")
    return value


def capture(root: str) -> dict[str, Any]:
    witnesses: list[dict[str, Any]] = []

    def observe(category: str, ident: str, obj: dict[str, Any]) -> None:
        if category != "block" or obj["type"] not in nw.EDIT_TYPES or obj["has_children"]:
            return
        kind = obj["type"]
        try:
            text = nw._plain_text(obj, kind)
        except nw.NotionWriteError:
            return
        observable = {
            key: value for key, value in obj.items() if key not in ni.TRANSPORT_METADATA
        }
        observable[kind] = {key: value for key, value in obj[kind].items() if key != "rich_text"}
        witnesses.append({
            "id": ident, "text_sha256": nw._digest(text),
            "surroundings_sha256": nw._digest(ni._stable(observable)),
        })

    bundle = refs.capture_references(root, observer=observe)
    return _seal({"schema": 1, "references": bundle, "text_witnesses": witnesses}, "capture_sha256")


def _capture(
    value: object, root: str,
) -> tuple[dict[str, Any], nd.Rows, dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    capture_data = _check(value, CAPTURE_FIELDS, "capture_sha256")
    bundle = capture_data["references"]
    if not isinstance(bundle, dict):
        raise nw.NotionWriteError("registre de références invalide")
    inventory, rows, references = refs._validated_bundle(bundle, root)
    witnesses = capture_data["text_witnesses"]
    if not isinstance(witnesses, list) or len(witnesses) > len(rows):
        raise nw.NotionWriteError("liste de preuves textuelles invalide")
    indexed: dict[str, dict[str, Any]] = {}
    for witness in witnesses:
        if (
            not isinstance(witness, dict) or set(witness) != WITNESS_FIELDS
            or not isinstance(witness["id"], str) or witness["id"] in indexed
            or not all(nd._matches(witness[field], nd.SHA) for field in WITNESS_FIELDS - {"id"})
        ):
            raise nw.NotionWriteError("preuve textuelle invalide")
        row = rows.get(("block", witness["id"]))
        if row is None or row["type"] not in nw.EDIT_TYPES or row["has_children"]:
            raise nw.NotionWriteError("preuve textuelle hors du périmètre éditable")
        indexed[witness["id"]] = witness
    return inventory, rows, references, indexed


def _planned_edits(plan: object, digest: str, page: str) -> list[dict[str, Any]]:
    if (
        not isinstance(plan, dict) or type(plan.get("schema")) is not int or plan["schema"] != 1
        or plan.get("manifest_sha256") != digest or not nd.SHA.fullmatch(digest)
        or plan.get("page_id") != page
        or nw._digest({k: v for k, v in plan.items() if k != "manifest_sha256"}) != digest
    ):
        raise nw.NotionWriteError("empreinte approuvée ou page du plan divergente")
    if plan.get("action") == "replace_plain_text":
        fields = {"schema", "action", "page_id", "block_id", "block_type",
                  "old_sha256", "new_text", "created_at", "manifest_sha256"}
        if set(plan) == fields:
            return [{"block_id": plan["block_id"], "type": plan["block_type"],
                     "old_sha256": plan["old_sha256"], "new_text": plan["new_text"]}]
    elif plan.get("action") == "replace_plain_text_batch":
        fields = {"schema", "action", "page_id", "inventory_sha256", "edits",
                  "created_at", "manifest_sha256"}
        edits = plan.get("edits")
        if set(plan) == fields and isinstance(edits, list) and 1 <= len(edits) <= MAX_EDITS:
            return edits
    raise nw.NotionWriteError("plan d'écriture de texte non pris en charge")


def prepare(
    before: dict[str, Any], *, root_page: str, page: str, plan: object, approved_manifest: str,
    annotations: object = None,
) -> dict[str, Any]:
    root, page = nw._id(root_page), nw._id(page)
    inventory, rows, _, witnesses = _capture(before, root)
    evidence = (
        dup._validate_evidence(annotations, inventory, rows) if annotations is not None else {}
    )
    protected = [
        {**nd._location(rows[key]), "context": context}
        for key in sorted(rows) if (context := dup._context(key, rows, evidence))
    ]
    protected_ids = {obj["id"] for obj in protected if obj["category"] == "block"}
    expected: dict[str, dict[str, Any]] = {}
    for edit in _planned_edits(plan, approved_manifest, page):
        if (
            not isinstance(edit, dict) or set(edit) != {"block_id", "type", "old_sha256", "new_text"}
            or not nd._matches(edit["old_sha256"], nd.SHA) or not isinstance(edit["block_id"], str)
        ):
            raise nw.NotionWriteError("bloc du plan d'écriture invalide")
        ident = nw._id(edit["block_id"])
        row = rows.get(("block", ident))
        if (
            row is None or row["parent_id"] != page or ("page", page) not in rows
            or row["type"] != edit["type"] or ident not in witnesses or ident in expected
            or ident in protected_ids
        ):
            raise nw.NotionWriteError("bloc prévu protégé, hors périmètre ou incompatible")
        witness = witnesses[ident]
        wanted = nw._digest(nw._text(edit["new_text"]))
        if wanted == witness["text_sha256"]:
            raise nw.NotionWriteError("texte prévu déjà présent dans la capture initiale")
        expected[ident] = {
            "id": ident, "type": row["type"], "before_text_sha256": witness["text_sha256"],
            "after_text_sha256": wanted, "surroundings_sha256": witness["surroundings_sha256"],
        }
    return _seal({
        "schema": 1, "root_page": root, "page_id": page, "before_sha256": before["capture_sha256"],
        "manifest_sha256": approved_manifest, "edits": [expected[k] for k in sorted(expected)],
        "protected": protected,
    }, "expectation_sha256")


def _expected(
    value: object, root: str, before_sha: str, rows: nd.Rows, witnesses: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], set[nd.Key]]:
    expectation = _check(value, EXPECTATION_FIELDS, "expectation_sha256")
    page = expectation["page_id"]
    if (
        expectation["root_page"] != root or expectation["before_sha256"] != before_sha
        or not nd._matches(page, nd.IDENTIFIER) or ("page", page) not in rows
        or not nd._matches(expectation["manifest_sha256"], nd.SHA)
    ):
        raise nw.NotionWriteError("attendus hors périmètre ou liés à une autre capture initiale")
    raw = expectation["edits"]
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_EDITS:
        raise nw.NotionWriteError("attendus de texte invalides")
    expected: dict[str, dict[str, Any]] = {}
    for edit in raw:
        if (
            not isinstance(edit, dict) or set(edit) != EDIT_FIELDS
            or not isinstance(edit["id"], str) or edit["id"] in expected
            or not nd._matches(edit["after_text_sha256"], nd.SHA)
        ):
            raise nw.NotionWriteError("attendu de texte invalide")
        ident = edit["id"]
        witness = witnesses.get(ident)
        row = rows.get(("block", ident))
        if (
            witness is None or row is None or row["type"] != edit["type"]
            or row["parent_id"] != page or witness["text_sha256"] != edit["before_text_sha256"]
            or witness["surroundings_sha256"] != edit["surroundings_sha256"]
            or edit["before_text_sha256"] == edit["after_text_sha256"]
        ):
            raise nw.NotionWriteError("attendu de texte incompatible avec la capture initiale")
        expected[ident] = edit
    protected: set[nd.Key] = set()
    raw_protected = expectation["protected"]
    if not isinstance(raw_protected, list) or len(raw_protected) > len(rows):
        raise nw.NotionWriteError("liste de contenus protégés invalide")
    for item in raw_protected:
        if not isinstance(item, dict) or set(item) != {
            "id", "category", "parent_id", "position", "context",
        }:
            raise nw.NotionWriteError("élément protégé invalide")
        key = dup._evidence_key(item, rows)
        if key in protected or any(item[k] != v for k, v in nd._location(rows[key]).items()):
            raise nw.NotionWriteError("emplacement protégé divergent")
        context = item["context"]
        if (
            not isinstance(context, list) or not context
            or any(not isinstance(c, str) or c not in dup.PROTECTED | {"synced_block"}
                   for c in context)
        ):
            raise nw.NotionWriteError("contexte protégé invalide")
        protected.add(key)
    if any(("block", ident) in protected for ident in expected):
        raise nw.NotionWriteError("une modification cible un contenu protégé")
    return expectation, expected, protected



def _changed_links(
    before: dict[str, dict[str, Any]], after: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    # A refreshed signed URL may have a different expiry without a different attachment.
    def group(references: dict[str, dict[str, Any]]) -> dict[nd.Key, Counter[str]]:
        result: dict[nd.Key, Counter[str]] = {}
        for row in references.values():
            key = row["source_category"], row["source_id"]
            meaning = {k: row[k] for k in ("slot", "kind", "target_id", "url_sha256", "page_id")}
            result.setdefault(key, Counter())[nw._digest(meaning)] += 1
        return result

    left, right = group(before), group(after)
    return [
        {"category": key[0], "id": key[1], "before_count": sum(left.get(key, Counter()).values()),
         "after_count": sum(right.get(key, Counter()).values())}
        for key in sorted(left.keys() | right.keys()) if left.get(key) != right.get(key)
    ]


def audit(
    before: dict[str, Any], after: dict[str, Any], expectation: object, *, root_page: str,
) -> dict[str, Any]:
    root = nw._id(root_page)
    initial, old, old_links, old_text = _capture(before, root)
    current, new, new_links, new_text = _capture(after, root)
    if refs._utc(initial["captured_at"]) >= refs._utc(current["captured_at"]):
        raise nw.NotionWriteError("capture après modification strictement postérieure requise")
    contract, expected, protected = _expected(
        expectation, root, before["capture_sha256"], old, old_text,
    )
    diff = nd.compare(initial, current, root_page=root)
    expected_results = []
    for ident, edit in expected.items():
        witness = new_text.get(ident)
        if witness is None:
            status = "missing_or_incompatible"
        elif witness["surroundings_sha256"] != edit["surroundings_sha256"]:
            status = "surroundings_changed"
        elif witness["text_sha256"] != edit["after_text_sha256"]:
            status = "expected_text_not_observed"
        else:
            status = "observed"
        expected_results.append({"id": ident, "status": status})

    unexpected = []
    metadata_only = []
    for change in diff["modified"]:
        key = change["category"], change["id"]
        if (
            key[0] == "block" and key[1] in expected and not change["structure"]
            and set(change["fingerprints"]) <= {"sha256", "text_sha256", "observable_sha256"}
            and not change["metadata_changed"]
        ):
            continue
        if (
            set(change["fingerprints"]) == {"sha256"} and not change["structure"]
            and not change["metadata_changed"]
        ):
            metadata_only.append(change)
        else:
            unexpected.append(change)
    changed_keys = {
        (row["category"], row["id"]) for row in diff["absent"] + unexpected
    }
    protected_changes = [{**nd._location(old[key]), "status": "changed_or_absent"}
                         for key in sorted(protected & changed_keys)]
    links = _changed_links(old_links, new_links)
    same_coverage = set(initial["limitations"]) == set(current["limitations"])
    verdict = "CONFORME_OBSERVABLE"
    if (
        diff["added"] or diff["absent"] or diff["reordered"] or unexpected or links
        or any(result["status"] != "observed" for result in expected_results)
    ):
        verdict = "NON_CONFORME"
    elif metadata_only or not same_coverage:
        verdict = "PARTIELLEMENT_CONFORME"
    return _seal({
        "schema": 1, "classification": "private_local_only", "root_page": root,
        "assessment": "NATIVE_NON_REGRESSION_REVIEW_REQUIRED", "verdict": verdict,
        "remote_write": False, "expectation_sha256": contract["expectation_sha256"],
        "manifest_sha256": contract["manifest_sha256"], "before_sha256": before["capture_sha256"],
        "after_sha256": after["capture_sha256"], "comparison_sha256": diff["report_sha256"],
        "expected_changes": expected_results,
        "unexpected_changes": {"added": diff["added"], "absent": diff["absent"],
                               "modified": unexpected, "reordered": diff["reordered"]},
        "metadata_only": metadata_only, "protected_checked": len(protected),
        "protected_changes": protected_changes, "changed_references": links,
        "coverage": {"before": initial["limitations"], "after": current["limitations"],
                     "same_limitations": same_coverage, "render_checked": False,
                     "external_destinations_checked": False},
    }, "report_sha256")


def _json(path: Path) -> dict[str, Any]:
    data = nd._load_snapshot(path)
    if not isinstance(data, dict):
        raise nw.NotionWriteError("objet JSON privé requis")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Contrôler la non-régression Notion")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("capture", "prepare", "audit"):
        cmd = commands.add_parser(name)
        cmd.add_argument("--page", required=True)
        cmd.add_argument("--output", type=Path, required=True)
        if name != "capture":
            cmd.add_argument("--before", type=Path, required=True)
        if name == "prepare":
            cmd.add_argument("--edit-page", required=True)
            cmd.add_argument("--plan", type=Path, required=True)
            cmd.add_argument("--approve-manifest", required=True)
            cmd.add_argument("--annotations", type=Path)
        if name == "audit":
            cmd.add_argument("--after", type=Path, required=True)
            cmd.add_argument("--expectation", type=Path, required=True)
            cmd.add_argument("--expectation-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        output = nd._private_path(args.output)
        if output.exists():
            raise nw.NotionWriteError("la destination doit être un fichier neuf")
        if args.command == "capture":
            result = capture(args.page)
            summary = "CAPTURED"
        elif args.command == "prepare":
            result = prepare(
                _json(args.before), root_page=args.page, page=args.edit_page, plan=_json(args.plan),
                approved_manifest=args.approve_manifest,
                annotations=_json(args.annotations) if args.annotations is not None else None,
            )
            summary = f"PREPARED expectation_sha256={result['expectation_sha256']}"
        else:
            expectation = _json(args.expectation)
            if expectation.get("expectation_sha256") != args.expectation_sha256:
                raise nw.NotionWriteError("empreinte des attendus non confirmée")
            result = audit(_json(args.before), _json(args.after), expectation, root_page=args.page)
            summary = result["verdict"]
        nd._write_private_report(output, result)
    except nw.NotionWriteError as exc:
        print(f"NOTION_REGRESSION=REFUSED {exc}")
        return 2
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        print("NOTION_REGRESSION=REFUSED entrée ou destination illisible")
        return 2
    print(f"NOTION_REGRESSION={summary}")
    return 1 if summary == "NON_CONFORME" else 0


if __name__ == "__main__":
    raise SystemExit(main())
