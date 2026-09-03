from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from clawfedora.core_config import resolve_runtime_root
from clawfedora.optimization import (
    compare_kernel,
    compare_model_challenger,
    compare_runtime,
    stage_ollama_artifacts,
    write_decision,
)
from clawfedora.optimization_contracts import validate_optimization_contracts


def _root(value: str | None) -> Path:
    if value:
        return Path(value).expanduser().resolve()
    env = os.environ.get("OPENCLAW_LOCAL_FEDORA_REPO")
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def _paths(values: list[str]) -> list[Path]:
    return [Path(value).expanduser().resolve() for value in values]


def _add_compare_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--baseline", action="append", required=True)
    parser.add_argument("--candidate", action="append", required=True)
    parser.add_argument("--output", required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clawfedora-l6")
    parser.add_argument("--root")
    parser.add_argument("--runtime-root")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate")
    validate.add_argument("--json", action="store_true")

    stage = sub.add_parser("stage-models")
    stage.add_argument("--apply", action="store_true")
    stage.add_argument("--json", action="store_true")

    runtime = sub.add_parser("compare-runtime")
    _add_compare_args(runtime)
    kernel = sub.add_parser("compare-kernel")
    _add_compare_args(kernel)
    challenger = sub.add_parser("compare-challenger")
    _add_compare_args(challenger)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = _root(args.root)
    runtime_root = resolve_runtime_root(args.runtime_root)

    if args.command == "validate":
        failures, warnings = validate_optimization_contracts(repo_root)
        if args.json:
            print(
                json.dumps(
                    {
                        "verdict": "PASS" if not failures else "FAIL",
                        "failures": list(failures),
                        "warnings": list(warnings),
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
        else:
            for warning in warnings:
                print(f"WARN {warning}")
            for failure in failures:
                print(f"FAIL {failure}")
            print(f"L6_CONTRACT_RESULT={'PASS' if not failures else 'FAIL'}")
        return 0 if not failures else 2

    if args.command == "stage-models":
        try:
            payload = stage_ollama_artifacts(
                repo_root,
                runtime_root,
                apply=bool(args.apply),
            )
        except (FileNotFoundError, OSError, ValueError) as exc:
            print(f"L6_STAGE_RESULT=FAIL error={exc}")
            return 2
        if args.json or not args.apply:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        print(f"L6_STAGE_RESULT=PASS apply={str(bool(args.apply)).lower()}")
        return 0

    baseline = _paths(args.baseline)
    candidate = _paths(args.candidate)
    try:
        if args.command == "compare-runtime":
            report = compare_runtime(repo_root, baseline, candidate)
        elif args.command == "compare-kernel":
            report = compare_kernel(repo_root, baseline, candidate)
        elif args.command == "compare-challenger":
            report = compare_model_challenger(repo_root, baseline, candidate)
        else:
            return 2
        output = write_decision(report, Path(args.output).expanduser().resolve())
    except (FileNotFoundError, KeyError, OSError, ValueError, ZeroDivisionError) as exc:
        print(f"L6_COMPARE_RESULT=FAIL error={exc}")
        return 2
    print(json.dumps(report.payload(), indent=2, ensure_ascii=False))
    print(f"L6_COMPARE_RESULT=PASS decision={output} verdict={report.verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
