from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from clawfedora.core_config import AGENT_IDS, root_contract
from clawfedora.optimization import (
    compare_kernel,
    compare_model_challenger,
    compare_runtime,
    write_decision,
)
from clawfedora.release_readiness import (
    BLOCKED,
    READY,
    approve_release,
    collect_readiness,
    dry_run,
    write_readiness_report,
)

ROOT = Path(__file__).resolve().parents[1]


def _write(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _hardware(runtime: Path, gate: str) -> Path:
    return _write(
        runtime / "proofs/hardware" / f"hardware_{gate.casefold()}_20260903_120000.json",
        {
            "schema_version": "1.0.0",
            "gate": gate,
            "collected_at": "2026-09-03T12:00:00+00:00",
            "kernel": "fedora-test",
            "verdict": "PASS",
            "failures": 0,
            "warnings": 0,
            "checks": [{"id": "synthetic", "status": "PASS", "detail": "test"}],
        },
    )


def _l4(runtime: Path) -> Path:
    version = root_contract(ROOT, "runtime_versions.yaml")["openclaw"]
    assert isinstance(version, dict)
    pin = str(version["initial_qualification_pin"])
    smokes = [
        {
            "agent": agent,
            "model_ref": "ollama/test",
            "provider": "ollama",
            "text_sha256": "a" * 64,
            "text_chars": 10,
            "status": "ok",
        }
        for agent in AGENT_IDS
    ]
    return _write(
        runtime / "proofs/openclaw-e2e/l4_20260903_120000.json",
        {
            "schema_version": "1.0.0",
            "gate": "L4",
            "backend": "ollama-vulkan",
            "openclaw_version": f"OpenClaw {pin}",
            "gateway": {"rpc": {"ok": True}},
            "cloud_enabled": False,
            "transport": "gateway",
            "agent_smokes": smokes,
            "tool_call": {"status": "ok"},
            "repair": {"status": "ok"},
            "stability": [{"run": index, "status": "ok"} for index in range(1, 4)],
            "verdict": "PASS",
        },
    )


def _l5(runtime: Path, l2: Path, l3: Path) -> Path:
    policy = root_contract(ROOT, "qualification_policy.yaml")
    automated = policy["automated_gates"]
    full = policy["full_gate"]
    assert isinstance(automated, dict)
    assert isinstance(full, dict)
    catalog = root_contract(ROOT, "model_catalog.yaml")
    models = catalog["models"]
    assert isinstance(models, dict)
    identities: list[dict[str, Any]] = []
    for alias, raw in models.items():
        if not isinstance(raw, dict) or raw.get("required") is not True:
            continue
        identities.append(
            {
                "alias": alias,
                "runtime_id": raw["runtime_id"],
                "digest": f"digest-{alias}",
                "size": 1,
                "format": "gguf",
                "family": raw.get("family"),
                "parameter_size": "test",
                "quantization_level": raw["quantization"],
            }
        )
    return _write(
        runtime / "proofs/qualification/hard40_20260903_120000.json",
        {
            "schema_version": "1.0.0",
            "protocol": "fedora-hard40-v1",
            "suite": policy["suite"],
            "started_at": "2026-09-03T12:00:00+00:00",
            "finished_at": "2026-09-03T12:10:00+00:00",
            "total_wall_seconds": 600.0,
            "max_wall_seconds": full["max_wall_seconds"],
            "case_timeout_seconds": full["case_timeout_seconds"],
            "kernel": "fedora-test",
            "mesa": "mesa-test",
            "ollama_version": "0.32.14",
            "performance_profile": {"source": "test", "value": "performance", "ok": True},
            "endpoint": "http://127.0.0.1:11434",
            "cloud_calls_allowed": False,
            "model_identities": identities,
            "scenario_matrix": automated["scenario_matrix"],
            "qwen_native_cases": automated["qwen_native_cases"],
            "hardware_evidence": {"l2": str(l2), "l3": str(l3)},
            "cases": [
                {
                    "model_alias": ("qwen-max", "gemma-deep", "devstral-devops")[index // 10],
                    "status": "ok",
                    "check_passed": True,
                }
                for index in range(30)
            ],
            "evaluation": {
                "verdict": "PASS",
                "failures": [],
                "metrics": {},
                "thresholds": automated["thresholds"],
            },
            "promotion": {
                "backend": False,
                "kernel": False,
                "v1": False,
                "human_review_required": True,
            },
        },
    )


def _model_metrics(runtime_id: str, digest: str, tps: float) -> dict[str, Any]:
    return {
        "runtime_id": runtime_id,
        "digest": digest,
        "quantization": "Q4_K_M",
        "median_tokens_per_second": tps,
        "p95_first_token_ms": 1000.0,
        "vram_mib": 8000.0,
        "ram_mib": 12000.0,
        "error_rate": 0.0,
    }


def _nominal_models(tps: float) -> dict[str, Any]:
    catalog = root_contract(ROOT, "model_catalog.yaml")
    models = catalog["models"]
    assert isinstance(models, dict)
    result: dict[str, Any] = {}
    for alias in ("qwen-max", "gemma-deep", "devstral-devops"):
        raw = models[alias]
        assert isinstance(raw, dict)
        result[alias] = _model_metrics(str(raw["runtime_id"]), f"digest-{alias}", tps)
    return result


def _snapshot(
    runtime: Path,
    *,
    run_id: str,
    kind: str,
    candidate_id: str,
    kernel: str,
    backend: str,
    models: dict[str, Any],
    extra: dict[str, Any] | None = None,
) -> Path:
    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "created_at": "2026-09-03T12:00:00+00:00",
        "kind": kind,
        "candidate_id": candidate_id,
        "kernel": kernel,
        "backend": backend,
        "models": models,
        "contexts": [8192],
        "prompt_hashes": ["prompt-a", "prompt-b", "prompt-c"],
        "functional_pass": True,
        "security_pass": True,
        "metrics": {"cases": 9, "passed_cases": 9},
        "raw_outputs_persisted": False,
        "cloud_calls_allowed": False,
    }
    if extra:
        payload.update(extra)
    return _write(runtime / "proofs/l6/snapshots" / f"{run_id}.json", payload)


def _l6(runtime: Path) -> None:
    runtime_base: list[Path] = []
    runtime_candidate: list[Path] = []
    for index in range(3):
        runtime_base.append(
            _snapshot(
                runtime,
                run_id=f"runtime-base-{index}",
                kind="runtime",
                candidate_id="baseline",
                kernel="6.17.0-fedora",
                backend="ollama-vulkan",
                models=_nominal_models(10.0),
            )
        )
        runtime_candidate.append(
            _snapshot(
                runtime,
                run_id=f"runtime-vulkan-{index}",
                kind="runtime",
                candidate_id="llama-cpp-vulkan",
                kernel="6.17.0-fedora",
                backend="llama-cpp-vulkan",
                models=_nominal_models(12.0),
            )
        )
    runtime_report = compare_runtime(ROOT, runtime_base, runtime_candidate)
    write_decision(runtime_report, runtime / "proofs/l6/decisions/runtime-vulkan.json")

    kernel_base: list[Path] = []
    kernel_candidate: list[Path] = []
    for index in range(3):
        kernel_base.append(
            _snapshot(
                runtime,
                run_id=f"kernel-base-{index}",
                kind="kernel",
                candidate_id="fedora-official",
                kernel="6.17.0-fedora",
                backend="llama-cpp-vulkan",
                models=_nominal_models(12.0),
            )
        )
        kernel_candidate.append(
            _snapshot(
                runtime,
                run_id=f"kernel-723-{index}",
                kind="kernel",
                candidate_id="upstream-7.2.3",
                kernel="7.2.3-test",
                backend="llama-cpp-vulkan",
                models=_nominal_models(12.6),
            )
        )
    kernel_report = compare_kernel(ROOT, kernel_base, kernel_candidate)
    write_decision(kernel_report, runtime / "proofs/l6/decisions/kernel-723.json")

    challenger_cfg = root_contract(ROOT, "optimization_policy.yaml")["model_challenger"]
    assert isinstance(challenger_cfg, dict)
    incumbent: list[Path] = []
    challenger: list[Path] = []
    for index in range(3):
        incumbent.append(
            _snapshot(
                runtime,
                run_id=f"gemma-{index}",
                kind="model-challenger",
                candidate_id=str(challenger_cfg["incumbent"]),
                kernel="6.17.0-fedora",
                backend="ollama-vulkan",
                models={
                    "gemma-deep": _model_metrics(
                        str(challenger_cfg["incumbent"]), "digest-gemma", 12.0
                    )
                },
                extra={
                    "vision_pass": True,
                    "document_quality_pass": True,
                    "tool_calling_pass": True,
                },
            )
        )
        challenger.append(
            _snapshot(
                runtime,
                run_id=f"ministral-{index}",
                kind="model-challenger",
                candidate_id=str(challenger_cfg["challenger"]),
                kernel="6.17.0-fedora",
                backend="ollama-vulkan",
                models={
                    "gemma-deep": _model_metrics(
                        str(challenger_cfg["challenger"]), "digest-ministral", 12.0
                    )
                },
                extra={
                    "vision_pass": True,
                    "document_quality_pass": True,
                    "tool_calling_pass": True,
                },
            )
        )
    challenger_report = compare_model_challenger(ROOT, incumbent, challenger)
    write_decision(challenger_report, runtime / "proofs/l6/decisions/ministral.json")


def _l7(runtime: Path) -> Path:
    projects = [
        {
            "project_id": f"project-{index}",
            "kind": "golden" if index < 5 else "representative",
            "verdict": "PASS",
            "terminal_status": "PACKAGING",
            "task_count": 1,
            "validation": "PASS",
            "review": "PASS",
            "package_integrity": True,
            "human_gate_preserved": True,
            "duration_ms": 1,
            "project_path": "/tmp/test",
            "failure": None,
        }
        for index in range(6)
    ]
    return _write(
        runtime / "proofs/l7/runs/test-run/L7_REPORT.json",
        {
            "schema_version": "1.0.0",
            "generated_at": "2026-09-03T12:00:00+00:00",
            "gate": "L7",
            "run_id": "test-run",
            "verdict": "PASS",
            "golden_projects_pass": 5,
            "representative_projects_pass": 1,
            "projects": projects,
            "telemetry": {
                "events": 6,
                "local_only": True,
                "raw_prompt_or_response_persisted": False,
            },
            "finops": {"events": 12, "net_exposure_eur": 0.0},
            "limitations": [],
            "cloud_calls_allowed": False,
            "remote_publication_allowed": False,
            "automatic_human_approval": False,
            "final_human_completion": False,
            "failures": [],
        },
    )


def _runtime(tmp_path: Path) -> Path:
    runtime = tmp_path / "runtime"
    l2 = _hardware(runtime, "L2")
    l3 = _hardware(runtime, "L3")
    _l4(runtime)
    _l5(runtime, l2, l3)
    _l6(runtime)
    _l7(runtime)
    return runtime


def test_l8_dry_run_never_claims_human_approval() -> None:
    payload = dry_run(ROOT)
    assert payload["verdict"] == "READY_TO_COLLECT_EVIDENCE"
    assert payload["automatic_human_approval"] is False
    assert payload["automatic_config_mutation"] is False
    assert payload["automatic_release_publication"] is False
    assert len(payload["required_l6_decisions"]) == 3


def test_l8_collects_and_recomputes_all_required_evidence(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    payload = collect_readiness(ROOT, runtime)
    assert payload["verdict"] == READY
    assert payload["software_contracts"]["verdict"] == "PASS"
    assert all(payload["gates"][gate]["status"] == "PASS" for gate in [
        "L0",
        "L1",
        "L2",
        "L3",
        "L4",
        "L5",
        "L6",
        "L7",
    ])
    assert len(payload["gates"]["L6"]["decisions"]) == 3
    assert all(item["recomputed"] is True for item in payload["gates"]["L6"]["decisions"])
    assert len(payload["evidence_set_sha256"]) == 64
    assert payload["human_approval"] == {
        "required": True,
        "status": "PENDING",
        "automatic": False,
    }
    assert payload["v1_approved"] is False


def test_l8_blocks_if_hard40_thresholds_are_tampered(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    path = next((runtime / "proofs/qualification").glob("hard40_*.json"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["evaluation"]["thresholds"]["min_check_pass_rate"] = 0.1
    _write(path, payload)
    report = collect_readiness(ROOT, runtime)
    assert report["verdict"] == BLOCKED
    assert any("seuils" in failure for failure in report["failures"])


def test_l8_blocks_if_mandatory_ministral_decision_is_missing(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    (runtime / "proofs/l6/decisions/ministral.json").unlink()
    report = collect_readiness(ROOT, runtime)
    assert report["verdict"] == BLOCKED
    assert any("model-challenger" in failure for failure in report["failures"])


def test_l8_blocks_if_recorded_l6_decision_does_not_match_current_recalculation(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    path = runtime / "proofs/l6/decisions/runtime-vulkan.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["verdict"] = "KEEP_BASELINE"
    _write(path, payload)
    report = collect_readiness(ROOT, runtime)
    assert report["verdict"] == BLOCKED
    assert any("recalcul courant" in failure for failure in report["failures"])


def test_l8_approval_requires_explicit_ack_and_does_not_publish_or_mutate(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    code, report_path = write_readiness_report(ROOT, runtime)
    assert code == 0

    try:
        approve_release(
            ROOT,
            runtime,
            report_path,
            approver="Mathias",
            acknowledge=False,
        )
    except PermissionError as exc:
        assert "acknowledgement" in str(exc)
    else:
        raise AssertionError("approval must require explicit acknowledgement")

    approval_path = approve_release(
        ROOT,
        runtime,
        report_path,
        approver="Mathias",
        acknowledge=True,
    )
    payload = json.loads(approval_path.read_text(encoding="utf-8"))
    assert payload["verdict"] == "APPROVED_FOR_V1_PREPARATION"
    assert payload["human_approved"] is True
    assert payload["automatic"] is False
    assert payload["scope"] == "prepare-v1"
    assert payload["runtime_config_mutated"] is False
    assert payload["release_published"] is False
    assert payload["project_complete_mutated"] is False
    assert len(payload["readiness_report_sha256"]) == 64


def test_l8_approval_rejects_changed_evidence_after_report(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    code, report_path = write_readiness_report(ROOT, runtime)
    assert code == 0
    l7_path = runtime / "proofs/l7/runs/test-run/L7_REPORT.json"
    payload = json.loads(l7_path.read_text(encoding="utf-8"))
    payload["generated_at"] = "2026-09-03T13:00:00+00:00"
    _write(l7_path, payload)
    try:
        approve_release(
            ROOT,
            runtime,
            report_path,
            approver="Mathias",
            acknowledge=True,
        )
    except PermissionError as exc:
        assert "ensemble de preuves modifié" in str(exc)
    else:
        raise AssertionError("approval must recheck current evidence hash")
