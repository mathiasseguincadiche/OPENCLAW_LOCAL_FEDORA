"""Capture Notion references and audit them without following links."""
from __future__ import annotations

import argparse
import re
from collections import Counter
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from clawfedora import notion_inventory_diff as nd
from clawfedora import notion_native_inventory as ni
from clawfedora import notion_write as nw

MAX_REFERENCES = 3000
MAX_URL = 4096
ID_PATTERN = r"[0-9a-f]{32}|[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"
URL_ID = re.compile(rf"(?:^|[-/])({ID_PATTERN})/?$", re.IGNORECASE)
UUID = re.compile(ID_PATTERN, re.IGNORECASE)
STAMP = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|\+00:00)", re.ASCII)
NOTION_HOSTS = {"notion.so", "www.notion.so", "app.notion.com", "notion.site"}
DOC_HOSTS = {"developers.notion.com", "docs.github.com", "docs.python.org", "docs.fedoraproject.org"}
CI_PATH = re.compile(r"/[^/]+/[^/]+/actions/(?:runs|workflows)(?:/|$)")
INTERNAL = {"page", "database", "block", "local_block", "page_or_database"}
EXTERNAL = {"github", "github_ci", "documentation", "external"}
OTHER = {"temporary_attachment", "attachment_unverified", "redacted_url", "unrecognized"}
SLOTS = {"body", "caption", "cell", "link", "attachment", "cover", "icon", "property", "metadata"}
SOURCE_CATEGORIES = {"block", "page", "database", "data_source"}
CAPTURE_FIELDS = {"schema", "classification", "inventory", "references", "capture_sha256"}
REF_FIELDS = {"source_category", "source_id", "slot", "index", "reference_id",
              "kind", "target_id", "url_sha256", "page_id", "expires_at"}
DEFAULT_LIMITS = [
    "destinations_not_contacted",
    "database_rows_dashboard_widgets_and_synced_copies_not_read",
    "raw_text_html_and_non_uuid_anchors_not_resolved",
    "attachments_bytes_login_and_ci_conclusion_not_verified",
    "external_statuses_require_operator_observations",
]


@dataclass(frozen=True)
class Target:
    kind: str
    target_id: str | None = None
    url_sha256: str | None = None
    page_id: str | None = None
    expires_at: str | None = None


def _object(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _items(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _utc(value: object) -> datetime:
    if not isinstance(value, str) or not STAMP.fullmatch(value):
        raise nw.NotionWriteError("horodatage UTC invalide")
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise nw.NotionWriteError("horodatage UTC invalide") from None


def _internal(kind: str, ident: object) -> Target:
    if isinstance(ident, str) and UUID.fullmatch(ident) is not None:
        return Target(kind, target_id=nw._id(ident))
    return Target("unrecognized")


def _notion_path(path: str, fragment: str, query: str, *, relative: bool = False) -> Target:
    match = URL_ID.search(unquote(path))
    page_id = nw._id(match[1]) if match else None
    if fragment:
        anchor = unquote(fragment)
        if UUID.fullmatch(anchor):
            if page_id is not None:
                return Target("block", target_id=nw._id(anchor), page_id=page_id)
            if relative and not path and not query:
                return Target("local_block", target_id=nw._id(anchor))
    elif page_id is not None and not query:
        return Target("page_or_database", target_id=page_id)
    return Target("unrecognized")


def _url(value: object) -> Target:
    if not isinstance(value, str) or not 1 <= len(value) <= MAX_URL or any(
        char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value
    ):
        return Target("unrecognized")
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        port = parsed.port
    except ValueError:
        return Target("unrecognized")
    if not parsed.scheme and not parsed.netloc and value.startswith(("/", "#")):
        return _notion_path(parsed.path, parsed.fragment, parsed.query, relative=True)
    if parsed.scheme not in {"http", "https"} or not host:
        return Target("unrecognized")
    if parsed.username is not None or port not in {None, 80, 443}:
        return Target("redacted_url")
    if host in NOTION_HOSTS or host.endswith(".notion.site"):
        return _notion_path(parsed.path, parsed.fragment, parsed.query)
    if parsed.query or parsed.fragment or "?" in value or "#" in value:
        return Target("redacted_url")
    if host == "github.com":
        kind = "github_ci" if CI_PATH.match(parsed.path) else "github"
    else:
        kind = "documentation" if host in DOC_HOSTS else "external"
    return Target(kind, url_sha256=sha256(value.encode("utf-8")).hexdigest())


def _text_reference(part: dict[str, Any]) -> Target | None:
    mention = _object(part.get("mention"))
    kind = mention.get("type")
    if isinstance(kind, str) and kind in {"page", "database"}:
        target = _internal(kind, _object(mention.get(kind)).get("id"))
        if target.kind != "unrecognized":
            return target
    if kind == "link_preview":
        return _url(_object(mention.get("link_preview")).get("url"))
    href = part.get("href")
    if href is None:
        href = _object(_object(part.get("text")).get("link")).get("url")
    if href is not None:
        return _url(href)
    if kind in ("page", "database"):
        return Target("unrecognized")
    return None


def _rich_text(slot: str, text: object) -> Iterator[tuple[str, Target]]:
    for raw in _items(text):
        target = _text_reference(_object(raw))
        if target is not None:
            yield slot, target


def _attachment(value: dict[str, Any]) -> Target:
    kind = value.get("type")
    if kind == "external":
        return _url(_object(value.get("external")).get("url"))
    if kind == "file":
        stamp = _object(value.get("file")).get("expiry_time")
        try:
            return Target("temporary_attachment", expires_at=_utc(stamp).isoformat())
        except nw.NotionWriteError:
            pass
    return Target("attachment_unverified")


def _object_references(category: str, obj: dict[str, Any]) -> Iterator[tuple[str, Target]]:
    if category == "block":
        kind = obj["type"]
        data = obj[kind]
        yield from _rich_text("body", data.get("rich_text"))
        yield from _rich_text("caption", data.get("caption"))
        if kind == "table_row":
            for cell in _items(data.get("cells")):
                yield from _rich_text("cell", cell)
        elif kind == "link_to_page":
            key = data.get("type")
            if isinstance(key, str) and key in {"page_id", "database_id", "block_id"}:
                yield "link", _internal(key.removesuffix("_id"), data.get(key))
            else:
                yield "link", Target("unrecognized")
        elif kind in {"bookmark", "embed", "link_preview", "html"}:
            yield "link", _url(data.get("url"))
        elif kind in {"audio", "file", "image", "pdf", "video"}:
            yield "attachment", _attachment(data)
    elif category in SOURCE_CATEGORIES:
        for slot in ("cover", "icon"):
            media = _object(obj.get(slot))
            if media.get("type") in ("file", "external", "file_upload"):
                yield slot, _attachment(media)
        for name in ("title", "description"):
            yield from _rich_text("metadata", obj.get(name))
        if category == "page":
            for prop in _object(obj.get("properties")).values():
                data = _object(prop)
                kind = data.get("type")
                if isinstance(kind, str) and kind in {"rich_text", "title"}:
                    yield from _rich_text("property", data.get(kind))
                elif kind == "files":
                    for media in _items(data.get("files")):
                        yield "property", _attachment(_object(media))
                elif kind == "url" and data.get("url") is not None:
                    yield "property", _url(data["url"])


def capture_references(root_page: str, *, observer: ni.Observer | None = None) -> dict[str, Any]:
    """Keep safe reference descriptors from the normal Notion inventory traversal."""
    references: list[dict[str, Any]] = []

    def observe(category: str, ident: str, obj: dict[str, Any]) -> None:
        for index, (slot, target) in enumerate(_object_references(category, obj)):
            if len(references) == MAX_REFERENCES:
                raise nw.NotionWriteError("budget de références dépassé")
            row = {"source_category": category, "source_id": ident, "slot": slot,
                   "index": index, **asdict(target)}
            references.append({**row, "reference_id": nw._digest(row)})
        if observer is not None:
            observer(category, ident, obj)

    bundle = {"schema": 1, "classification": "private_local_only",
              "inventory": ni.capture(root_page, observer=observe), "references": references}
    return {**bundle, "capture_sha256": nw._digest(bundle)}



def _validate_reference(row: object, rows: nd.Rows) -> tuple[str, str, int]:
    if not isinstance(row, dict) or set(row) != REF_FIELDS:
        raise nw.NotionWriteError("champs de référence invalides")
    category, ident, slot, index = (row[k] for k in ("source_category", "source_id", "slot", "index"))
    if (
        not isinstance(category, str) or category not in SOURCE_CATEGORIES
        or not isinstance(ident, str) or not nd.IDENTIFIER.fullmatch(ident)
        or (category, ident) not in rows or not isinstance(slot, str) or slot not in SLOTS
        or type(index) is not int or not 0 <= index < MAX_REFERENCES
    ):
        raise nw.NotionWriteError("source de référence hors périmètre ou invalide")
    kind = row["kind"]
    if not isinstance(kind, str) or kind not in INTERNAL | EXTERNAL | OTHER:
        raise nw.NotionWriteError("type de destination invalide")
    if kind in INTERNAL:
        if not nd._matches(row["target_id"], nd.IDENTIFIER):
            raise nw.NotionWriteError("identifiant de destination invalide")
    elif row["target_id"] is not None:
        raise nw.NotionWriteError("identifiant de destination inattendu")
    if row["page_id"] is not None and (
        kind != "block" or not nd._matches(row["page_id"], nd.IDENTIFIER)
    ):
        raise nw.NotionWriteError("identifiant de page pour ancre invalide")
    if kind in EXTERNAL:
        if not nd._matches(row["url_sha256"], nd.SHA):
            raise nw.NotionWriteError("empreinte d'URL invalide")
    elif row["url_sha256"] is not None:
        raise nw.NotionWriteError("empreinte d'URL inattendue")
    if kind == "temporary_attachment":
        _utc(row["expires_at"])
    elif row["expires_at"] is not None:
        raise nw.NotionWriteError("expiration inattendue")
    if row["reference_id"] != nw._digest({k: row[k] for k in REF_FIELDS - {"reference_id"}}):
        raise nw.NotionWriteError("empreinte de référence divergente")
    return category, ident, index


def _validated_bundle(
    bundle: dict[str, Any], root_page: str,
) -> tuple[dict[str, Any], nd.Rows, dict[str, dict[str, Any]]]:
    if (
        set(bundle) != CAPTURE_FIELDS or type(bundle["schema"]) is not int or bundle["schema"] != 1
        or bundle["classification"] != "private_local_only"
        or not isinstance(bundle["references"], list) or len(bundle["references"]) > MAX_REFERENCES
    ):
        raise nw.NotionWriteError("capture de références incompatible")
    inventory, rows = nd._validated(bundle["inventory"], root_page)
    references: dict[str, dict[str, Any]] = {}
    positions: dict[nd.Key, int] = {}
    for row in bundle["references"]:
        category, ident, index = _validate_reference(row, rows)
        key = category, ident
        if index != positions.get(key, 0) or row["reference_id"] in references:
            raise nw.NotionWriteError("référence répétée ou liste discontinue")
        positions[key] = index + 1
        references[row["reference_id"]] = row
    if bundle["capture_sha256"] != nw._digest({
        k: bundle[k] for k in CAPTURE_FIELDS - {"capture_sha256"}
    }):
        raise nw.NotionWriteError("empreinte de capture de références divergente")
    return inventory, rows, references


def _validate_observation(entry: dict[str, Any], kind: str) -> None:
    fields = {"reference_id", "observed_at", "result"}
    result = entry.get("result")
    if result == "http":
        if (
            kind not in EXTERNAL or set(entry) != fields | {"status_code", "visibility"}
            or not nd._integer(entry["status_code"], 200, 599)
            or entry["visibility"] not in ("public", "unknown")
        ):
            raise nw.NotionWriteError("observation HTTP invalide")
    elif set(entry) != fields or result not in (
        "network_error", "missing_confirmed", "obsolete_confirmed",
    ):
        raise nw.NotionWriteError("observation non prise en charge")
    elif result == "network_error" and kind not in EXTERNAL:
        raise nw.NotionWriteError("limitation réseau inattendue pour cette référence")


def _observations(
    raw: object, capture_sha: str, references: dict[str, dict[str, Any]],
    captured_at: datetime, as_of: datetime,
) -> dict[str, dict[str, Any]]:
    if raw is None:
        return {}
    if (
        not isinstance(raw, dict) or set(raw) != {"schema", "capture_sha256", "entries"}
        or type(raw["schema"]) is not int or raw["schema"] != 1
        or raw["capture_sha256"] != capture_sha or not isinstance(raw["entries"], list)
        or len(raw["entries"]) > len(references)
    ):
        raise nw.NotionWriteError("observations incompatibles avec la capture de références")
    observed: dict[str, dict[str, Any]] = {}
    for entry in raw["entries"]:
        if not isinstance(entry, dict):
            raise nw.NotionWriteError("observation mal formée")
        ident = entry.get("reference_id")
        if not isinstance(ident, str) or ident not in references or ident in observed:
            raise nw.NotionWriteError("observation hors périmètre ou répétée")
        when = _utc(entry.get("observed_at"))
        if not captured_at <= when <= as_of:
            raise nw.NotionWriteError("observation hors fenêtre d'audit")
        _validate_observation(entry, references[ident]["kind"])
        observed[ident] = entry
    return observed


def _http_status(code: int, visibility: str) -> str:
    if 200 <= code < 300:
        return "http_reachable_observed"
    if 300 <= code < 400:
        return "http_redirect_unverified"
    if code in {401, 403}:
        return "access_restricted"
    if code in {404, 410}:
        return "broken_confirmed_public" if visibility == "public" else "absence_unconfirmed"
    if code in {408, 425, 429} or code >= 500:
        return "network_or_server_limited"
    return "http_result_unverified"


def _owning_page(ident: str, rows: nd.Rows) -> str:
    key = ("block", ident)
    while key[0] == "block":
        key = nd._parent_key(key[0], rows[key]["parent_id"], rows)
    return key[1]


def _status(
    row: dict[str, Any], rows: nd.Rows, observation: dict[str, Any] | None, as_of: datetime,
) -> str:
    if observation is not None:
        result = observation["result"]
        if result == "http":
            return _http_status(observation["status_code"], observation["visibility"])
        if result == "network_error":
            return "network_or_server_limited"
        return "obsolete_confirmed" if result == "obsolete_confirmed" else "broken_confirmed_manual"
    kind = row["kind"]
    target = row["target_id"]
    if kind in INTERNAL:
        categories = {
            "page_or_database": ("page", "database"), "local_block": ("block",),
        }.get(kind, (kind,))
        if not any((category, target) in rows for category in categories):
            return "outside_observed_inventory"
        expected_page = row["page_id"]
        if kind == "local_block":
            if row["source_category"] not in {"page", "block"}:
                return "not_verified"
            expected_page = (
                row["source_id"] if row["source_category"] == "page"
                else _owning_page(row["source_id"], rows)
            )
        if expected_page and _owning_page(target, rows) != expected_page:
            return "block_anchor_page_mismatch"
        return "present_in_inventory"
    if kind == "temporary_attachment":
        return ("temporary_url_expired" if _utc(row["expires_at"]) <= as_of
                else "temporary_url_unexpired_unverified")
    return "not_verified"


def audit(
    bundle: dict[str, Any], *, root_page: str, as_of: datetime, observations: object = None,
) -> dict[str, Any]:
    root_page = nw._id(root_page)
    as_of = _utc(as_of.isoformat())
    inventory, rows, references = _validated_bundle(bundle, root_page)
    captured_at = _utc(inventory["captured_at"])
    if as_of < captured_at:
        raise nw.NotionWriteError("audit antérieur à la capture")
    observed = _observations(observations, bundle["capture_sha256"], references, captured_at, as_of)
    findings = []
    for ident, row in references.items():
        observation = observed.get(ident)
        status = _status(row, rows, observation, as_of)
        findings.append({**row, "status": status, "observation": observation})
    report = {
        "schema": 1, "root_page": root_page, "classification": "private_local_only",
        "assessment": "NATIVE_REFERENCES_REVIEW_REQUIRED", "remote_write": False,
        "capture_sha256": bundle["capture_sha256"], "as_of": as_of.isoformat(),
        "coverage": {"inventory_objects": len(rows), "references": len(references),
                     "operator_observations": len(observed)},
        "counts_by_status": dict(sorted(Counter(f["status"] for f in findings).items())),
        "capture_limitations": inventory["limitations"], "audit_limitations": DEFAULT_LIMITS,
        "references": findings,
    }
    return {**report, "report_sha256": nw._digest(report)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inventorier et contrôler les références Notion")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("capture", "audit"):
        command = commands.add_parser(name)
        command.add_argument("--page", required=True)
        command.add_argument("--output", type=Path, required=True)
        if name == "audit":
            command.add_argument("--capture-file", type=Path, required=True)
            command.add_argument("--observations", type=Path)
            command.add_argument("--as-of")
    args = parser.parse_args(argv)
    try:
        output = nd._private_path(args.output)
        if output.exists():
            raise nw.NotionWriteError("la destination doit être un nouveau fichier")
        if args.command == "capture":
            result = capture_references(args.page)
        else:
            bundle = nd._load_snapshot(args.capture_file)
            if not isinstance(bundle, dict):
                raise nw.NotionWriteError("capture de références invalide")
            observed = nd._load_snapshot(args.observations) if args.observations is not None else None
            if args.observations is not None and observed is None:
                raise nw.NotionWriteError("observations JSON absentes")
            as_of = _utc(args.as_of) if args.as_of is not None else datetime.now(UTC)
            result = audit(bundle, root_page=args.page, as_of=as_of, observations=observed)
        nd._write_private_report(output, result)
    except nw.NotionWriteError as exc:
        print(f"NOTION_REFERENCES=REFUSED {exc}")
        return 2
    except (OSError, ValueError, RecursionError):
        print("NOTION_REFERENCES=REFUSED capture, observations ou destination illisibles")
        return 2
    print("NOTION_REFERENCES=CAPTURED" if args.command == "capture"
          else "NOTION_REFERENCES=REVIEW_REQUIRED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
