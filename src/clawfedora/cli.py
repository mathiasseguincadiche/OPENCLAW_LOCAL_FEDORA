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
from clawfedora.golden_contracts import validate_golden_contracts
from clawfedora.hardware_gate import collect_hardware_gate, write_hardware_evidence
from clawfedora.openclaw_config import build_openclaw_patch, write_openclaw_patch
from clawfedora.openclaw_e2e import dry_run as e2e_dry_run
from clawfedora.openclaw_e2e import run_e2e
from clawfedora.optimization_contracts import validate_optimization_contracts
from clawfedora.project_cli import add_project_parser, run_project_command
from clawfedora.qualification import dry_run as qualification_dry_run
from clawfedora.qualification import run_qualification
from clawfedora.qualification_contracts import validate_qualification_contracts
from clawfedora.release_readiness_contracts import validate_release_readiness_contracts

SLEEP_INHIBIT_MARKER = "OPENCLAW_LOCAL_FEDORA_SLEEP_INHIBITED"


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
        qualification_failures, qualification_warnings = validate_qualification_contracts(root)
        failures.extend(qualification_failures)
        warnings.extend(qualification_warnings)
        optimization_failures, optimization_warnings = validate_optimization_contracts(root)
        failures.extend(optimization_failures)
        warnings.extend(optimization_warnings)
        golden_failures, golden_warnings = validate_golden_contracts(root)
        failures.extend(golden_failures)
        warnings.extend(golden_warnings)
        readiness_failures, readiness_warnings = validate_release_readiness_contracts(root)
        failures.extend(readiness_failures)
        warnings.extend(readiness_warnings)
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


def _hardware(
    root: Path,
    gate: str,
    runtime_value: str | None,
    as_json: bool,
) -> int:
    try:
        report = collect_hardware_gate(root, gate)
        runtime = resolve_runtime_root(runtime_value)
        evidence = write_hardware_evidence(
            report,
            runtime / "proofs" / "hardware",
        )
    except (FileNotFoundError, OSError, ValueError) as exc:
        if as_json:
            print(json.dumps({"verdict": "FAIL", "error": str(exc)}, ensure_ascii=False))
        else:
            print(f"HARDWARE_RESULT=FAIL error={exc}")
        return 2
    if as_json:
        payload = report.payload()
        payload["evidence"] = str(evidence)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        for check in report.checks:
            print(f"{check.status:<4} {check.id:<24} {check.detail}")
        print(f"EVIDENCE={evidence}")
        print(
            f"HARDWARE_RESULT={'PASS' if report.ok else 'FAIL'} "
            f"gate={report.gate} failures={report.failures} warnings={report.warnings}"
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
        print(
            f"AGENTS_DEPLOY_RESULT=PASS count={len(deployed)} "
            f"root={runtime_root / 'workspaces'}"
        )
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


def _sleep_inhibit_ok(gate: str) -> bool:
    if os.environ.get(SLEEP_INHIBIT_MARKER) == "1":
        return True
    print(
        f"{gate}_RESULT=FAIL systemd-inhibit requis; "
        "utiliser le launcher Linux/menu pour un run réel"
    )
    return False


def _qualification(
    root: Path,
    runtime_value: str | None,
    endpoint: str,
    dry_run: bool,
    as_json: bool,
) -> int:
    if dry_run:
        try:
            payload = qualification_dry_run(root)
        except (FileNotFoundError, KeyError, ValueError) as exc:
            print(f"QUALIFICATION_DRY_RUN=FAIL error={exc}")
            return 2
        if as_json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(
                "QUALIFICATION_DRY_RUN=PASS "
                f"gate={payload['gate']} cases={payload['cases']} "
                f"contexts={payload['contexts']} qwen_native={payload['qwen_native_probes']} "
                f"qwen_max={payload['qwen_native_max_output_tokens']} "
                f"case_timeout={payload['case_timeout_seconds']}s "
                f"hard_wall={payload['max_wall_seconds']}s"
            )
            print(
                "PRECHECKS=L2,L3,performance-profile,ollama-model-identity "
                "SUSPEND=systemd-inhibit CLOUD=false"
            )
        return 0

    if not _sleep_inhibit_ok("QUALIFICATION"):
        return 2
    contract_failures, _ = validate_qualification_contracts(root)
    if contract_failures:
        print(
            "QUALIFICATION_RESULT=FAIL contrats invalides: "
            + "; ".join(contract_failures)
        )
        return 2
    runtime = resolve_runtime_root(runtime_value)
    code, _ = run_qualification(root, runtime_root=runtime, endpoint=endpoint)
    return code


def _e2e(
    root: Path,
    runtime_value: str | None,
    backend: str,
    dry_run: bool,
    as_json: bool,
) -> int:
    if dry_run:
        try:
            payload = e2e_dry_run(backend)
        except ValueError as exc:
            print(f"L4_DRY_RUN=FAIL error={exc}")
            return 2
        if as_json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(
                f"L4_DRY_RUN=PASS backend={backend} agents=8 "
                "tool_call=true repair=true stability=3 gateway=true"
            )
        return 0

    if not _sleep_inhibit_ok("L4"):
        return 2
    runtime = resolve_runtime_root(runtime_value)
    code, _ = run_e2e(root, backend=backend, runtime_root=runtime)
    return code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clawfedora")
    parser.add_argument("--root", help="racine du dépôt")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="valider tous les contrats du dépôt")
    validate.add_argument("--json", action="store_true")

    audit = subparsers.add_parser("audit", help="auditer Fedora 44 et la B580")
    audit.add_argument("--strict", action="store_true", help="faire échouer les prérequis Fedora")
    audit.add_argument("--json", action="store_true")

    hardware = subparsers.add_parser("hardware", help="gates matériels L2/L3")
    hardware.add_argument("--gate", choices=("l2", "l3"), required=True)
    hardware.add_argument("--runtime-root")
    hardware.add_argument("--json", action="store_true")

    qualification = subparsers.add_parser("qualification", help="qualification HARD-40M L5")
    qualification.add_argument("--runtime-root")
    qualification.add_argument("--endpoint", default="http://127.0.0.1:11434")
    qualification.add_argument("--dry-run", action="store_true")
    qualification.add_argument("--json", action="store_true")

    e2e = subparsers.add_parser("e2e", help="gate OpenClaw L4")
    e2e.add_argument("--runtime-root")
    e2e.add_argument(
        "--backend",
        choices=("ollama-vulkan", "llama-cpp-vulkan", "llama-cpp-sycl"),
        default="ollama-vulkan",
    )
    e2e.add_argument("--dry-run", action="store_true")
    e2e.add_argument("--json", action="store_true")

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

    add_project_parser(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = _root_from_args(args.root)
    if args.command == "validate":
        return _validate(root, bool(args.json))
    if args.command == "audit":
        return _audit(bool(args.strict), bool(args.json))
    if args.command == "hardware":
        return _hardware(root, str(args.gate), args.runtime_root, bool(args.json))
    if args.command == "qualification":
        return _qualification(
            root,
            args.runtime_root,
            str(args.endpoint),
            bool(args.dry_run),
            bool(args.json),
        )
    if args.command == "e2e":
        return _e2e(
            root,
            args.runtime_root,
            str(args.backend),
            bool(args.dry_run),
            bool(args.json),
        )
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
    if args.command == "project":
        return run_project_command(root, args)
    parser.error(f"commande non supportée: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
