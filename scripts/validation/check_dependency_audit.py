"""Turn a raw dependency audit into a verdict: new serious advisories fail, reviewed ones pass.

Standard library only. ``npm`` reads ``npm audit --json``; ``python`` reads ``pip-audit -f json``.
High and critical npm advisories, and every Python advisory (pip-audit gives no severity),
must appear in config/dependency_audit_exceptions.json with a reason and an expiry date. An
expired exception fails too: a residual risk is re-reviewed, never forgotten. Moderate npm
advisories are reported without failing. An unreadable report always fails (fail closed).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EXCEPTIONS = ROOT / "config/dependency_audit_exceptions.json"
SERIOUS = {"high", "critical"}
RANK = {"info": 0, "low": 1, "moderate": 2, "high": 3, "critical": 4}


def load_exceptions(path: Path = EXCEPTIONS) -> dict[tuple[str, str], dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != 1 or not isinstance(data.get("exceptions"), list):
        raise ValueError("fichier d'exceptions invalide")
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for item in data["exceptions"]:
        if not isinstance(item, dict) or item.get("ecosystem") not in {"npm", "python"}:
            raise ValueError("exception invalide")
        for field in ("id", "package", "reason", "reviewed", "expires", "doc"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise ValueError(f"exception incomplète: {field}")
        dt.date.fromisoformat(item["reviewed"])
        dt.date.fromisoformat(item["expires"])
        key = (item["ecosystem"], item["id"])
        if key in result:
            raise ValueError(f"exception dupliquée: {item['id']}")
        result[key] = item
    return result


def npm_advisories(report: dict[str, Any]) -> list[dict[str, str]]:
    vulnerabilities = report.get("vulnerabilities")
    if not isinstance(vulnerabilities, dict) or not isinstance(report.get("metadata"), dict):
        raise ValueError("rapport npm audit illisible")
    found: dict[str, dict[str, str]] = {}
    for entry in vulnerabilities.values():
        for via in entry.get("via", []) if isinstance(entry, dict) else []:
            if isinstance(via, dict) and isinstance(via.get("url"), str):
                advisory = via["url"].rstrip("/").rsplit("/", 1)[-1]
                severity = str(via.get("severity", "unknown")).lower()
                # An unknown severity counts as critical: never under-rate an advisory.
                rank = RANK.get(severity, RANK["critical"])
                known = found.get(advisory)
                if known is None or rank > RANK.get(known["severity"], RANK["critical"]):
                    found[advisory] = {
                        "id": advisory, "package": str(via.get("name", "?")),
                        "severity": severity if severity in RANK else "critical",
                        "title": str(via.get("title", ""))[:120],
                    }
    return sorted(found.values(), key=lambda item: item["id"])


def python_advisories(report: Any) -> list[dict[str, str]]:
    dependencies = report.get("dependencies") if isinstance(report, dict) else None
    if not isinstance(dependencies, list):
        raise ValueError("rapport pip-audit illisible")
    found: list[dict[str, str]] = []
    for dependency in dependencies:
        for vuln in dependency.get("vulns", []) if isinstance(dependency, dict) else []:
            entry = {
                "id": str(vuln.get("id", "?")), "package": str(dependency.get("name", "?")),
                # pip-audit reports no severity: every Python advisory is treated as serious.
                "severity": "unrated",
                "title": ", ".join(str(v) for v in vuln.get("fix_versions", []))[:120],
            }
            # The same artifact may be listed by several lock files: report it once.
            if entry not in found:
                found.append(entry)
    return sorted(found, key=lambda item: item["id"])


def verdict(
    ecosystem: str, advisories: list[dict[str, str]],
    exceptions: dict[tuple[str, str], dict[str, Any]], today: dt.date,
) -> tuple[bool, list[str]]:
    lines: list[str] = []
    ok = True
    present = set()
    for advisory in advisories:
        serious = ecosystem == "python" or advisory["severity"] in SERIOUS
        key = (ecosystem, advisory["id"])
        present.add(key)
        exception = exceptions.get(key)
        label = f"{advisory['severity']} {advisory['id']} {advisory['package']}"
        if not serious:
            lines.append(f"INFO {label} (modéré : signalé, non bloquant)")
        elif exception is None:
            ok = False
            lines.append(f"NOUVEAU {label} : à analyser — {advisory['title']}")
        elif dt.date.fromisoformat(exception["expires"]) < today:
            ok = False
            lines.append(f"EXPIRÉ {label} : exception du {exception['reviewed']} à revoir")
        else:
            lines.append(f"REVU {label} jusqu'au {exception['expires']} ({exception['doc']})")
    for key, exception in sorted(exceptions.items()):
        if key[0] == ecosystem and key not in present:
            lines.append(f"CORRIGÉ {exception['id']} : l'exception peut être retirée")
    return ok, lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ecosystem", choices=("npm", "python"))
    parser.add_argument("report", type=Path)
    parser.add_argument("--exceptions", type=Path, default=EXCEPTIONS)
    parser.add_argument("--today", type=dt.date.fromisoformat, default=dt.date.today())
    args = parser.parse_args(argv)
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        advisories = (
            npm_advisories(report) if args.ecosystem == "npm" else python_advisories(report)
        )
        ok, lines = verdict(args.ecosystem, advisories, load_exceptions(args.exceptions),
                            args.today)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        print(f"DEPENDENCY_AUDIT_RESULT=REFUSED {args.ecosystem}: {exc}")
        return 2
    for line in lines:
        print(line)
    print(f"DEPENDENCY_AUDIT_RESULT={'PASS' if ok else 'FAIL'} {args.ecosystem} "
          f"advisories={len(advisories)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
