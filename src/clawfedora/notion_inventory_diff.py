"""Compare private native Notion inventories offline, without accessing Notion."""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import tempfile
from collections import Counter, defaultdict, deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from clawfedora import notion_native_inventory as ni
from clawfedora import notion_write as nw

MAX_BYTES = 8 * 1024 * 1024
SHA = re.compile(r"[a-f0-9]{64}")
IDENTIFIER = re.compile(ni.ID)
KIND = re.compile(r"[a-z][a-z0-9_]{0,63}")
METADATA = {
    "page": ("cover_present", "icon_present"),
    "block": ("type", "has_children", "text_sha256", "media"),
    "database": (),
    "data_source": ("property_types",),
    "view": ("type", "filter_present", "sort_count"),
}
ROW_FIELDS = {"category", "id", "parent_id", "position", "sha256"}
INVENTORY_FIELDS = {
    "schema", "classification", "assessment", "root_page", "api_version", "captured_at",
    "objects", "counts", "requests", "limitations", "remote_write", "native_render_verified",
    "structure_sha256",
}
Key = tuple[str, str]
Rows = dict[Key, dict[str, Any]]
SiblingGroup = tuple[str, str]


def _matches(value: object, pattern: re.Pattern[str]) -> bool:
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _integer(value: object, low: int, high: int) -> bool:
    return type(value) is int and low <= value <= high


def _validate_row(row: object, schema: int) -> Key:
    if not isinstance(row, dict) or not isinstance(row.get("category"), str):
        raise nw.NotionWriteError("objet d'inventaire mal formé")
    category = row["category"]
    if category not in METADATA:
        raise nw.NotionWriteError("catégorie d'objet inconnue")
    fields = ROW_FIELDS.union(METADATA[category])
    if schema == ni.SCHEMA:
        fields.add("observable_sha256")
        if category == "data_source":
            fields.add("properties_sha256")
    if set(row) != fields or not _matches(row["id"], IDENTIFIER):
        raise nw.NotionWriteError("champs ou identité d'objet invalides")
    if row["parent_id"] is not None and not _matches(row["parent_id"], IDENTIFIER):
        raise nw.NotionWriteError("identifiant de parent invalide")
    if category in {"block", "view"}:
        if not _integer(row["position"], 0, ni.MAX_OBJECTS - 1):
            raise nw.NotionWriteError("position d'objet invalide")
    elif row["position"] is not None:
        raise nw.NotionWriteError("position inattendue")
    for field in fields - ROW_FIELDS:
        value = row[field]
        if field.endswith("_sha256"):
            if not (field == "text_sha256" and value is None) and not _matches(value, SHA):
                raise nw.NotionWriteError("empreinte d'objet invalide")
        elif field == "type":
            if not _matches(value, KIND):
                raise nw.NotionWriteError("type d'objet invalide")
        elif field == "property_types":
            if not isinstance(value, dict) or any(
                not _matches(kind, KIND) or type(count) is not int or count < 1
                for kind, count in value.items()
            ):
                raise nw.NotionWriteError("types de propriétés invalides")
        elif field == "sort_count":
            if type(value) is not int or value < 0:
                raise nw.NotionWriteError("nombre de tris invalide")
        elif type(value) is not bool:
            raise nw.NotionWriteError("indicateur d'objet invalide")
    if not _matches(row["sha256"], SHA):
        raise nw.NotionWriteError("empreinte d'objet invalide")
    if category == "block" and row["media"] != (row["type"] in ni.MEDIA):
        raise nw.NotionWriteError("indicateur de média incohérent")
    return category, row["id"]


def _parent_key(category: str, parent: str, rows: Rows) -> Key:
    if category in {"data_source", "view"}:
        return "database", parent
    if ("page", parent) in rows:
        return "page", parent
    block = rows.get(("block", parent))
    if block is None or not block["has_children"] or block["type"] in {
        "child_page", "child_database", "link_to_page", "unsupported",
    }:
        raise nw.NotionWriteError("parent de bloc ou page absent ou incohérent")
    return "block", parent


def _validate_tree(rows: Rows, root: Key) -> None:
    if root not in rows or rows[root]["parent_id"] is not None or ("block", root[1]) in rows:
        raise nw.NotionWriteError("racine d'inventaire incohérente")
    children: dict[Key, list[Key]] = defaultdict(list)
    positions: dict[SiblingGroup, list[int]] = defaultdict(list)
    for key, row in rows.items():
        if key == root:
            continue
        category, ident = key
        parent = row["parent_id"]
        if parent is None:
            raise nw.NotionWriteError("objet sans parent dans le périmètre")
        parent_key = _parent_key(category, parent, rows)
        if parent_key not in rows:
            raise nw.NotionWriteError("parent absent de l'inventaire")
        children[parent_key].append(key)
        if row["position"] is not None:
            positions[category, parent].append(row["position"])
        if category in {"page", "database"}:
            block = rows.get(("block", ident))
            if block is None or block["type"] != f"child_{category}" or block["parent_id"] != parent:
                raise nw.NotionWriteError("bloc représentant la page ou base absent ou divergent")
        if (
            category == "block" and row["type"] in {"child_page", "child_database"}
            and (row["type"].removeprefix("child_"), ident) not in rows
        ):
            raise nw.NotionWriteError("page ou base enfant absente de l'inventaire")
    if any(sorted(group) != list(range(len(group))) for group in positions.values()):
        raise nw.NotionWriteError("ordre incomplet ou positions dupliquées")
    queue = deque([root])
    reached = 0
    while queue:
        reached += 1
        queue.extend(children.get(queue.popleft(), ()))
    if reached != len(rows):
        raise nw.NotionWriteError("objets hors périmètre ou parents cycliques")


def _validated(snapshot: object, root_page: str) -> tuple[dict[str, Any], Rows]:
    if not isinstance(snapshot, dict):
        raise nw.NotionWriteError("inventaire JSON non objet")
    schema = snapshot.get("schema")
    if type(schema) is not int or schema not in {1, ni.SCHEMA}:
        raise nw.NotionWriteError("version de schéma d'inventaire non prise en charge")
    fields = INVENTORY_FIELDS | ({"inventory_sha256"} if schema == ni.SCHEMA else set())
    if (
        set(snapshot) != fields or snapshot["root_page"] != root_page
        or snapshot["api_version"] != ni.VERSION
        or snapshot["classification"] != "private_local_only"
        or snapshot["assessment"] != ni.ASSESSMENT
        or snapshot["remote_write"] is not False or snapshot["native_render_verified"] is not False
        or not _integer(snapshot["requests"], 2, ni.MAX_REQUESTS)
    ):
        raise nw.NotionWriteError("inventaire hors périmètre, incompatible ou incomplet")
    stamp = snapshot["captured_at"]
    if not isinstance(stamp, str) or len(stamp) > 40:
        raise nw.NotionWriteError("horodatage de capture invalide")
    try:
        captured_at = datetime.fromisoformat(stamp)
    except ValueError:
        raise nw.NotionWriteError("horodatage de capture invalide") from None
    if captured_at.utcoffset() != timedelta(0):
        raise nw.NotionWriteError("horodatage de capture UTC requis")
    limits = snapshot["limitations"]
    if (
        not isinstance(limits, list) or len(limits) > len(ni.BASE_LIMITS | ni.OPTIONAL_LIMITS)
        or not all(isinstance(limit, str) for limit in limits)
        or len(set(limits)) != len(limits)
        or not ni.BASE_LIMITS <= set(limits) <= ni.BASE_LIMITS | ni.OPTIONAL_LIMITS
    ):
        raise nw.NotionWriteError("couverture d'inventaire invalide")
    objects = snapshot["objects"]
    if not isinstance(objects, list) or not 1 <= len(objects) <= ni.MAX_OBJECTS:
        raise nw.NotionWriteError("liste d'objets absente ou hors limite")
    rows: Rows = {}
    for row in objects:
        key = _validate_row(row, schema)
        if key in rows:
            raise nw.NotionWriteError("objet d'inventaire répété")
        rows[key] = row
    counts = snapshot["counts"]
    if (
        not isinstance(counts, dict) or not all(type(count) is int for count in counts.values())
        or counts != Counter(category for category, _ in rows)
    ):
        raise nw.NotionWriteError("totaux d'inventaire divergents")
    _validate_tree(rows, ("page", root_page))
    if snapshot["structure_sha256"] != nw._digest(objects):
        raise nw.NotionWriteError("empreinte de structure divergente")
    if schema == ni.SCHEMA and snapshot["inventory_sha256"] != nw._digest({
        field: snapshot[field] for field in fields - {"inventory_sha256"}
    }):
        raise nw.NotionWriteError("empreinte d'inventaire divergente")
    return snapshot, rows


def _sibling_order(rows: Rows, comparable: set[Key]) -> dict[SiblingGroup, list[str]]:
    groups: dict[SiblingGroup, list[tuple[int, str]]] = defaultdict(list)
    for category, ident in comparable:
        row = rows[category, ident]
        if row["position"] is not None:
            groups[category, row["parent_id"]].append((row["position"], ident))
    return {group: [ident for _, ident in sorted(items)] for group, items in groups.items()}


def _location(row: dict[str, Any]) -> dict[str, Any]:
    return {field: row[field] for field in ("category", "id", "parent_id", "position")}


def _changed(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any] | None:
    structure = {
        field: {"before": before[field], "after": after[field]}
        for field in ("parent_id", "position")
        if before[field] != after[field]
    }
    fingerprints = {
        field: {"before": before[field], "after": after[field]}
        for field in ("sha256", "observable_sha256", "text_sha256", "properties_sha256")
        if before.get(field) != after.get(field)
    }
    metadata = sorted(
        field for field in METADATA[before["category"]]
        if field != "text_sha256" and before[field] != after[field]
    )
    if not (structure or fingerprints or metadata):
        return None
    return {
        "category": before["category"], "id": before["id"], "structure": structure,
        "fingerprints": fingerprints, "metadata_changed": metadata,
    }


def compare(before: object, after: object, *, root_page: str) -> dict[str, Any]:
    """Return a deterministic report for the operator-selected wiki and direction."""
    root_page = nw._id(root_page)
    left, old = _validated(before, root_page)
    right, new = _validated(after, root_page)
    if left["schema"] != right["schema"]:
        raise nw.NotionWriteError("schémas d'inventaire différents")
    if datetime.fromisoformat(left["captured_at"]) > datetime.fromisoformat(right["captured_at"]):
        raise nw.NotionWriteError("ordre chronologique des captures inversé")
    common = old.keys() & new.keys()
    modified = []
    for key in sorted(common):
        changes = _changed(old[key], new[key])
        if changes is not None:
            modified.append(changes)
    comparable = {key for key in common if old[key]["parent_id"] == new[key]["parent_id"]}
    old_order = _sibling_order(old, comparable)
    new_order = _sibling_order(new, comparable)
    reordered = [
        {"category": category, "parent_id": parent, "before": old_order[category, parent],
         "after": new_order[category, parent]}
        for category, parent in sorted(old_order)
        if old_order[category, parent] != new_order[category, parent]
    ]
    report: dict[str, Any] = {
        "schema": 1, "inventory_schema": left["schema"], "api_version": left["api_version"],
        "classification": "private_local_only", "root_page": root_page,
        "assessment": "NATIVE_INVENTORIES_COMPARED_REVIEW_REQUIRED",
        "remote_write": False, "native_render_verified": False,
        "before": {f: left[f] for f in ("captured_at", "structure_sha256", "limitations")},
        "after": {f: right[f] for f in ("captured_at", "structure_sha256", "limitations")},
        "added": [_location(new[key]) for key in sorted(new.keys() - old.keys())],
        "absent": [_location(old[key]) for key in sorted(old.keys() - new.keys())],
        "modified": modified,
        "reordered": reordered,
    }
    report["report_sha256"] = nw._digest(report)
    return report


def _private_path(path: Path) -> Path:
    path = path.absolute()
    if os.name != "posix":
        raise nw.NotionWriteError("permissions privées POSIX requises")
    if path != path.resolve() or any(p.is_symlink() for p in (path, *path.parents)):
        raise nw.NotionWriteError("chemin lié interdit")
    if any((p / ".git").exists() for p in path.parents):
        raise nw.NotionWriteError("fichier privé requis hors Git")
    directory = path.parent.stat()
    if not stat.S_ISDIR(directory.st_mode) or directory.st_mode & 0o077:
        raise nw.NotionWriteError("dossier privé requis")
    if directory.st_uid != os.getuid():
        raise nw.NotionWriteError("dossier privé appartenant à l'opérateur requis")
    return path


def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = dict(pairs)
    if len(result) != len(pairs):
        raise nw.NotionWriteError("clé JSON en double")
    return result


def _load_snapshot(path: Path) -> object:
    path = _private_path(path)
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    with os.fdopen(os.open(path, flags), "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077
            or info.st_uid != os.getuid() or info.st_size > MAX_BYTES
        ):
            raise nw.NotionWriteError("fichier d'inventaire privé ou taille invalide")
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise nw.NotionWriteError("fichier d'inventaire trop volumineux")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_json_object)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Comparer deux inventaires Notion hors ligne")
    parser.add_argument("--page", required=True)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        output = _private_path(args.output)
        if output.exists():
            raise nw.NotionWriteError("le rapport doit être un nouveau fichier")
        report = compare(_load_snapshot(args.before), _load_snapshot(args.after), root_page=args.page)
        with tempfile.TemporaryDirectory(dir=output.parent) as directory:
            staged = Path(directory) / "report.json"
            nw._private_new(staged, report)
            os.link(staged, output)
    except nw.NotionWriteError as exc:
        print(f"NOTION_INVENTORY_DIFF=REFUSED {exc}")
        return 2
    except (OSError, ValueError, RecursionError):
        print("NOTION_INVENTORY_DIFF=REFUSED inventaire ou destination illisible")
        return 2
    print("NOTION_INVENTORY_DIFF=REVIEW_REQUIRED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
