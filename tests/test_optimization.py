from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from clawfedora import optimization

MODELS = {
    "qwen-max": "qwen3.5:9b-q4_K_M",
    "gemma-deep": "gemma3:12b-it-q4_K_M",
    "devstral-devops": "qwen2.5-coder:14b-instruct-q4_K_M",
}


def _policy() -> dict[str, object]:
    return {
        "pins": {"kernel_candidate": {"version": "7.2.3"}},
        "paths": {"llama_models": "models/llama-router"},
        "artifact_staging": {"network_downloads_allowed": False},
        "runtime_comparison": {
            "baseline": "ollama-vulkan",
            "candidates": ["llama-cpp-vulkan", "llama-cpp-sycl"],
            "minimum_repeated_runs": 3,
            "aggregate_improvement_target_pct": 10.0,
            "maximum_single_model_regression_pct": 5.0,
        },
        "kernel_comparison": {
            "baseline": "fedora-official",
            "candidate": "upstream-7.2.3",
            "minimum_repeated_runs": 3,
            "minimum_aggregate_improvement_pct": 3.0,
            "maximum_single_model_regression_pct": 2.0,
        },
        "model_challenger": {
            "slot": "gemma-deep",
            "incumbent": "gemma3:12b-it-q4_K_M",
            "challenger": "ministral-3:14b-instruct-2512-q4_K_M",
            "minimum_repeated_runs": 3,
            "maximum_performance_regression_pct": 5.0,
        },
    }


def _catalog() -> dict[str, object]:
    return {
        "models": {
            alias: {
                "required": True,
                "runtime_id": runtime_id,
                "quantization": "Q4_K_M",
            }
            for alias, runtime_id in MODELS.items()
        }
    }


def _root_contract(_root: Path, name: str) -> dict[str, object]:
    if name == "optimization_policy.yaml":
        return _policy()
    if name == "model_catalog.yaml":
        return _catalog()
    raise AssertionError(name)


def _models(runtime_ids: dict[str, str], tps: float) -> dict[str, object]:
    return {
        alias: {
            "runtime_id": runtime_id,
            "digest": f"sha-{alias}",
            "quantization": "Q4_K_M",
            "median_tokens_per_second": tps,
            "p95_first_token_ms": 100.0,
            "vram_mib": 4096.0,
            "ram_mib": 8192.0,
            "error_rate": 0.0,
        }
        for alias, runtime_id in runtime_ids.items()
    }


def _evidence(
    run_id: str,
    kind: str,
    candidate_id: str,
    kernel: str,
    backend: str,
    *,
    runtime_ids: dict[str, str] | None = None,
    tps: float = 10.0,
    functional: bool = True,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": optimization.EVIDENCE_SCHEMA,
        "run_id": run_id,
        "kind": kind,
        "candidate_id": candidate_id,
        "kernel": kernel,
        "backend": backend,
        "models": _models(runtime_ids or MODELS, tps),
        "contexts": [8192],
        "prompt_hashes": ["prompt-a", "prompt-b"],
        "functional_pass": functional,
        "security_pass": True,
        "metrics": {"cases": 9},
    }
    if extra:
        payload.update(extra)
    return payload


def _series(tmp_path: Path, prefix: str, values: list[dict[str, object]]) -> list[Path]:
    paths: list[Path] = []
    for index, value in enumerate(values):
        path = tmp_path / f"{prefix}-{index}.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        paths.append(path)
    return paths


def test_helpers_and_evidence_validation(tmp_path: Path) -> None:
    assert optimization._safe_relative(tmp_path, "models/x") == (
        tmp_path / "models/x"
    ).resolve()
    with pytest.raises(ValueError, match="chemin relatif interdit"):
        optimization._safe_relative(tmp_path, "../escape")

    source = tmp_path / "model.gguf"
    source.write_bytes(b"abc")
    assert optimization._sha256(source) == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
    refs = optimization._modelfile_refs(f'FROM "{source}"\n')
    assert refs == [("FROM", source.resolve())]
    with pytest.raises(ValueError, match="Modelfile invalide"):
        optimization._modelfile_refs('FROM "unterminated')

    good = _evidence("r1", "runtime", "candidate", "kernel", "backend")
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(good), encoding="utf-8")
    assert optimization.load_evidence(path)["run_id"] == "r1"

    path.write_text(json.dumps({"schema_version": "0"}), encoding="utf-8")
    with pytest.raises(ValueError, match="schéma preuve invalide"):
        optimization.load_evidence(path)
    path.write_text(json.dumps({"schema_version": "1.0.0"}), encoding="utf-8")
    with pytest.raises(ValueError, match="preuve incomplète"):
        optimization.load_evidence(path)

    no_models = dict(good)
    no_models["models"] = {}
    path.write_text(json.dumps(no_models), encoding="utf-8")
    with pytest.raises(ValueError, match="preuve sans modèles"):
        optimization.load_evidence(path)

    bad_model = dict(good)
    bad_model["models"] = {"qwen-max": {"runtime_id": "x"}}
    path.write_text(json.dumps(bad_model), encoding="utf-8")
    with pytest.raises(ValueError, match="digest absent"):
        optimization.load_evidence(path)


def test_stage_models_dry_run_apply_and_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(optimization, "root_contract", _root_contract)
    sources: dict[str, Path] = {}
    for alias in MODELS:
        source = tmp_path / f"{alias}.gguf"
        source.write_bytes(alias.encode())
        sources[alias] = source

    def fake_run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        runtime_id = command[2]
        alias = next(key for key, value in MODELS.items() if value == runtime_id)
        return SimpleNamespace(
            returncode=0,
            stdout=f'FROM "{sources[alias]}"\n',
            stderr="",
        )

    monkeypatch.setattr(optimization.subprocess, "run", fake_run)
    runtime = tmp_path / "runtime"
    dry = optimization.stage_ollama_artifacts(tmp_path, runtime, apply=False)
    assert dry["apply"] is False
    applied = optimization.stage_ollama_artifacts(tmp_path, runtime, apply=True)
    assert Path(str(applied["manifest"])).is_file()
    for alias, source in sources.items():
        staged = runtime / "models/llama-router" / alias / f"{alias}.gguf"
        assert staged.is_symlink()
        assert staged.resolve() == source.resolve()

    policy = _policy()
    staging = policy["artifact_staging"]
    assert isinstance(staging, dict)
    staging["network_downloads_allowed"] = True
    monkeypatch.setattr(
        optimization,
        "root_contract",
        lambda _root, name: policy if name == "optimization_policy.yaml" else _catalog(),
    )
    with pytest.raises(ValueError, match="staging réseau interdit"):
        optimization.stage_ollama_artifacts(tmp_path, runtime, apply=False)

    monkeypatch.setattr(optimization, "root_contract", _root_contract)
    monkeypatch.setattr(
        optimization.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stdout="", stderr="absent"),
    )
    with pytest.raises(ValueError, match="modèle Ollama local requis absent"):
        optimization.stage_ollama_artifacts(tmp_path, runtime, apply=False)


def test_runtime_comparison_eligible_and_keep_baseline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(optimization, "root_contract", _root_contract)
    baseline = _series(
        tmp_path,
        "base",
        [
            _evidence(f"b{i}", "runtime", "baseline", "fedora", "ollama-vulkan")
            for i in range(3)
        ],
    )
    candidate = _series(
        tmp_path,
        "candidate",
        [
            _evidence(
                f"c{i}",
                "runtime",
                "llama-cpp-vulkan",
                "fedora",
                "llama-cpp-vulkan",
                tps=12.0,
            )
            for i in range(3)
        ],
    )
    report = optimization.compare_runtime(tmp_path, baseline, candidate)
    assert report.verdict == "ELIGIBLE_FOR_HUMAN_PROMOTION"
    assert report.aggregate_improvement_pct == 20.0

    regressions = _series(
        tmp_path,
        "regression",
        [
            _evidence(
                f"r{i}",
                "runtime",
                "llama-cpp-vulkan",
                "fedora",
                "llama-cpp-vulkan",
                tps=9.0,
                functional=i != 0,
            )
            for i in range(3)
        ],
    )
    report = optimization.compare_runtime(tmp_path, baseline, regressions)
    assert report.verdict == "KEEP_BASELINE"
    assert "functional_or_security_gate_failed" in report.reasons
    assert any("aggregate_improvement_below" in reason for reason in report.reasons)
    assert any("regression_exceeds" in reason for reason in report.reasons)

    with pytest.raises(ValueError, match="3 runs minimum"):
        optimization.compare_runtime(tmp_path, baseline[:1], candidate[:1])


def test_runtime_comparison_rejects_mixed_series(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(optimization, "root_contract", _root_contract)
    mixed = _series(
        tmp_path,
        "mixed",
        [
            _evidence(
                f"m{i}",
                "runtime",
                "baseline" if i < 2 else "other",
                "fedora",
                "ollama-vulkan",
            )
            for i in range(3)
        ],
    )
    with pytest.raises(ValueError, match="mélange kind/candidate"):
        optimization.compare_runtime(tmp_path, mixed, mixed)


def test_kernel_comparison_and_wrong_kernel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(optimization, "root_contract", _root_contract)
    baseline = _series(
        tmp_path,
        "kernel-base",
        [
            _evidence(
                f"b{i}",
                "kernel",
                "fedora-official",
                "6.17-fedora",
                "ollama-vulkan",
            )
            for i in range(3)
        ],
    )
    candidate = _series(
        tmp_path,
        "kernel-candidate",
        [
            _evidence(
                f"c{i}",
                "kernel",
                "upstream-7.2.3",
                "7.2.3-openclaw-l6",
                "ollama-vulkan",
                tps=10.5,
            )
            for i in range(3)
        ],
    )
    report = optimization.compare_kernel(tmp_path, baseline, candidate)
    assert report.verdict == "ELIGIBLE_FOR_HUMAN_PROMOTION"
    assert report.candidate_id == "upstream-7.2.3"

    wrong = _series(
        tmp_path,
        "kernel-wrong",
        [
            _evidence(
                f"w{i}",
                "kernel",
                "upstream-7.2.3",
                "7.2.2",
                "ollama-vulkan",
            )
            for i in range(3)
        ],
    )
    with pytest.raises(ValueError, match="candidat kernel doit dériver de 7.2.3"):
        optimization.compare_kernel(tmp_path, baseline, wrong)

    wrong_id = _series(
        tmp_path,
        "kernel-wrong-id",
        [
            _evidence(
                f"x{i}",
                "kernel",
                "untrusted-candidate",
                "7.2.3-openclaw-l6",
                "ollama-vulkan",
            )
            for i in range(3)
        ],
    )
    with pytest.raises(ValueError, match="candidate_id candidat kernel invalide"):
        optimization.compare_kernel(tmp_path, baseline, wrong_id)


def test_model_challenger_comparison(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(optimization, "root_contract", _root_contract)
    incumbent_ids = {"gemma-deep": "gemma3:12b-it-q4_K_M"}
    challenger_ids = {"gemma-deep": "ministral-3:14b-instruct-2512-q4_K_M"}
    incumbent = _series(
        tmp_path,
        "incumbent",
        [
            _evidence(
                f"i{index}",
                "model-challenger",
                "gemma3",
                "fedora",
                "ollama-vulkan",
                runtime_ids=incumbent_ids,
            )
            for index in range(3)
        ],
    )
    challenger = _series(
        tmp_path,
        "challenger",
        [
            _evidence(
                f"c{index}",
                "model-challenger",
                "ministral",
                "fedora",
                "ollama-vulkan",
                runtime_ids=challenger_ids,
                extra={
                    "vision_pass": True,
                    "document_quality_pass": True,
                    "tool_calling_pass": True,
                },
            )
            for index in range(3)
        ],
    )
    report = optimization.compare_model_challenger(tmp_path, incumbent, challenger)
    assert report.verdict == "ELIGIBLE_FOR_HUMAN_PROMOTION"

    failed = _series(
        tmp_path,
        "challenger-failed",
        [
            _evidence(
                f"f{index}",
                "model-challenger",
                "ministral",
                "fedora",
                "ollama-vulkan",
                runtime_ids=challenger_ids,
                tps=9.0,
                extra={
                    "vision_pass": index != 0,
                    "document_quality_pass": False,
                    "tool_calling_pass": True,
                },
            )
            for index in range(3)
        ],
    )
    report = optimization.compare_model_challenger(tmp_path, incumbent, failed)
    assert report.verdict == "KEEP_BASELINE"
    assert "challenger_vision_pass_failed" in report.reasons
    assert "challenger_document_quality_pass_failed" in report.reasons
    assert any("performance_regression_exceeds" in reason for reason in report.reasons)


def test_decision_and_required_models_guards(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = optimization.ComparisonReport(
        kind="runtime",
        candidate_id="candidate",
        verdict="KEEP_BASELINE",
        aggregate_improvement_pct=0.0,
        per_model_change_pct={"qwen-max": 0.0},
        reasons=("test",),
        baseline_runs=("b1",),
        candidate_runs=("c1",),
    )
    output = optimization.write_decision(report, tmp_path / "decision.json")
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["automatic_promotion"] is False

    invalid = optimization.ComparisonReport(
        kind="runtime",
        candidate_id="candidate",
        verdict="PROMOTE_NOW",
        aggregate_improvement_pct=0.0,
        per_model_change_pct={},
        reasons=(),
        baseline_runs=(),
        candidate_runs=(),
    )
    with pytest.raises(ValueError, match="verdict décision invalide"):
        optimization.write_decision(invalid, tmp_path / "invalid.json")

    monkeypatch.setattr(
        optimization,
        "root_contract",
        lambda _root, _name: {"models": {"only": {"required": True}}},
    )
    with pytest.raises(ValueError, match="exactement trois modèles"):
        optimization._required_models(tmp_path)
