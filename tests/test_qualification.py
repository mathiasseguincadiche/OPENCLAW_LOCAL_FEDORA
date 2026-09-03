from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from clawfedora.hardware_gate import HardwareGateReport
from clawfedora import qualification

ROOT = Path(__file__).resolve().parents[1]


def _tag(name: str, digest: str, quantization: str = "Q4_K_M") -> dict[str, Any]:
    return {
        "name": name,
        "digest": digest,
        "size": 123456,
        "details": {
            "format": "gguf",
            "family": "test",
            "parameter_size": "27B",
            "quantization_level": quantization,
        },
    }


def _tags() -> dict[str, Any]:
    return {
        "models": [
            _tag("qwen3.8:27b", "a" * 64),
            _tag("gemma4:26b", "b" * 64),
            _tag("devstral-small-2:24b", "c" * 64),
        ]
    }


def _output_for(scenario_id: str) -> str:
    values = {
        "project-intake-analysis": json.dumps(
            {
                "objectives": [],
                "constraints": [],
                "deliverables": [],
                "risks": [],
                "first_actions": [],
            }
        ),
        "systemd-service-debug": "systemctl puis journalctl, vérifier et rollback sans supposer.",
        "kubernetes-root-cause": "kubectl get pods, describe, events puis logs sans supposer.",
        "terraform-multifile-change": "main.tf variables.tf outputs.tf",
        "ansible-idempotence": "check mode, handler, second passage changed=0, idempotence.",
        "selinux-security-review": "SELinux Enforcing: AVC puis ausearch et restorecon, validation.",
        "rollback-runbook": "Préconditions\nDéploiement\nVérification\nRollback",
        "architecture-diagram-d2": (
            "Utilisateur -> OpenClaw\nOpenClaw -> Routeur\n"
            "Routeur -> Ollama\nRouteur -> llama.cpp"
        ),
        "web-freshness-discipline": "Vérifier une source officielle récente sur le web.",
        "tool-intent-json": json.dumps(
            {"tool": "read_file", "arguments": {"path": "README.md"}, "reason": "inspect"}
        ),
        "tool-feedback-repair-json": json.dumps(
            {"diagnosis": "file_not_found", "next_action": "vérifier le chemin"}
        ),
        "long-context-discipline": "dérive versions; dérive paramètres; dérive permissions",
    }
    return values[scenario_id]


def _generation(case: qualification.PlannedCase) -> dict[str, Any]:
    output = _output_for(str(case.scenario["id"]))
    return {
        "output": output,
        "first_generation_ms": 500.0,
        "response_ttft_ms": 600.0,
        "wall_ms": 1000.0,
        "eval_count": 100,
        "tokens_per_second": 10.0,
        "prompt_eval_count": 100,
        "prompt_tokens_per_second": 100.0,
        "load_duration_ms": 20.0,
        "thinking_chars": 50 if case.thinking_mode == "native" else 0,
        "done_reason": "stop",
        "output_truncated": False,
    }


def test_dry_run_has_exact_hard40_plan() -> None:
    payload = qualification.dry_run(ROOT)
    assert payload["verdict"] == "PASS"
    assert payload["cases"] == 30
    assert payload["contexts"] == {8192: 24, 16384: 6}
    assert payload["qwen_native_probes"] == 3
    assert payload["qwen_native_max_output_tokens"] == 768
    assert payload["case_timeout_seconds"] == 210
    assert payload["max_wall_seconds"] == 2400
    assert payload["cloud_calls_allowed"] is False


def test_plan_has_ten_cases_per_model_and_exact_native_probes() -> None:
    policy = qualification.root_contract(ROOT, "qualification_policy.yaml")
    catalog = qualification.root_contract(ROOT, "model_catalog.yaml")
    suite = qualification.load_yaml(ROOT / "benchmarks" / "suites" / "linux_devops_v1.yaml")
    plan = qualification.build_plan(catalog, policy, suite)
    for alias in ("qwen-max", "gemma-deep", "devstral-devops"):
        assert sum(case.model_alias == alias for case in plan.cases) == 10
    native = [case for case in plan.cases if case.thinking_mode == "native"]
    assert len(native) == 3
    assert all(case.model_alias == "qwen-max" for case in native)
    assert all(case.max_output_tokens == 768 for case in native)


def test_checks_cover_structured_positive_and_negative_rules() -> None:
    ok, details = qualification.run_checks(
        '{"a": 1, "b": 2}',
        [{"type": "json_keys", "keys": ["a", "b"]}, {"type": "nonempty"}],
    )
    assert ok is True
    assert details == ["json_keys:pass", "nonempty:pass"]
    ok, _ = qualification.run_checks(
        "SELinux AVC ausearch",
        [
            {"type": "contains_all", "values": ["SELinux", "AVC"]},
            {"type": "contains_any", "values": ["ausearch", "audit2why"]},
            {"type": "not_contains_any", "values": ["setenforce 0"]},
        ],
    )
    assert ok is True
    ok, _ = qualification.run_checks("x", [{"type": "unknown"}])
    assert ok is False


def test_evaluator_applies_global_and_context_thresholds() -> None:
    policy = qualification.root_contract(ROOT, "qualification_policy.yaml")
    cases: list[dict[str, Any]] = []
    for index in range(30):
        cases.append(
            {
                "status": "ok",
                "check_passed": True,
                "context": 8192 if index < 24 else 16384,
                "model_alias": ("qwen-max", "gemma-deep", "devstral-devops")[index // 10],
                "tokens_per_second": 10.0,
                "first_token_ms": 1000.0,
            }
        )
    result = qualification.evaluate_cases(policy, cases)
    assert result["verdict"] == "PASS"
    cases[0]["status"] = "error"
    result = qualification.evaluate_cases(policy, cases)
    assert result["verdict"] == "FAIL"
    assert "error_rate" in result["failures"]


def test_loopback_endpoint_policy() -> None:
    assert qualification._loopback_endpoint("http://127.0.0.1:11434") is True
    assert qualification._loopback_endpoint("http://localhost:11434") is True
    assert qualification._loopback_endpoint("https://127.0.0.1:11434") is False
    assert qualification._loopback_endpoint("http://example.com:11434") is False


def test_model_inventory_requires_digest_and_quantization() -> None:
    policy = qualification.root_contract(ROOT, "qualification_policy.yaml")
    catalog = qualification.root_contract(ROOT, "model_catalog.yaml")
    required = qualification._selected_models(catalog, policy)
    inventory = qualification._model_inventory(_tags(), required)
    assert len(inventory) == 3
    assert {item["alias"] for item in inventory} == {
        "qwen-max",
        "gemma-deep",
        "devstral-devops",
    }
    bad = _tags()
    bad["models"][0]["digest"] = ""
    with pytest.raises(ValueError, match="identité Ollama incomplète"):
        qualification._model_inventory(bad, required)


def _mock_hardware(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def collect(_root: Path, gate: str) -> HardwareGateReport:
        return HardwareGateReport(gate.upper(), (), "now")

    def write(report: HardwareGateReport, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{report.gate}.json"
        path.write_text("{}", encoding="utf-8")
        return path

    monkeypatch.setattr(qualification, "collect_hardware_gate", collect)
    monkeypatch.setattr(qualification, "write_hardware_evidence", write)
    monkeypatch.setattr(
        qualification,
        "_performance_profile",
        lambda: {"source": "test", "value": "performance", "ok": True},
    )
    monkeypatch.setattr(qualification, "_rpm_version", lambda _package: "mesa-test")


def test_full_qualification_simulation_passes_30_cases_without_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_hardware(monkeypatch, tmp_path)

    def request(url: str, **_kwargs: Any) -> dict[str, Any]:
        return _tags() if url.endswith("/api/tags") else {"version": "test-ollama"}

    monkeypatch.setattr(qualification, "_request_json", request)
    monkeypatch.setattr(
        qualification,
        "_run_generation",
        lambda _endpoint, case, deadline: _generation(case),
    )
    code, evidence = qualification.run_qualification(
        ROOT,
        runtime_root=tmp_path / "runtime",
    )
    assert code == 0
    assert evidence is not None and evidence.is_file()
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["evaluation"]["verdict"] == "PASS"
    assert len(payload["cases"]) == 30
    assert all("output" not in item for item in payload["cases"])
    assert payload["promotion"] == {
        "backend": False,
        "kernel": False,
        "v1": False,
        "human_review_required": True,
    }


def test_qualification_refuses_non_loopback_before_hardware(tmp_path: Path) -> None:
    code, evidence = qualification.run_qualification(
        ROOT,
        runtime_root=tmp_path,
        endpoint="http://example.com:11434",
    )
    assert code == 2
    assert evidence is None


def test_qualification_fails_fast_on_truncation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_hardware(monkeypatch, tmp_path)
    monkeypatch.setattr(
        qualification,
        "_request_json",
        lambda url, **_kwargs: _tags() if url.endswith("/api/tags") else {"version": "test"},
    )

    def truncated(_endpoint: str, case: qualification.PlannedCase, deadline: float) -> dict[str, Any]:
        result = _generation(case)
        result["output_truncated"] = True
        result["eval_count"] = case.max_output_tokens
        return result

    monkeypatch.setattr(qualification, "_run_generation", truncated)
    code, evidence = qualification.run_qualification(
        ROOT,
        runtime_root=tmp_path / "runtime",
    )
    assert code == 2
    assert evidence is not None
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert len(payload["cases"]) == 1
    assert payload["evaluation"]["verdict"] == "FAIL"
