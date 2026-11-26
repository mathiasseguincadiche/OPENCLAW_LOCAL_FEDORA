"""Read-only, bounded comparison of explicit facts in GitHub/Notion snapshots.

A matching reference is not evidence of technical truth. Never expose the values
or the contents of private documents in the generated report.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from clawfedora.document_impact import _relative, _safe
from clawfedora.structured_response import parse_response

MAX_FILES = 24
MAX_FILE = 160_000
MAX_TOTAL = 2_000_000
MAX_RULES = 40
KEY = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")
COMMIT = re.compile(r"[0-9a-f]{40}\Z")
FACT = re.compile(r"^(?:- )?Référence éditoriale \[([a-z][a-z0-9_.-]{0,63})\] : (.+)$")


def _read(root: Path, relative: str, limit: int = MAX_FILE) -> bytes:
    target = _safe(root, _relative(relative))
    if target is None or not target.is_file() or target.stat().st_size > limit:
        raise ValueError("source locale absente, liée ou hors limites")
    data = target.read_bytes()
    if len(data) > limit:
        raise ValueError("source locale trop volumineuse")
    return data


def _hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _text(raw: bytes) -> str:
    value = raw.decode("utf-8")
    if "\x00" in value:
        raise ValueError("source texte invalide")
    return value


def _manifest(root: Path, source: str) -> dict[str, Any]:
    raw = _read(root, source, 30_000)
    return parse_response(_text(raw), {"type": "object"})


def _sources(root: Path, spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entries = spec["sources"]
    if not isinstance(entries, list) or not 2 <= len(entries) <= MAX_FILES:
        raise ValueError("deux à vingt-quatre sources requises")
    output: dict[str, dict[str, Any]] = {}
    paths: set[str] = set()
    budget = 0
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {
            "id", "support", "visibility", "snapshot", "path", "sha256", "revision",
        }:
            raise ValueError("description de source invalide")
        ident, support = entry["id"], entry["support"]
        if (
            not isinstance(ident, str) or not KEY.fullmatch(ident) or ident in output
            or support not in {"github", "notion"}
            or entry["visibility"] not in {"public", "private"}
            or support == "notion" and entry["visibility"] != "private"
            or not isinstance(entry["sha256"], str) or not SHA.fullmatch(entry["sha256"])
        ):
            raise ValueError("identité, visibilité ou empreinte de source invalide")
        snapshot = _relative(entry["snapshot"])
        relative = _relative(entry["path"])
        full = snapshot + "/" + relative
        if full in paths or not relative.endswith(".md"):
            raise ValueError("source Markdown unique requise")
        paths.add(full)
        provenance = _manifest(root, snapshot + "/.source-provenance.json")
        if provenance.get("provider") != support or provenance.get("read_only") is not True:
            raise ValueError("provenance du snapshot invalide")
        revision = entry["revision"]
        if support == "github":
            if (
                not isinstance(revision, str) or not COMMIT.fullmatch(revision)
                or provenance.get("commit") != revision
            ):
                raise ValueError("commit GitHub divergent")
        else:
            pages = provenance.get("pages")
            if (
                not isinstance(revision, str) or not revision
                or provenance.get("captured_at") != revision
                or provenance.get("classification") != "private_local_only"
                or not isinstance(pages, list)
                or not any(isinstance(p, dict) and relative == f"page-{p.get('id')}.md"
                           for p in pages)
            ):
                raise ValueError("capture Notion divergente")
        raw = _read(root, full)
        budget += len(raw)
        if budget > MAX_TOTAL or _hash(raw) != entry["sha256"]:
            raise ValueError("budget dépassé ou source modifiée depuis sélection")
        output[ident] = {**entry, "body": _text(raw)}
    if {row["support"] for row in output.values()} != {"github", "notion"}:
        raise ValueError("les deux supports sont requis")
    return output


def _rules(spec: dict[str, Any]) -> dict[str, str]:
    rules = spec["facts"]
    if not isinstance(rules, dict) or not 1 <= len(rules) <= MAX_RULES:
        raise ValueError("registre de faits vide ou trop volumineux")
    result: dict[str, str] = {}
    for key, value in rules.items():
        if not KEY.fullmatch(key) or value not in {"shared", "private"}:
            raise ValueError("classification de fait invalide")
        result[key] = value
    return result


def _observations(sources: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    facts: dict[str, list[dict[str, Any]]] = {}
    count = 0
    for ident, row in sources.items():
        fence = ""
        for line_no, line in enumerate(row["body"].splitlines(), 1):
            # Examples inside fenced code are not project assertions.
            match = re.match(r"^\s*(`{3,}|~{3,})", line)
            if match:
                delimiter = match.group(1)
                if not fence:
                    fence = delimiter
                elif delimiter[0] == fence[0] and len(delimiter) >= len(fence):
                    fence = ""
                continue
            if fence:
                continue
            fact = FACT.fullmatch(line.strip())
            if fact is None:
                continue
            key, value = fact.groups()
            if not value.strip() or len(value) > 400:
                raise ValueError("valeur de référence vide ou trop longue")
            count += 1
            if count > 200:
                raise ValueError("trop de références déclarées")
            facts.setdefault(key, []).append({
                "source": ident, "line": line_no, "support": row["support"],
                "visibility": row["visibility"], "value": value.strip(),
            })
    return facts


def _locations(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"source": item["source"], "line": item["line"]} for item in rows]


def inspect(root: Path, manifest: str) -> dict[str, Any]:
    if not root.is_dir() or any(p.is_symlink() for p in (root, *root.parents)):
        raise ValueError("dossier local non lié requis")
    root = root.resolve(strict=True)
    spec = _manifest(root, manifest)
    if set(spec) != {"schema", "sources", "facts"} or spec["schema"] != 1:
        raise ValueError("contrat de cohérence inconnu")
    sources = _sources(root, spec)
    rules = _rules(spec)
    observed = _observations(sources)
    findings: list[dict[str, Any]] = []
    for key in sorted(rules.keys() | observed.keys()):
        rows = observed.get(key, [])
        locations = _locations(rows)
        if key not in rules:
            findings.append({"code": "UNCLASSIFIED_FACT", "key": key, "locations": locations})
            continue
        private = rules[key] == "private"
        if private:
            public = [row for row in rows if row["visibility"] == "public"]
            # Exact literal check only; no secret values are emitted.
            values = {row["value"] for row in rows if row["visibility"] == "private"}
            hits = [
                {"source": ident, "line": index}
                for ident, source in sources.items() if source["visibility"] == "public"
                for index, line in enumerate(source["body"].splitlines(), 1)
                if any(len(value) >= 12 and value.casefold() in line.casefold()
                       for value in values)
            ]
            if public or hits:
                findings.append({"code": "PRIVATE_FACT_EXPOSURE", "key": key,
                                 "locations": _locations(public) + hits[:50]})
            if not values:
                findings.append({"code": "PRIVATE_REFERENCE_MISSING", "key": key,
                                 "locations": locations})
        else:
            supports = {row["support"] for row in rows}
            if supports != {"github", "notion"}:
                findings.append({"code": "SHARED_REFERENCE_MISSING", "key": key,
                                 "locations": locations})
        if len({row["value"] for row in rows}) > 1:
            findings.append({"code": "REFERENCE_DIVERGENCE", "key": key,
                             "locations": locations})
    return {
        "assessment": "REVIEW_REQUIRED" if findings else "DECLARED_REFERENCES_ALIGNED",
        "sources": [{"id": ident, "support": row["support"], "sha256": row["sha256"]}
                    for ident, row in sources.items()],
        "facts_checked": len(rules), "findings": findings,
        "limitations": [
            "Comparaison littérale de références déclarées, pas audit sémantique.",
            "Visibilité déclarée par opérateur, droits réels non vérifiés.",
            "Provenance locale et SHA-256, pas authentification distante.",
            "Médias, bases Notion, liens et preuves d'exécution non certifiés.",
            "Aucune modification, publication, synchronisation ou requête distante.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Contrôle local GitHub / Notion")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", required=True, help="Chemin relatif au dossier local")
    args = parser.parse_args(argv)
    try:
        result = inspect(args.root, args.manifest)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"assessment": "REFUSED", "reason": type(exc).__name__}))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["findings"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
