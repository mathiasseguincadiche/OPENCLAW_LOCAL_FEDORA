from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from clawfedora.agents import deploy_workspaces, validate_agent_assets
from clawfedora.audit import collect_audit
from clawfedora.contracts import validate_repository
from clawfedora.core_config import resolve_runtime_root
from clawfedora.core_contracts import validate_core_contracts
from clawfedora.openclaw_config import build_openclaw_patch, write_openclaw_patch


def _root_from_args(value: str | None) -> Path:
    if value:
        return Path(value).expanduser().resolve()
    env = os.environ.get("OPENCLAW_LOCAL_FEDORA_REPO")
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def _validate(root: Path, as_json: bool) -> int:
    failures: list[str] = []
    warnings: list[str] = []
    try:
        report = validate_repository(root)
        failures.extend(report.failures)
        warnings.extend(report.warnings)
        core_failures, core_warnings = validate_core_contracts(root)
        failures.extend(core_failures)
        warnings.extend(core_warnings)
    except (FileNotFoundError, ValueError) as exc:
        failures.append(str(exc))

    if as_json:
        print(
            json.dumps(
                {
                    "verdict": "PASS" if not failures else "FAIL",
                    "failures": failures,
                    "warnings": warnings,
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
        if failures:
            print(f"CONTRACT_RESULT=FAIL failures={len(failures)}")
        else:
            print("CONTRACT_RESULT=PASS")
    return 0 if not failures else 2


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


def _agents_validate(root: Path, as_json: bool) -> int:
    failures = list(validate_agent_assets(root))
    if as_json:
        print(
            json.dumps(
                {"verdict": "PASS" if not failures else "FAIL", "failures": failures},
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        for failure in failures:
            print(f"FAIL {failure}")
        if failures:
            print(f"AGENTS_RESULT=FAIL failures={len(failures)}")
        else:
            print("AGENTS_RESULT=PASS")
    return 0 if not failures else 2


def _agents_deploy(root: Path, runtime_value: str | None, as_json: bool) -> int:
    runtime_root = resolve_runtime_root(runtime_value)
    try:
        deployed = deploy_workspaces(root, runtime_root)
    except (OSError, PermissionError, ValueError) as exc:
        if as_json:
            print(json.dumps({"verdict": "FAIL", "error": str(exc)}, ensure_ascii=False))
        else:
            print(f"AGENTS_DEPLOY_RESULT=FAIL error={exc}")
        return 2
    if as_json:
        print(
            json.dumps(
                {
                    "verdict": "PASS",
                    "runtime_root": str(runtime_root),
                    "workspaces": [str(path) for path in deployed],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print(f"AGENTS_DEPLOY_RESULT=PASS count={len(deployed)} root={runtime_root / 'workspaces'}")
    return 0


def _openclaw_render(
    root: Path,
    runtime_value: str | None,
    backend: str,
    output: str | None,
    as_json: bool,
) -> int:
    runtime_root = resolve_runtime_root(runtime_value)
    try:
        patch = build_openclaw_patch(root, runtime_root, backend)
        if output:
            path = write_openclaw_patch(Path(output).expanduser().resolve(), patch)
            if as_json:
                print(json.dumps({"verdict": "PASS", "output": str(path)}, ensure_ascii=False))
            else:
                print(f"OPENCLAW_PATCH={path}")
        else:
            print(json.dumps(patch, indent=2, ensure_ascii=False))
    except (FileNotFoundError, KeyError, OSError, ValueError) as exc:
        if as_json:
            print(json.dumps({"verdict": "FAIL", "error": str(exc)}, ensure_ascii=False))
        else:
            print(f"OPENCLAW_RENDER_RESULT=FAIL error={exc}")
        return 2
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clawfedora")
    parser.add_argument("--root", help="racine du dépôt")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="valider tous les contrats du dépôt")
    validate.add_argument("--json", action="store_true")

    audit = subparsers.add_parser("audit", help="auditer Fedora 44 et la B580")
    audit.add_argument("--strict", action="store_true", help="faire échouer les prérequis Fedora")
    audit.add_argument("--json", action="store_true")

    agents = subparsers.add_parser("agents", help="valider ou déployer les huit workspaces")
    agent_commands = agents.add_subparsers(dest="agents_command", required=True)
    agents_validate = agent_commands.add_parser("validate")
    agents_validate.add_argument("--json", action="store_true")
    agents_deploy = agent_commands.add_parser("deploy")
    agents_deploy.add_argument("--runtime-root")
    agents_deploy.add_argument("--json", action="store_true")

    openclaw = subparsers.add_parser("openclaw", help="outils de configuration OpenClaw")
    openclaw_commands = openclaw.add_subparsers(dest="openclaw_command", required=True)
    render = openclaw_commands.add_parser("render", help="générer le patch OpenClaw")
    render.add_argument("--runtime-root")
    render.add_argument(
        "--backend",
        choices=("ollama-vulkan", "llama-cpp-vulkan", "llama-cpp-sycl"),
        default="ollama-vulkan",
    )
    render.add_argument("--output")
    render.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = _root_from_args(args.root)
    if args.command == "validate":
        return _validate(root, bool(args.json))
    if args.command == "audit":
        return _audit(bool(args.strict), bool(args.json))
    if args.command == "agents":
        if args.agents_command == "validate":
            return _agents_validate(root, bool(args.json))
        if args.agents_command == "deploy":
            return _agents_deploy(root, args.runtime_root, bool(args.json))
    if args.command == "openclaw" and args.openclaw_command == "render":
        return _openclaw_render(
            root,
            args.runtime_root,
            str(args.backend),
            args.output,
            bool(args.json),
        )
    parser.error("commande non supportée")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
