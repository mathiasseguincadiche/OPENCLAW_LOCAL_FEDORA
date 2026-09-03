from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from clawfedora.core_config import resolve_runtime_root
from clawfedora.finops import append_cost_event, summarize
from clawfedora.lifecycle import cleanup_managed, collect_health, create_backup, model_plan, restore_backup
from clawfedora.lifecycle_contracts import validate_lifecycle_contracts
from clawfedora.telemetry import emit_event, read_events


def _root(value: str | None) -> Path:
    return Path(value).expanduser().resolve() if value else Path(__file__).resolve().parents[2]


def _models(repo_root: Path, apply: bool) -> int:
    plan = model_plan(repo_root)
    if not apply:
        print(json.dumps({"verdict": "PLAN", "models": plan}, indent=2, ensure_ascii=False))
        return 0
    for item in plan:
        completed = subprocess.run(
            ["ollama", "pull", str(item["runtime_id"])],
            check=False,
        )
        if completed.returncode != 0:
            print(f"MODEL_PROVISION_RESULT=FAIL model={item['runtime_id']}")
            return 2
    print(f"MODEL_PROVISION_RESULT=PASS count={len(plan)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clawfedora-ops")
    parser.add_argument("--root")
    parser.add_argument("--runtime-root")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate-lifecycle")
    sub.add_parser("health")
    models = sub.add_parser("models")
    models.add_argument("--apply", action="store_true")
    backup = sub.add_parser("backup")
    backup.add_argument("--output-dir")
    restore = sub.add_parser("restore")
    restore.add_argument("archive")
    restore.add_argument("destination")
    cleanup = sub.add_parser("cleanup")
    cleanup.add_argument("--apply", action="store_true")
    cleanup.add_argument("--purge-data", action="store_true")
    telemetry = sub.add_parser("telemetry")
    telemetry.add_argument("--event")
    telemetry.add_argument("--agent-id")
    telemetry.add_argument("--project-id")
    telemetry.add_argument("--status")
    telemetry.add_argument("--show", action="store_true")
    finops = sub.add_parser("finops")
    finops.add_argument("--event", choices=("reservation", "charge", "release", "refund"))
    finops.add_argument("--amount-eur", type=float, default=0.0)
    finops.add_argument("--reason")
    finops.add_argument("--provider")
    finops.add_argument("--project-id")
    finops.add_argument("--show", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = _root(args.root)
    runtime_root = resolve_runtime_root(args.runtime_root)
    if args.command == "validate-lifecycle":
        failures, warnings = validate_lifecycle_contracts(repo_root)
        for warning in warnings:
            print(f"WARN {warning}")
        for failure in failures:
            print(f"FAIL {failure}")
        print(f"LIFECYCLE_CONTRACT_RESULT={'PASS' if not failures else 'FAIL'}")
        return 0 if not failures else 2
    if args.command == "health":
        report = collect_health(repo_root, runtime_root)
        print(json.dumps(report.payload(), indent=2, ensure_ascii=False))
        return 0 if report.ok else 2
    if args.command == "models":
        return _models(repo_root, bool(args.apply))
    if args.command == "backup":
        output = Path(args.output_dir).expanduser() if args.output_dir else None
        path = create_backup(runtime_root, output)
        print(f"BACKUP_RESULT=PASS path={path}")
        return 0
    if args.command == "restore":
        path = restore_backup(Path(args.archive).expanduser(), Path(args.destination).expanduser())
        print(f"RESTORE_RESULT=PASS path={path}")
        return 0
    if args.command == "cleanup":
        if not args.apply:
            print("CLEANUP_PLAN=managed-workspaces,managed-venv" + (",data" if args.purge_data else ""))
            return 0
        removed = cleanup_managed(runtime_root, purge_data=bool(args.purge_data))
        print(f"CLEANUP_RESULT=PASS removed={len(removed)}")
        return 0
    if args.command == "telemetry":
        if args.show:
            print(json.dumps(read_events(repo_root, runtime_root), indent=2, ensure_ascii=False))
            return 0
        if not args.event:
            raise SystemExit("telemetry: --event requis hors --show")
        fields = {
            key: value
            for key, value in {
                "agent_id": args.agent_id,
                "project_id": args.project_id,
                "status": args.status,
            }.items()
            if value is not None
        }
        path = emit_event(repo_root, runtime_root, args.event, **fields)
        print(f"TELEMETRY_RESULT=PASS path={path}")
        return 0
    if args.command == "finops":
        if args.show:
            print(json.dumps(summarize(repo_root, runtime_root), indent=2, ensure_ascii=False))
            return 0
        if not args.event or not args.reason or not args.provider:
            raise SystemExit("finops: --event --reason --provider requis hors --show")
        payload = append_cost_event(
            repo_root,
            runtime_root,
            event=args.event,
            amount_eur=float(args.amount_eur),
            reason=args.reason,
            provider=args.provider,
            project_id=args.project_id,
        )
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
