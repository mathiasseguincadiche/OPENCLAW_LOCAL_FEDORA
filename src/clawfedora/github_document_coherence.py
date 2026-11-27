"""Compare selected technical and documentary facts at one immutable Git revision."""
from __future__ import annotations

import argparse
import json
import re
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from markdown_it import MarkdownIt
from yaml.nodes import MappingNode, ScalarNode

from clawfedora import github_document_inventory as inv
from clawfedora import github_document_links as links
from clawfedora import source_connectors as sources
from clawfedora.notion_inventory_diff import _json_object, _private_path, _write_private_report
from clawfedora.notion_write import _digest

DEFAULT_CONTRACT = ".github/clawfedora-doc-contract.json"
MAX_RULES = 40
MAX_READ = 4_000_000
KEY = re.compile(r"[a-z][a-z0-9_.-]{0,63}")
VERSION = re.compile(r"v?[0-9][0-9A-Za-z.+_-]{0,78}")
MODES = {"text", "json", "toml", "yaml", "markdown_table"}


def _path(value: object) -> str:
    if not isinstance(value, str):
        raise inv.InventoryError("chemin de contrat invalide")
    path, _ = inv._path(value)
    if path is None:
        raise inv.InventoryError("chemin de contrat hors périmètre")
    return path.as_posix()


def _selector(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) != {"path", "format", "select"}:
        raise inv.InventoryError("sélecteur de version invalide")
    mode, parts = raw["format"], raw["select"]
    if (
        not isinstance(mode, str) or mode not in MODES or not isinstance(parts, list)
        or len(parts) > 8 or any(not isinstance(part, str) or not 0 < len(part) <= 120
                                 or inv.CONTROL.search(part) for part in parts)
        or (mode == "text" and parts) or (mode != "text" and not parts)
        or (mode == "markdown_table" and len(parts) != 2)
    ):
        raise inv.InventoryError("format ou champ de version invalide")
    return {"path": _path(raw["path"]), "format": mode, "select": parts}


def _rules(raw: object) -> list[dict[str, Any]]:
    if (
        not isinstance(raw, dict) or set(raw) != {"schema", "checks"}
        or type(raw["schema"]) is not int or raw["schema"] != 1
        or not isinstance(raw["checks"], list) or not 1 <= len(raw["checks"]) <= MAX_RULES
    ):
        raise inv.InventoryError("contrat documentaire invalide")
    known = set()
    rules = []
    for row in raw["checks"]:
        if not isinstance(row, dict):
            raise inv.InventoryError("règle documentaire invalide")
        ident, kind = row.get("id"), row.get("kind")
        if not isinstance(ident, str) or not KEY.fullmatch(ident) or ident in known:
            raise inv.InventoryError("identifiant de règle invalide ou répété")
        known.add(ident)
        if kind == "version" and set(row) == {"id", "kind", "authority", "declarations"}:
            declarations = row["declarations"]
            if not isinstance(declarations, list) or not 1 <= len(declarations) <= 8:
                raise inv.InventoryError("une à huit déclarations par version requises")
            rules.append({
                "id": ident, "kind": kind, "authority": _selector(row["authority"]),
                "declarations": [_selector(entry) for entry in declarations],
            })
        elif kind == "path" and set(row) == {"id", "kind", "document", "target"}:
            document = _path(row["document"])
            if not links._markdown(document):
                raise inv.InventoryError("source Markdown requise pour un chemin technique")
            rules.append({"id": ident, "kind": kind, "document": document,
                          "target": _path(row["target"])})
        else:
            raise inv.InventoryError("type ou paramètres de contrôle non pris en charge")
    return rules


def _field(value: object, parts: list[str]) -> object:
    for part in parts:
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _yaml_scalar(content: str, parts: list[str]) -> str | None:
    node = yaml.compose(content, Loader=yaml.SafeLoader)
    for name in parts:
        if not isinstance(node, MappingNode):
            return None
        matches = [
            val for key, val in node.value if isinstance(key, ScalarNode) and key.value == name
        ]
        if len(matches) > 1:
            raise ValueError("clé YAML répétée")
        node = matches[0] if matches else None
    return node.value if isinstance(node, ScalarNode) and node.tag.endswith(":str") else None


def _table_version(content: str, heading: str, label: str) -> tuple[object, int | None]:
    tokens = MarkdownIt("commonmark").enable("table").parse(content)
    headings: list[tuple[int, str]] = []
    matches = []
    for i, token in enumerate(tokens):
        if token.type == "heading_open":
            level = int(token.tag[1:])
            headings = [item for item in headings if item[0] < level]
            headings.append((level, tokens[i + 1].content.strip()))
        if token.type != "tr_open" or heading not in {item[1] for item in headings}:
            continue
        cells = []
        for cell in tokens[i + 1:]:
            if cell.type == "tr_close":
                break
            if cell.type == "inline":
                cells.append(cell)
        if len(cells) >= 2 and cells[0].content.strip() == label:
            values = [part.content for part in (cells[1].children or [])
                      if part.type == "code_inline"]
            line = token.map[0] + 1 if token.map else None
            matches.append((values[0] if values else None, line))
    if len(matches) > 1:
        raise ValueError("ligne documentaire répétée dans le périmètre")
    return matches[0] if matches else (None, None)


def _version(content: str, mode: str, selector: list[str]) -> tuple[object, int | None]:
    if mode == "markdown_table":
        return _table_version(content, *selector)
    if mode == "text":
        return content.strip(), 1
    if mode == "yaml":
        return _yaml_scalar(content, selector), None
    root = (tomllib.loads(content) if mode == "toml"
            else json.loads(content, object_pairs_hook=_json_object))
    return _field(root, selector), None


def _path_mentions(content: str, target: str) -> list[int]:
    lines = set()
    for token in MarkdownIt().parse(content):
        if token.map is None:
            continue
        if token.type == "fence" and token.info.split()[:1] in (
            ["bash"], ["sh"], ["shell"], ["zsh"], ["console"],
        ):
            candidates = [
                (token.map[0] + offset + 2, item.strip().removeprefix("$ "))
                for offset, item in enumerate(token.content.splitlines())
            ]
        else:
            candidates = [(token.map[0] + 1, child.content.strip())
                          for child in token.children or [] if child.type == "code_inline"]
        for line, candidate in candidates:
            literal = candidate.split(maxsplit=1)
            if literal and literal[0].removeprefix("./") == target:
                lines.add(line)
    return sorted(lines)


class Audit:
    def __init__(self, inventory: dict[str, Any], blob: Callable[[str], bytes | None]) -> None:
        self.inventory = inventory
        self.blob = blob
        self.files = {item["path"]: item["git_blob"] for item in inventory["files"]}
        self.cache: dict[str, str | None] = {}
        self.read_bytes = 0

    def read(self, path: str) -> str | None:
        sha = self.files.get(path)
        if sha is None:
            return None
        if sha not in self.cache:
            data = self.blob(sha)
            text = None
            if data is not None:
                self.read_bytes += len(data)
                if self.read_bytes > MAX_READ:
                    raise inv.InventoryError("budget de lecture du contrat dépassé")
                links._check_blob(data, sha)
                try:
                    decoded = data.decode("utf-8-sig")
                    if "\0" not in decoded:
                        text = decoded
                except UnicodeError:
                    pass
            self.cache[sha] = text
        return self.cache[sha]

    def observation(self, selector: dict[str, Any]) -> dict[str, Any]:
        path = selector["path"]
        result = {"path": path, "git_blob": self.files.get(path), "format": selector["format"],
                  "select": selector["select"]}
        content = self.read(path)
        if content is None:
            state = "content_not_checked" if path in self.files else "missing_path"
            return {**result, "status": state}
        try:
            value, line = _version(content, selector["format"], selector["select"])
        except (ValueError, yaml.YAMLError, RecursionError):
            return {**result, "status": "ambiguous_or_invalid"}
        if not isinstance(value, str) or not VERSION.fullmatch(value):
            return {**result, "status": "version_not_observed"}
        return {**result, "status": "observed", "value": value, "line": line}

    def compare(self, rule: dict[str, Any]) -> dict[str, Any]:
        base = {"id": rule["id"], "kind": rule["kind"]}
        if rule["kind"] == "path":
            document, target = rule["document"], rule["target"]
            content = self.read(document)
            locations = _path_mentions(content, target) if content is not None else []
            status = "match"
            if content is None:
                status = "not_verified" if document in self.files else "missing_document"
            elif not locations:
                status = "mention_not_observed"
            elif target not in self.files:
                status = "missing_technical_path"
            return {**base, "status": status, "document": document, "target": target,
                    "lines": locations[:80], "location_count": len(locations),
                    "document_blob": self.files.get(document),
                    "target_blob": self.files.get(target)}
        authority = self.observation(rule["authority"])
        declarations = [self.observation(item) for item in rule["declarations"]]
        for item in declarations:
            if item["status"] == authority["status"] == "observed":
                item["comparison"] = (
                    "match" if item["value"] == authority["value"] else "version_drift"
                )
            else:
                item["comparison"] = "not_verified"
        outcomes = {item["comparison"] for item in declarations}
        if "version_drift" in outcomes:
            status = "version_drift"
        elif "missing_path" in {item["status"] for item in [authority, *declarations]}:
            status = "missing_version_path"
        else:
            status = "not_verified" if "not_verified" in outcomes else "match"
        return {**base, "status": status, "authority": authority, "declarations": declarations}



def _audit(inventory: dict[str, Any], blob: Callable[[str], bytes | None],
           contract: str, expected_inventory: str | None) -> dict[str, Any]:
    links._require_inventory(inventory, expected_inventory)
    audit = Audit(inventory, blob)
    contract = _path(contract)
    text = audit.read(contract)
    if text is None:
        raise inv.InventoryError("contrat documentaire absent ou illisible au commit")
    rules = _rules(json.loads(text, object_pairs_hook=_json_object))
    checks = [audit.compare(rule) for rule in sorted(rules, key=lambda rule: rule["id"])]
    counts = Counter(row["status"] for row in checks)
    report = {
        "schema": 1, "classification": inv.CLASSIFICATION,
        "assessment": "GIT_DOCUMENTARY_COHERENCE_REVIEW_REQUIRED",
        "repository": inventory["repository"], "commit": inventory["commit"],
        "git_tree": inventory["git_tree"], "inventory_sha256": inventory["inventory_sha256"],
        "contract_path": contract, "contract_blob": audit.files[contract],
        "counts_by_status": dict(sorted(counts.items())), "checks": checks,
        "limits": ["explicit_rules_only", "declared_values_only", "no_command_execution",
                   "no_runtime_or_installation_verification"],
    }
    return {**report, "report_sha256": _digest(report)}


def audit_local(root: Path, commit: str, contract: str = DEFAULT_CONTRACT, *,
                expected_inventory: str | None = None) -> dict[str, Any]:
    tree, entries = inv._local_tree(root, commit)
    inventory = inv._inventory(commit, tree, entries)
    return _audit(inventory, lambda sha: links._local_blob(root, sha), contract, expected_inventory)


def audit_github(repository: str, commit: str, contract: str = DEFAULT_CONTRACT, *,
                 expected_inventory: str | None = None) -> dict[str, Any]:
    inventory = inv.inventory_github(repository, commit)
    return _audit(inventory, lambda sha: links._github_blob(repository, sha),
                  contract, expected_inventory)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Contrôler la cohérence documentaire d'un commit")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--path", type=Path)
    source.add_argument("--github")
    parser.add_argument("--commit", required=True)
    parser.add_argument("--contract", default=DEFAULT_CONTRACT)
    parser.add_argument("--inventory-sha256")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        output = _private_path(args.output)
        if output.exists():
            raise inv.InventoryError("la destination doit être un fichier neuf")
        if args.path is None:
            result = audit_github(args.github, args.commit, args.contract,
                                  expected_inventory=args.inventory_sha256)
        else:
            result = audit_local(args.path, args.commit, args.contract,
                                 expected_inventory=args.inventory_sha256)
        size = len(json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8")) + 1
        if size > inv.MAX_REPORT_BYTES:
            raise inv.InventoryError("rapport de cohérence trop volumineux")
        _write_private_report(output, result)
    except (inv.InventoryError, sources.SourceImportError) as exc:
        print(f"GITHUB_DOCUMENTARY_COHERENCE=REFUSED {exc}")
        return 2
    except (OSError, ValueError, RecursionError):
        print("GITHUB_DOCUMENTARY_COHERENCE=REFUSED entrée ou destination illisible")
        return 2
    counts = result["counts_by_status"]
    pending = len(result["checks"]) - counts.get("match", 0)
    print(f"GITHUB_DOCUMENTARY_COHERENCE=REVIEW_REQUIRED pending={pending}")
    return 1 if pending else 0


if __name__ == "__main__":
    raise SystemExit(main())
