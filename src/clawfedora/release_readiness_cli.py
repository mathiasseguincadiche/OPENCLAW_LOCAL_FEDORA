from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from clawfedora.core_config import resolve_runtime_root
from clawfedora.release_readiness import approve_release, dry_run, write_readiness_report
from clawfedora.release_readiness_contracts import validate_release_readiness_contracts


def _root(value: str | None) -> Path:
    if value:
        return Path(value).expanduser().resolve()
    env = os.environ.get("OPENCLAW_LOCAL_FEDORA_REPO")
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clawfedora-l8",
        description="Gate L8: release readiness puis approbation humaine explicite",
    )
    parser.add_argument("--root", help="racine du dépôt")
    parser.add_argument("--runtime-root", help="racine runtime/proofs")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate")
    validate.add_argument("--json", action="store_true")

    dry = sub.add_parser("dry-run")
    dry.add_argument("--json", action="store_true")

    check = sub.add_parser("check")
    check.add_argument("--json", action="store_true")

    approve = sub.add_parser("approve")
    approve.add_argument("--report", required=True)
    approve.add_argument("--approver", required=True)
    approve.add_argument("--acknowledge-v1", action="store_true")
    approve.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = _root(args.root)
    runtime_root = resolve_runtime_root(args.runtime_root)

    if args.command == "validate":
        failures, warnings = validate_release_readiness_contracts(repo_root)
        payload = {
            "verdict": "PASS" if not failures else "FAIL",
            "failures": list(failures),
            "warnings": list(warnings),
        }
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            for warning in warnings:
                print(f"WARN {warning}")
            for failure in failures:
                print(f"FAIL {failure}")
            print(f"L8_CONTRACT_RESULT={'PASS' if not failures else 'FAIL'}")
        return 0 if not failures else 2

    if args.command == "dry-run":
        try:
            payload = dry_run(repo_root)
        except (FileNotFoundError, KeyError, OSError, ValueError) as exc:
            if args.json:
                print(json.dumps({"verdict": "FAIL", "error": str(exc)}, ensure_ascii=False))
            else:
                print(f"L8_DRY_RUN_RESULT=FAIL error={exc}")
            return 2
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(
                "L8_DRY_RUN_RESULT=PASS "
                f"required_gates={len(payload['required_gates'])} "
                f"l6_decisions={len(payload['required_l6_decisions'])}"
            )
        return 0

    if args.command == "check":
        try:
            code, path = write_readiness_report(repo_root, runtime_root)
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, KeyError, OSError, ValueError) as exc:
            if args.json:
                print(json.dumps({"verdict": "FAIL", "error": str(exc)}, ensure_ascii=False))
            else:
                print(f"L8_READINESS=BLOCKED error={exc}")
            return 2
        if args.json:
            payload["report"] = str(path)
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(f"REPORT={path}")
            print(
                f"L8_READINESS={payload['verdict']} "
                f"failures={len(payload.get('failures', []))}"
            )
        return code

    if args.command == "approve":
        try:
            path = approve_release(
                repo_root,
                runtime_root,
                Path(args.report).expanduser(),
                approver=str(args.approver),
                acknowledge=bool(args.acknowledge_v1),
            )
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, KeyError, OSError, PermissionError, ValueError) as exc:
            if args.json:
                print(json.dumps({"verdict": "BLOCKED", "error": str(exc)}, ensure_ascii=False))
            else:
                print(f"L8_APPROVAL=BLOCKED error={exc}")
            return 2
        if args.json:
            payload["approval_record"] = str(path)
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(f"APPROVAL_RECORD={path}")
            print("L8_APPROVAL=APPROVED_FOR_V1_PREPARATION")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
