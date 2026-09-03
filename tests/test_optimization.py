from __future__ import annotations

import json
import os
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


def _model_payload(runtime_ids: dict[str, str], tps: float) -> dict[str, object]:
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
    *,
    kind: str,
    candidate_id: str,
    kernel: str,
    backend: str,
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
        "models": _model_payload(runtime_ids or MODELS, tps),
        "contexts": [8192],
        "prompt_hashes": ["prompt-a", "prompt-b"],
        "functional_pass": functional,
        "security_pass": True,
        "metrics": {"cases": 9},
    }
    if extra:
        payload.update(extra)
    return payload


def _write_series(tmp_path: Path, prefix: str, payloads: list[dict[str, object]]) -> list[Path]:
    paths: list[Path] = []
    for index, payload in enumerate(payloads, start=1):
        path = tmp_path / f"{prefix}-{index}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        paths.append(path)
    return paths


def test_safe_path_and_modelfile_helpers(tmp_path: Path) -> None:
    target = optimization._safe_relative(tmp_path, "models/x")
    assert target == (tmp_path / "models/x").resolve()
    with pytest.raises(ValueError, match="chemin relatif interdit"):
        optimization._safe_relative(tmp_path, "../escape")
    with pytest.raises(ValueError, match="chemin relatif interdit"):
        optimization._safe_relative(tmp_path, str(tmp_path / "absolute"))

    model = tmp_path / "model.gguf"
    projector = tmp_path / "projector.gguf"
    model.write_bytes(b"model")
    projector.write_bytes(b"projector")
    text = f'FROM "{model}"\nPROJECTOR "{projector}"\nPARAMETER x 1\n'
    refs = optimization._modelfile_refs(text)
    assert refs == [("FROM", model.resolve()), ("PROJECTOR", projector.resolve())]
    with pytest.raises(ValueError, match="Modelfile invalide"):
        optimization._modelfile_refs('FROM "unterminated')


def test_stage_ollama_artifacts_dry_run_and_apply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(optimization, "root_contract", _root_contract)
    sources: dict[str, Path] = {}
    projectors: dict[str, Path] = {}
    for alias in MODELS:
        source = tmp_path / f"{alias}.gguf"
        projector = tmp_path / f"{alias}-mmproj.gguf"
        source.write_bytes(f"model:{alias}".encode())
        projector.write_bytes(f"projector:{alias}".encode())
        sources[alias] = source
        projectors[alias] = projector

    def fake_run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        runtime_id = command[2]
        alias = next(key for key, value in MODELS.items() if value == runtime_id)
        stdout = f'FROM "{sources[alias]}"\nPROJECTOR "{projectors[alias]}"\n'
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(optimization.subprocess, "run", fake_run)
    dry = optimization.stage_ollama_artifacts(tmp_path, tmp_path / "runtime", apply=False)
    assert dry["apply"] is False
    assert set(dry["models"]) == set(MODELS)

    applied = optimization.stage_ollama_artifacts(tmp_path, tmp_path / "runtime", apply=True)
    manifest = Path(str(applied["manifest"]))
    assert manifest.is_file()
    for alias in MODELS:
        staged = tmp_path / "runtime/models/llama-router" / alias / f"{alias}.gguf"
        assert staged.is_symlink()
        assert staged.resolve() == sources[alias].resolve()


def test_stage_rejects_network_missing_model_and_ambiguous_from(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
        optimization.stage_ollama_artifacts(tmp_path, tmp_path / "runtime", apply=False)

    monkeypatch.setattr(optimization, "root_contract", _root_contract)
    monkeypatch.setattr(
        optimization.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stdout="", stderr="absent"),
    )
    with pytest.raises(ValueError, match="modèle Ollama local requis absent"):
        optimization.stage_ollama_artifacts(tmp_path, tmp_path / "runtime", apply=False)

    source_a = tmp_path / "a.gguf"
    source_b = tmp_path / "b.gguf"
    source_a.write_bytes(b"a")
    source_b.write_bytes(b"b")
    monkeypatch.setattr(
        optimization.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout=f"FROM {source_a}\nFROM {source_b}\n",
            stderr="",
        ),
    )
    with pytest.raises(ValueError, match="exactement un artefact FROM"):
        optimization.stage_ollama_artifacts(tmp_path, tmp_path / "runtime", apply=False)


def test_load_evidence_and_write_decision(tmp_path: Path) -> None:
    path = tmp_path / "evidence.json"
    payload = _evidence(
        "run-1",
        kind="runtime",
        candidate_id="llama-cpp-vulkan",
        kernel="fedora",
        backend="llama-cpp-vulkan",
    )
    path.write_text(json.dumps(payload), encoding="utf-8")
    loaded = optimization.load_evidence(path)
    assert loaded["run_id"] == "run-1"

    report = optimization.ComparisonReport(
        kind="runtime",
        candidate_id="llama-cpp-vulkan",
        verdict="KEEP_BASELINE",
        aggregate_improvement_pct=0.0,
        per_model_change_pct={"qwen-max": 0.0},
        reasons=("test",),
        baseline_runs=("b1",),
        candidate_runs=("c1",),
    )
    output = optimization.write_decision(report, tmp_path / "decision/result.json")
    decision = json.loads(output.read_text(encoding="utf-8"))
    assert decision["automatic_promotion"] is False
    assert decision["verdict"] == "KEEP_BASELINE"

    bad_report = optimization.ComparisonReport(
        kind="runtime",
        candidate_id="x",
        verdict="PROMOTE_NOW",
        aggregate_improvement_pct=0.0,
        per_model_change_pct={},
        reasons=(),
        baseline_runs=(),
        candidate_runs=(),
    )
    with pytest.raises(ValueError, match="verdict décision invalide"):
        optimization.write_decision(bad_report, tmp_path / "bad.json")


def test_load_evidence_rejects_bad_schema_missing_fields_and_model_metrics(
    tmp_path: Path,
) -> None:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"schema_version": "0"}), encoding="utf-8")
    with pytest.raises(ValueError, match="schéma preuve invalide"):
        optimization.load_evidence(path)

    path.write_text(json.dumps({"schema_version": "1.0.0"}), encoding="utf-8")
    with pytest.raises(ValueError, match="preuve incomplète"):
        optimization.load_evidence(path)

    payload = _evidence(
        "run",
        kind="runtime",
        candidate_id="x",
        kernel="k",
        backend="b",
    )
    payload["models"] = {}
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="preuve sans modèles"):
        optimization.load_evidence(path)

    payload["models"] = {"qwen-max": {"runtime_id": "x"}}
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="digest absent"):
        optimization.load_evidence(path)


def test_compare_runtime_eligible_and_regression(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(optimization, "root_contract", _root_contract)
    baseline = _write_series(
        tmp_path,
        "runtime-base",
        [
            _evidence(
                f"b{index}",
                kind="runtime",
                candidate_id="baseline",
                kernel="fedora-6",
                backend="ollama-vulkan",
                tps=10.0,
            )
            for index in range(3)
        ],
    )
    candidate = _write_series(
        tmp_path,
        "runtime-candidate",
        [
            _evidence(
                f"c{index}",
                kind="runtime",
                candidate_id="llama-cpp-vulkan",
                kernel="fedora-6",
                backend="llama-cpp-vulkan",
                tps=12.0,
            )
            for index in range(3)
        ],
    )
    report = optimization.compare_runtime(tmp_path, baseline, candidate)
    assert report.verdict == "ELIGIBLE_FOR_HUMAN_PROMOTION"
    assert report.aggregate_improvement_pct == 20.0

    failing_payloads = [
        _evidence(
            f"f{index}",
            kind="runtime",
            candidate_id="llama-cpp-vulkan",
            kernel="fedora-6",
            backend="llama-cpp-vulkan",
            tps=9.0,
            functional=index != 0,
        )
        for index in range(3)
    ]
    failing = _write_series(tmp_path, "runtime-failing", failing_payloads)
    report = optimization.compare_runtime(tmp_path, baseline, failing)
    assert report.verdict == "KEEP_BASELINE"
    assert "functional_or_security_gate_failed" in report.reasons
    assert any("aggregate_improvement_below" in reason for reason in report.reasons)
    assert any("regression_exceeds" in reason for reason in report.reasons)


def test_compare_runtime_rejects_insufficient_and_mismatched_series(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(optimization, "root_contract", _root_contract)
    one = _write_series(
        tmp_path,
        "one",
        [
            _evidence(
                "one",
                kind="runtime",
                candidate_id="baseline",
                kernel="fedora",
                backend="ollama-vulkan",
            )
        ],
    )
    with pytest.raises(ValueError, match="3 runs minimum"):
        optimization.compare_runtime(tmp_path, one, one)

    mixed = _write_series(
        tmp_path,
        "mixed",
        [
            _evidence(
                f"m{index}",
                kind="runtime",
                candidate_id="baseline" if index < 2 else "other",
                kernel="fedora",
                backend="ollama-vulkan",
            )
            for index in range(3)
        ],
    )
    with pytest.raises(ValueError, match="mélange kind/candidate"):
        optimization.compare_runtime(tmp_path, mixed, mixed)


def test_compare_kernel_eligible_and_rejects_wrong_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(optimization, "root_contract", _root_contract)
    baseline = _write_series(
        tmp_path,
        "kernel-base",
        [
            _evidence(
                f"kb{index}",
                kind="kernel",
                candidate_id="fedora-official",
                kernel="6.17-fedora",
                backend="ollama-vulkan",
                tps=10.0,
            )
            for index in range(3)
        ],
    )
    candidate = _write_series(
        tmp_path,
        "kernel-candidate",
        [
            _evidence(
                f"kc{index}",
                kind="kernel",
                candidate_id="upstream-7.2.3",
                kernel="7.2.3",
                backend="ollama-vulkan",
                tps=10.5,
            )
            for index in range(3)
        ],
    )
    report = optimization.compare_kernel(tmp_path, baseline, candidate)
    assert report.verdict == "ELIGIBLE_FOR_HUMAN_PROMOTION"
    assert report.aggregate_improvement_pct == 5.0

    wrong = _write_series(
        tmp_path,
        "kernel-wrong",
        [
            _evidence(
                f"kw{index}",
                kind="kernel",
                candidate_id="upstream",
                kernel="7.2.2",
                backend="ollama-vulkan",
                tps=11.0,
            )
            for index in range(3)
        ],
    )
    with pytest.raises(ValueError, match="candidat kernel doit être 7.2.3"):
        optimization.compare_kernel(tmp_path, baseline, wrong)


def test_compare_model_challenger_eligible_and_gate_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(optimization, "root_contract", _root_contract)
    incumbent_id = {"gemma-deep": "gemma3:12b-it-q4_K_M"}
    challenger_id = {"gemma-deep": "ministral-3:14b-instruct-2512-q4_K_M"}
    incumbent = _write_series(
        tmp_path,
        "incumbent",
        [
            _evidence(
                f"i{index}",
                kind="model-challenger",
                candidate_id="gemma3",
                kernel="fedora",
                backend="ollama-vulkan",
                runtime_ids=incumbent_id,
                tps=10.0,
            )
            for index in range(3)
        ],
    )
    challenger = _write_series(
        tmp_path,
        "challenger",
        [
            _evidence(
                f"m{index}",
                kind="model-challenger",
                candidate_id="ministral",
                kernel="fedora",
                backend="ollama-vulkan",
                runtime_ids=challenger_id,
                tps=10.0,
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

    failed_payloads = [
        _evidence(
            f"mf{index}",
            kind="model-challenger",
            candidate_id="ministral",
            kernel="fedora",
            backend="ollama-vulkan",
            runtime_ids=challenger_id,
            tps=9.0,
            extra={
                "vision_pass": index != 0,
                "document_quality_pass": False,
                "tool_calling_pass": True,
            },
        )
        for index in range(3)
    ]
    failed = _write_series(tmp_path, "challenger-failed", failed_payloads)
    report = optimization.compare_model_challenger(tmp_path, incumbent, failed)
    assert report.verdict == "KEEP_BASELINE"
    assert "challenger_vision_pass_failed" in report.reasons
    assert "challenger_document_quality_pass_failed" in report.reasons
    assert any("performance_regression_exceeds" in reason for reason in report.reasons)


def test_required_models_rejects_incomplete_catalog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        optimization,
        "root_contract",
        lambda _root, _name: {"models": {"only": {"required": True}}},
    )
    with pytest.raises(ValueError, match="exactement trois modèles"):
        optimization._required_models(tmp_path)


def test_sha256_is_stable(tmp_path: Path) -> None:
    path = tmp_path / "payload"
    path.write_bytes(b"abc")
    assert optimization._sha256(path) == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
    assert not os.path.isabs("models/llama-router")
