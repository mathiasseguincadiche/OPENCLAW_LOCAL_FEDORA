from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from clawfedora.core_config import resolve_runtime_root
from clawfedora.golden_projects import dry_run, run_golden_suite


def _root(value: str | None) -> Path:
    if value:
        return Path(value).expanduser().resolve()
    configured = os.environ.get("OPENCLAW_LOCAL_FEDORA_REPO")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clawfedora-golden",
        description="Gate L7: cinq Golden Projects + projet représentatif",
    )
    parser.add_argument("--root", help="racine du dépôt")
    parser.add_argument("--runtime-root", help="racine runtime/proofs")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = _root(args.root)
    try:
        if args.dry_run:
            payload = dry_run(repo_root)
            if args.json:
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                print(
                    "L7_DRY_RUN=PASS "
                    f"projects={payload['project_count']} tasks={payload['task_count']} "
                    "cloud=false remote_publication=false human_completion=false"
                )
            return 0
        runtime_root = resolve_runtime_root(args.runtime_root)
        code, report_path = run_golden_suite(repo_root, runtime_root)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print(f"L7_REPORT={report_path}")
            print(
                f"L7_RESULT={report['verdict']} "
                f"golden={report['golden_projects_pass']}/5 "
                f"representative={report['representative_projects_pass']}/1 "
                f"telemetry={report['telemetry']['events']} "
                f"finops_exposure_eur={report['finops']['net_exposure_eur']}"
            )
        return code
    except (FileNotFoundError, KeyError, OSError, PermissionError, ValueError) as exc:
        if args.json:
            print(json.dumps({"verdict": "FAIL", "error": str(exc)}, ensure_ascii=False))
        else:
            print(f"L7_RESULT=FAIL error={exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
