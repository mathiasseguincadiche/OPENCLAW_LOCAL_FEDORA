from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from clawfedora import optimization_runner

ROOT = Path(__file__).resolve().parents[1]


class FakeResponse:
    def __init__(self, lines: list[bytes] | None = None, payload: bytes = b"{}") -> None:
        self.lines = lines or []
        self.payload = payload

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self.lines)

    def read(self) -> bytes:
        return self.payload


def test_mapping_loopback_context_prompt_and_p95() -> None:
    assert optimization_runner._mapping({"x": 1}) == {"x": 1}
    with pytest.raises(ValueError, match="objet attendu"):
        optimization_runner._mapping([])
    assert optimization_runner._loopback("http://127.0.0.1:11434") is True
    assert optimization_runner._loopback("http://localhost:8080/v1") is False
    assert optimization_runner._loopback("http://[::1]:8080/v1") is False
    assert optimization_runner._loopback("https://127.0.0.1:8080") is False
    assert optimization_runner._loopback("http://example.com:8080") is False

    context = optimization_runner._synthetic_context(250)
    assert len(context) == 250
    assert "env=synthetic" in context
    assert optimization_runner._prompt({"prompt": "hello"}) == "hello"
    synthetic = optimization_runner._prompt(
        {"prompt": "hello", "synthetic_context_chars": 100}
    )
    assert synthetic.startswith("INVENTAIRE SYNTHÉTIQUE NON-PRODUCTION")
    assert synthetic.endswith("CONSIGNE:\nhello")
    assert optimization_runner._p95([]) == float("inf")
    assert optimization_runner._p95([1.0, 2.0, 3.0, 100.0]) == 100.0


def test_request_json_and_backend_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(_request: object, timeout: float) -> FakeResponse:
        assert timeout == 3
        return FakeResponse(payload=b'{"ok": true}')

    monkeypatch.setattr(optimization_runner.urllib.request, "urlopen", fake_urlopen)
    assert optimization_runner._request_json(
        "http://127.0.0.1:1/test",
        {"x": 1},
        timeout=3,
    ) == {"ok": True}

    calls: list[str] = []

    def fake_request(url: str, **_kwargs: object) -> dict[str, Any]:
        calls.append(url)
        if url.endswith("/models"):
            return {"data": []}
        return {"version": "ok"}

    monkeypatch.setattr(optimization_runner, "_request_json", fake_request)
    optimization_runner._backend_ready("ollama-vulkan", "http://127.0.0.1:11434")
    optimization_runner._backend_ready("llama-cpp-vulkan", "http://127.0.0.1:8081/v1")
    assert any(url.endswith("/api/version") for url in calls)
    assert any(url.endswith("/models") for url in calls)

    monkeypatch.setattr(
        optimization_runner,
        "_request_json",
        lambda *_args, **_kwargs: {"data": {}},
    )
    with pytest.raises(ValueError, match="inventaire llama.cpp invalide"):
        optimization_runner._backend_ready(
            "llama-cpp-vulkan",
            "http://127.0.0.1:8081/v1",
        )


def test_build_l6_cases_uses_exact_nine_cases() -> None:
    cases = optimization_runner.build_l6_cases(ROOT)
    assert len(cases) == 9
    assert {case.model_alias for case in cases} == set(optimization_runner.L6_SCENARIOS)
    assert all(case.quantization == "Q4_K_M" for case in cases)
    assert all(case.max_output_tokens <= 512 for case in cases)


def test_ollama_case_stream_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    events = [
        {
            "message": {"content": "hello"},
            "done": False,
        },
        {
            "message": {"content": " world"},
            "done": True,
            "eval_count": 20,
            "eval_duration": 2_000_000_000,
            "prompt_eval_count": 10,
            "prompt_eval_duration": 1_000_000_000,
            "done_reason": "stop",
        },
    ]
    lines = [(json.dumps(event) + "\n").encode() for event in events]
    monkeypatch.setattr(
        optimization_runner.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse(lines=lines),
    )
    case = optimization_runner.L6Case(
        model_alias="qwen-max",
        runtime_id="model",
        quantization="Q4_K_M",
        scenario_id="scenario",
        prompt="hello",
        checks=[],
        max_output_tokens=32,
    )
    result = optimization_runner._ollama_case("http://127.0.0.1:11434", case, 10)
    assert result["output"] == "hello world"
    assert result["tokens_per_second"] == 10.0
    assert result["prompt_tokens_per_second"] == 10.0
    assert result["output_tokens"] == 20
    assert result["finish_reason"] == "stop"

    incomplete = [(json.dumps({"message": {"content": ""}, "done": True}) + "\n").encode()]
    monkeypatch.setattr(
        optimization_runner.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse(lines=incomplete),
    )
    with pytest.raises(ValueError, match="métriques Ollama incomplètes"):
        optimization_runner._ollama_case("http://127.0.0.1:11434", case, 10)


def test_llama_case_stream_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    events = [
        {
            "choices": [
                {
                    "delta": {"content": "hello"},
                    "finish_reason": None,
                }
            ]
        },
        {
            "timings": {
                "predicted_per_second": 14.5,
                "prompt_per_second": 30.0,
                "predicted_n": 12,
            },
            "choices": [
                {
                    "delta": {"content": " world"},
                    "finish_reason": "stop",
                }
            ],
        },
    ]
    lines = [f"data: {json.dumps(event)}\n".encode() for event in events]
    lines.append(b"data: [DONE]\n")
    monkeypatch.setattr(
        optimization_runner.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse(lines=lines),
    )
    case = optimization_runner.L6Case(
        model_alias="qwen-max",
        runtime_id="model",
        quantization="Q4_K_M",
        scenario_id="scenario",
        prompt="hello",
        checks=[],
        max_output_tokens=32,
    )
    result = optimization_runner._llama_case("http://127.0.0.1:8081/v1", case, 10)
    assert result["output"] == "hello world"
    assert result["tokens_per_second"] == 14.5
    assert result["prompt_tokens_per_second"] == 30.0
    assert result["output_tokens"] == 12
    assert result["finish_reason"] == "stop"

    monkeypatch.setattr(
        optimization_runner.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse(lines=[b"data: [DONE]\n"]),
    )
    with pytest.raises(ValueError, match="métriques llama.cpp incomplètes"):
        optimization_runner._llama_case("http://127.0.0.1:8081/v1", case, 10)


def test_artifact_identities_and_ram(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    model_dir = runtime_root / "models/llama-router"
    model_dir.mkdir(parents=True)
    manifest = {
        "models": {
            alias: {"sha256": f"digest-{alias}"}
            for alias in optimization_runner.L6_SCENARIOS
        }
    }
    (model_dir / "ARTIFACT_MANIFEST.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    identities = optimization_runner._artifact_identities(ROOT, runtime_root)
    assert set(identities) == set(optimization_runner.L6_SCENARIOS)
    assert all(value["quantization"] == "Q4_K_M" for value in identities.values())
    assert optimization_runner._ram_mib() > 0


def test_run_performance_snapshot_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identities = {
        alias: {
            "runtime_id": f"runtime-{alias}",
            "digest": f"digest-{alias}",
            "quantization": "Q4_K_M",
        }
        for alias in optimization_runner.L6_SCENARIOS
    }
    monkeypatch.setattr(optimization_runner, "_backend_ready", lambda *_args: None)
    monkeypatch.setattr(
        optimization_runner,
        "_artifact_identities",
        lambda *_args: identities,
    )
    monkeypatch.setattr(optimization_runner, "_vram_mib", lambda: 4096.0)
    monkeypatch.setattr(optimization_runner, "_ram_mib", lambda: 8192.0)
    monkeypatch.setattr(
        optimization_runner,
        "run_checks",
        lambda _output, _checks: (True, ["ok"]),
    )
    monkeypatch.setattr(
        optimization_runner,
        "_ollama_case",
        lambda _endpoint, _case, _timeout: {
            "output": "valid output",
            "first_token_ms": 50.0,
            "wall_ms": 100.0,
            "tokens_per_second": 10.0,
            "prompt_tokens_per_second": 20.0,
            "output_tokens": 10,
            "finish_reason": "stop",
        },
    )
    output = tmp_path / "proofs/snapshot.json"
    result = optimization_runner.run_performance_snapshot(
        ROOT,
        tmp_path / "runtime",
        backend="ollama-vulkan",
        endpoint="http://127.0.0.1:11434",
        kind="runtime",
        candidate_id="ollama-vulkan",
        output=output,
    )
    assert result == output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["functional_pass"] is True
    assert payload["security_pass"] is True
    assert payload["metrics"]["cases"] == 9
    assert payload["metrics"]["passed_cases"] == 9
    assert payload["raw_outputs_persisted"] is False
    assert payload["cloud_calls_allowed"] is False
    assert len(payload["cases"]) == 9
    assert all(value["median_tokens_per_second"] == 10.0 for value in payload["models"].values())


def test_run_performance_snapshot_records_case_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identities = {
        alias: {
            "runtime_id": f"runtime-{alias}",
            "digest": f"digest-{alias}",
            "quantization": "Q4_K_M",
        }
        for alias in optimization_runner.L6_SCENARIOS
    }
    monkeypatch.setattr(optimization_runner, "_backend_ready", lambda *_args: None)
    monkeypatch.setattr(
        optimization_runner,
        "_artifact_identities",
        lambda *_args: identities,
    )
    monkeypatch.setattr(optimization_runner, "_vram_mib", lambda: 1.0)
    monkeypatch.setattr(optimization_runner, "_ram_mib", lambda: 2.0)
    monkeypatch.setattr(
        optimization_runner,
        "_llama_case",
        lambda *_args: (_ for _ in ()).throw(ValueError("boom")),
    )
    output = tmp_path / "error.json"
    optimization_runner.run_performance_snapshot(
        ROOT,
        tmp_path / "runtime",
        backend="llama-cpp-vulkan",
        endpoint="http://127.0.0.1:8081/v1",
        kind="kernel",
        candidate_id="upstream-7.2.3",
        output=output,
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["functional_pass"] is False
    assert payload["metrics"]["passed_cases"] == 0
    assert all(case["status"] == "error" for case in payload["cases"])
    assert all(case["error"] == "boom" for case in payload["cases"])


def test_snapshot_rejects_invalid_backend_kind_and_endpoint(tmp_path: Path) -> None:
    common = {
        "repo_root": ROOT,
        "runtime_root": tmp_path,
        "candidate_id": "x",
        "output": tmp_path / "x.json",
    }
    with pytest.raises(ValueError, match="backend invalide"):
        optimization_runner.run_performance_snapshot(
            backend="invalid",
            endpoint="http://127.0.0.1:1",
            kind="runtime",
            **common,
        )
    with pytest.raises(ValueError, match="kind invalide"):
        optimization_runner.run_performance_snapshot(
            backend="ollama-vulkan",
            endpoint="http://127.0.0.1:1",
            kind="invalid",
            **common,
        )
    with pytest.raises(ValueError, match="endpoint loopback obligatoire"):
        optimization_runner.run_performance_snapshot(
            backend="ollama-vulkan",
            endpoint="http://example.com:1",
            kind="runtime",
            **common,
        )
