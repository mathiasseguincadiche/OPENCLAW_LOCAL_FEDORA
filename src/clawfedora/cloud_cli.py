"""Command line of the cloud route: status, key, activation, reconciliation, service unit.

The provider key is never taken from the command line (it would show in the process list and
the shell history): it is read from the standard input or from ``CLAWFEDORA_PROVIDER_KEY``.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from clawfedora.cloud_activation import (
    Check,
    disable,
    enable,
    fingerprint,
    key_path,
    render_unit,
    set_key,
)
from clawfedora.cloud_budget import BudgetRefused, load_ledger, month_key
from clawfedora.cloud_state import cloud_status, read_activation
from clawfedora.core_config import core_contract, resolve_runtime_root

KEY_ENVIRONMENT = "CLAWFEDORA_PROVIDER_KEY"


def _print_checks(checks: list[Check]) -> None:
    for check in checks:
        print(f"  [{'OK' if check.ok else 'ÉCHEC'}] {check.name}: {check.detail}")


def budget_lines(root: Path, runtime: Path) -> list[str]:
    ledger = load_ledger(runtime, root)
    summary = ledger.summary()
    lines = [
        f"CLOUD_BUDGET month={summary.month} spent_eur={summary.effective_eur:.2f} "
        f"cap_eur={summary.cap_eur:.0f} remaining_eur={summary.remaining_eur:.2f} "
        f"level={summary.level(ledger.alert_ratio)}",
        f"CLOUD_CALLS ok={summary.calls_ok} failed={summary.calls_failed} "
        f"uncertain={summary.calls_uncertain} pending={summary.pending}",
    ]
    if summary.billed_eur:
        lines.append(f"CLOUD_INVOICE declared_eur={summary.billed_eur:.2f}")
    return lines


def _status(root: Path, runtime: Path) -> int:
    ready, reason = cloud_status(runtime, root)
    print(f"CLOUD_STATUS ready={int(ready)} reason={reason}")
    try:
        key = key_path(root, runtime).read_text(encoding="utf-8").strip()
        print(f"CLOUD_KEY present=1 fingerprint={fingerprint(key)}")
    except OSError:
        print("CLOUD_KEY present=0")
    declared = read_activation(runtime).get("declared")
    if isinstance(declared, dict):
        print(f"CLOUD_DECLARED key_limit_usd={declared.get('key_limit_usd')} "
              f"verified_online={declared.get('verified_online')}")
    try:
        for line in budget_lines(root, runtime):
            print(line)
    except (BudgetRefused, OSError, ValueError) as exc:
        print(f"CLOUD_BUDGET error={exc}")
        return 2
    return 0


def _read_key() -> str:
    value = os.environ.get(KEY_ENVIRONMENT)
    if value is None and not sys.stdin.isatty():
        value = sys.stdin.readline()
    if not value or not value.strip():
        raise ValueError(f"clé absente: la fournir sur l'entrée standard ou dans {KEY_ENVIRONMENT}")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clawfedora.cloud_cli")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    key = commands.add_parser("set-key")
    key.add_argument("--replace", action="store_true")
    activate = commands.add_parser("enable")
    activate.add_argument("--key-limit-usd", type=float)
    activate.add_argument("--confirm-prepaid", action="store_true")
    activate.add_argument("--verify-online", action="store_true")
    activate.add_argument("--apply", action="store_true")
    commands.add_parser("disable")
    reconcile = commands.add_parser("reconcile")
    reconcile.add_argument("--eur", type=float, required=True)
    reconcile.add_argument("--month")
    reconcile.add_argument("--note", default="")
    unit = commands.add_parser("render-unit")
    unit.add_argument("--unit-root", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    runtime = resolve_runtime_root(args.runtime_root)
    try:
        if args.command == "status":
            return _status(root, runtime)
        if args.command == "set-key":
            path = set_key(root, runtime, _read_key(), replace=args.replace)
            print(f"CLOUD_KEY_RESULT=PASS path={path}")
            return 0
        if args.command == "enable":
            checks, activated = enable(
                root, runtime, key_limit_usd=args.key_limit_usd, prepaid=args.confirm_prepaid,
                verify_online=args.verify_online, apply=args.apply,
            )
            _print_checks(checks)
            if not all(check.ok for check in checks):
                print("CLOUD_ENABLE_RESULT=FAIL cloud reste désactivé")
                return 2
            if not activated:
                print("CLOUD_ENABLE_RESULT=DRY_RUN contrôles passés, rien d'activé (--apply)")
                return 0
            print("CLOUD_ENABLE_RESULT=PASS cloud activé")
            return 0
        if args.command == "disable":
            disable(runtime)
            print("CLOUD_DISABLE_RESULT=PASS cloud désactivé")
            return 0
        if args.command == "reconcile":
            ledger = load_ledger(runtime, root)
            limit = float(core_contract(root, "cloud_policy.yaml")["budget"]["monthly_cap_eur"])
            ledger.record_invoice(args.eur, args.month or month_key(time.time()), args.note)
            print(f"CLOUD_RECONCILE_RESULT=PASS declared_eur={args.eur:.2f} cap_eur={limit:.0f}")
            for line in budget_lines(root, runtime):
                print(line)
            return 0
        if args.command == "render-unit":
            print(f"CLOUD_UNIT={render_unit(root, runtime, args.unit_root.resolve())}")
            return 0
    except (BudgetRefused, OSError, ValueError, KeyError) as exc:
        print(f"CLOUD_RESULT=FAIL error={exc}")
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
