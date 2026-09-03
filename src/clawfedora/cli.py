from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from clawfedora.audit import collect_audit
from clawfedora.contracts import validate_repository


def _root_from_args(value: str | None) -> Path:
    if value:
        return Path(value).expanduser().resolve()
    env = os.environ.get("OPENCLAW_LOCAL_FEDORA_REPO")
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def _validate(root: Path, as_json: bool) -> int:
    try:
        report = validate_repository(root)
    except ValueError as exc:
        if as_json:
            print(json.dumps({"verdict": "FAIL", "failures": [str(exc)]}, ensure_ascii=False))
        else:
            print(f"FAIL contracts: {exc}")
        return 2

    if as_json:
        print(
            json.dumps(
                {
                    "verdict": "PASS" if report.ok else "FAIL",
                    "failures": list(report.failures),
                    "warnings": list(report.warnings),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        for warning in report.warnings:
            print(f"WARN {warning}")
        for failure in report.failures:
            print(f"FAIL {failure}")
        print(
            "CONTRACT_RESULT=PASS"
            if report.ok
            else f"CONTRACT_RESULT=FAIL failures={len(report.failures)}"
        )
    return 0 if report.ok else 2


def _audit(strict: bool, as_json: bool) -> int:
    report = collect_audit(strict=strict)
    if as_json:
        print(report.to_json())
    else:
        for check in report.checks:
            print(f"{check.status:<4} {check.id:<24} {check.detail}")
        print(
            f"AUDIT_RESULT={'PASS' if report.ok else 'FAIL'} "
            f"failures={report.failures} warnings={report.warnings}"
        )
    return 0 if report.ok else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clawfedora")
    parser.add_argument("--root", help="racine du dépôt")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="valider les contrats du dépôt")
    validate.add_argument("--json", action="store_true")

    audit = subparsers.add_parser("audit", help="auditer Fedora 44 et la B580")
    audit.add_argument("--strict", action="store_true", help="faire échouer les prérequis Fedora")
    audit.add_argument("--json", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = _root_from_args(args.root)
    if args.command == "validate":
        return _validate(root, bool(args.json))
    if args.command == "audit":
        return _audit(bool(args.strict), bool(args.json))
    parser.error(f"commande non supportée: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
