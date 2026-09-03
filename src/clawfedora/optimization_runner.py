from __future__ import annotations

import hashlib
import json
import math
import platform
import statistics
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from clawfedora.core_config import load_yaml, root_contract
from clawfedora.qualification import run_checks

L6_SCENARIOS: dict[str, tuple[str, ...]] = {
    "qwen-max": (
        "project-intake-analysis",
        "systemd-service-debug",
        "web-freshness-discipline",
    ),
    "gemma-deep": (
        "project-intake-analysis",
        "terraform-multifile-change",
        "rollback-runbook",
    ),
    "devstral-devops": (
        "systemd-service-debug",
        "kubernetes-root-cause",
        "ansible-idempotence",
    ),
}


@dataclass(frozen=True)
class L6Case:
    model_alias: str
    runtime_id: str
    quantization: str
    scenario_id: str
    prompt: str
    checks: list[Any]
    max_output_tokens: int


def _mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("L6 runner: objet attendu")
    return value


def _loopback(endpoint: str) -> bool:
    parsed = urlparse(endpoint)
    return parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}


def _request_json(url: str, payload: dict[str, Any] | None = None, timeout: float = 10) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if data is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        value = json.loads(response.read().decode("utf-8"))
    return _mapping(value)


def _synthetic_context(characters: int) -> str:
    rows: list[str] = []
    index = 1
    while sum(len(row) for row in rows) < characters:
        rows.append(
            f"node-{index:04d}: env=synthetic service=example state=unknown owner=team-{index % 5}\n"
        )
        index += 1
    return "".join(rows)[:characters]


def _prompt(scenario: dict[str, Any]) -> str:
    body = str(scenario.get("prompt", ""))
    synthetic = int(scenario.get("synthetic_context_chars", 0) or 0)
    if synthetic:
        return f"INVENTAIRE SYNTHÉTIQUE NON-PRODUCTION:\n{_synthetic_context(synthetic)}\nCONSIGNE:\n{body}"
    return body


def build_l6_cases(repo_root: Path) -> list[L6Case]:
    suite = load_yaml(repo_root / "benchmarks/suites/linux_devops_v1.yaml")
    scenarios_raw = suite.get("scenarios", [])
    if not isinstance(scenarios_raw, list):
        raise ValueError("L6 runner: suite scénarios invalide")
    scenarios = {
        str(item.get("id")): item
        for item in scenarios_raw
        if isinstance(item, dict) and item.get("id")
    }
    catalog = root_contract(repo_root, "model_catalog.yaml")
    models = _mapping(catalog.get("models"))
    cases: list[L6Case] = []
    for alias, scenario_ids in L6_SCENARIOS.items():
        model = _mapping(models.get(alias))
        runtime_id = str(model.get("runtime_id", ""))
        quantization = str(model.get("quantization", ""))
        if not runtime_id or not quantization:
            raise ValueError(f"L6 runner: identité modèle incomplète: {alias}")
        for scenario_id in scenario_ids:
            scenario = _mapping(scenarios.get(scenario_id))
            max_output = min(512, int(scenario.get("max_output_tokens", 256) or 256))
            cases.append(
                L6Case(
                    model_alias=alias,
                    runtime_id=runtime_id,
                    quantization=quantization,
                    scenario_id=scenario_id,
                    prompt=_prompt(scenario),
                    checks=list(scenario.get("checks", [])),
                    max_output_tokens=max_output,
                )
            )
    if len(cases) != 9:
        raise ValueError("L6 runner: exactement 9 cas de comparaison requis")
    return cases


def _artifact_identities(repo_root: Path, runtime_root: Path) -> dict[str, dict[str, str]]:
    policy = root_contract(repo_root, "optimization_policy.yaml")
    relative = str(_mapping(policy.get("paths")).get("llama_models", ""))
    value = Path(relative)
    if not relative or value.is_absolute() or ".." in value.parts:
        raise ValueError("L6 runner: chemin manifest artefact invalide")
    manifest_path = runtime_root.resolve() / value / "ARTIFACT_MANIFEST.json"
    manifest = _mapping(json.loads(manifest_path.read_text(encoding="utf-8")))
    staged = _mapping(manifest.get("models"))
    catalog = _mapping(root_contract(repo_root, "model_catalog.yaml").get("models"))
    result: dict[str, dict[str, str]] = {}
    for alias in L6_SCENARIOS:
        entry = _mapping(staged.get(alias))
        model = _mapping(catalog.get(alias))
        digest = str(entry.get("sha256", ""))
        runtime_id = str(model.get("runtime_id", ""))
        quantization = str(model.get("quantization", ""))
        if not digest or not runtime_id or not quantization:
            raise ValueError(f"L6 runner: identité artefact incomplète: {alias}")
        result[alias] = {
            "runtime_id": runtime_id,
            "digest": digest,
            "quantization": quantization,
        }
    return result


def _vram_mib() -> float:
    values: list[int] = []
    for path in Path("/sys/class/drm").glob("card*/device/mem_info_vram_used"):
        try:
            values.append(int(path.read_text(encoding="utf-8").strip()))
        except (OSError, ValueError):
            continue
    if not values:
        raise ValueError("L6 runner: télémétrie VRAM xe indisponible")
    return max(values) / (1024 * 1024)


def _ram_mib() -> float:
    fields: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        key, _, raw = line.partition(":")
        if key in {"MemTotal", "MemAvailable"}:
            fields[key] = int(raw.strip().split()[0])
    if set(fields) != {"MemTotal", "MemAvailable"}:
        raise ValueError("L6 runner: télémétrie RAM indisponible")
    return (fields["MemTotal"] - fields["MemAvailable"]) / 1024


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    if not ordered:
        return math.inf
    index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return ordered[index]


def _ollama_case(endpoint: str, case: L6Case, timeout: float) -> dict[str, Any]:
    payload = {
        "model": case.runtime_id,
        "messages": [{"role": "user", "content": case.prompt}],
        "stream": True,
        "think": False,
        "options": {
            "num_ctx": 8192,
            "num_predict": case.max_output_tokens,
            "temperature": 0.1,
        },
    }
    request = urllib.request.Request(
        f"{endpoint.rstrip('/')}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    first: float | None = None
    content: list[str] = []
    final: dict[str, Any] = {}
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        for raw in response:
            line = raw.decode("utf-8").strip()
            if not line:
                continue
            event = _mapping(json.loads(line))
            message = event.get("message", {})
            message = message if isinstance(message, dict) else {}
            chunk = str(message.get("content", ""))
            if chunk and first is None:
                first = time.perf_counter()
            content.append(chunk)
            if event.get("done") is True:
                final = event
    ended = time.perf_counter()
    eval_count = int(final.get("eval_count") or 0)
    eval_duration = int(final.get("eval_duration") or 0)
    prompt_count = int(final.get("prompt_eval_count") or 0)
    prompt_duration = int(final.get("prompt_eval_duration") or 0)
    if first is None or eval_count <= 0 or eval_duration <= 0:
        raise ValueError("L6 runner: métriques Ollama incomplètes")
    return {
        "output": "".join(content).strip(),
        "first_token_ms": (first - started) * 1000,
        "wall_ms": (ended - started) * 1000,
        "tokens_per_second": eval_count / eval_duration * 1_000_000_000,
        "prompt_tokens_per_second": (
            prompt_count / prompt_duration * 1_000_000_000 if prompt_duration > 0 else None
        ),
        "output_tokens": eval_count,
        "finish_reason": final.get("done_reason"),
    }


def _llama_case(endpoint: str, case: L6Case, timeout: float) -> dict[str, Any]:
    payload = {
        "model": case.runtime_id,
        "messages": [{"role": "user", "content": case.prompt}],
        "max_tokens": case.max_output_tokens,
        "temperature": 0.1,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    request = urllib.request.Request(
        f"{endpoint.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    first: float | None = None
    content: list[str] = []
    timings: dict[str, Any] = {}
    finish_reason: str | None = None
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        for raw in response:
            line = raw.decode("utf-8").strip()
            if not line or line.startswith(":"):
                continue
            if line.startswith("data:"):
                line = line[5:].strip()
            if line == "[DONE]":
                continue
            event = _mapping(json.loads(line))
            if isinstance(event.get("timings"), dict):
                timings = dict(event["timings"])
            choices = event.get("choices", [])
            if not isinstance(choices, list) or not choices:
                continue
            choice = choices[0]
            if not isinstance(choice, dict):
                continue
            delta = choice.get("delta", {})
            delta = delta if isinstance(delta, dict) else {}
            chunk = str(delta.get("content") or "")
            reasoning = str(delta.get("reasoning_content") or "")
            if (chunk or reasoning) and first is None:
                first = time.perf_counter()
            content.append(chunk)
            if choice.get("finish_reason"):
                finish_reason = str(choice["finish_reason"])
    ended = time.perf_counter()
    tps = timings.get("predicted_per_second")
    prompt_tps = timings.get("prompt_per_second")
    output_tokens = int(timings.get("predicted_n") or 0)
    if first is None or not isinstance(tps, (int, float)) or float(tps) <= 0:
        raise ValueError("L6 runner: métriques llama.cpp incomplètes")
    return {
        "output": "".join(content).strip(),
        "first_token_ms": (first - started) * 1000,
        "wall_ms": (ended - started) * 1000,
        "tokens_per_second": float(tps),
        "prompt_tokens_per_second": (
            float(prompt_tps) if isinstance(prompt_tps, (int, float)) else None
        ),
        "output_tokens": output_tokens,
        "finish_reason": finish_reason,
    }


def _backend_ready(backend: str, endpoint: str) -> None:
    if backend == "ollama-vulkan":
        _request_json(f"{endpoint.rstrip('/')}/api/version", timeout=5)
        return
    models = _request_json(f"{endpoint.rstrip('/')}/models", timeout=5)
    data = models.get("data", [])
    if not isinstance(data, list):
        raise ValueError("L6 runner: inventaire llama.cpp invalide")


def run_performance_snapshot(
    repo_root: Path,
    runtime_root: Path,
    *,
    backend: str,
    endpoint: str,
    kind: str,
    candidate_id: str,
    output: Path,
) -> Path:
    if backend not in {"ollama-vulkan", "llama-cpp-vulkan", "llama-cpp-sycl"}:
        raise ValueError(f"L6 runner: backend invalide: {backend}")
    if kind not in {"runtime", "kernel"}:
        raise ValueError(f"L6 runner: kind invalide: {kind}")
    if not _loopback(endpoint):
        raise ValueError("L6 runner: endpoint loopback obligatoire")
    _backend_ready(backend, endpoint)
    identities = _artifact_identities(repo_root, runtime_root)
    cases = build_l6_cases(repo_root)
    case_results: list[dict[str, Any]] = []
    max_vram = 0.0
    max_ram = 0.0
    for case in cases:
        started = time.perf_counter()
        try:
            if backend == "ollama-vulkan":
                result = _ollama_case(endpoint, case, 210)
            else:
                result = _llama_case(endpoint, case, 210)
            passed, details = run_checks(str(result.pop("output")), case.checks)
            status = "ok" if passed else "check-failed"
            error: str | None = None
        except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError, ValueError) as exc:
            result = {
                "first_token_ms": None,
                "wall_ms": (time.perf_counter() - started) * 1000,
                "tokens_per_second": None,
                "prompt_tokens_per_second": None,
                "output_tokens": 0,
                "finish_reason": None,
            }
            details = [f"{type(exc).__name__}: {exc}"]
            status = "error"
            error = str(exc)
        vram = _vram_mib()
        ram = _ram_mib()
        max_vram = max(max_vram, vram)
        max_ram = max(max_ram, ram)
        case_results.append(
            {
                "model_alias": case.model_alias,
                "runtime_id": case.runtime_id,
                "scenario_id": case.scenario_id,
                "context": 8192,
                "prompt_sha256": hashlib.sha256(case.prompt.encode("utf-8")).hexdigest(),
                "status": status,
                "check_passed": status == "ok",
                "check_details": details,
                "error": error,
                "vram_mib": vram,
                "ram_mib": ram,
                **result,
            }
        )

    model_payload: dict[str, Any] = {}
    for alias in L6_SCENARIOS:
        subset = [item for item in case_results if item["model_alias"] == alias]
        rates = [float(item["tokens_per_second"]) for item in subset if isinstance(item.get("tokens_per_second"), (int, float))]
        first = [float(item["first_token_ms"]) for item in subset if isinstance(item.get("first_token_ms"), (int, float))]
        errors = sum(item["status"] != "ok" for item in subset)
        identity = identities[alias]
        model_payload[alias] = {
            **identity,
            "median_tokens_per_second": statistics.median(rates) if rates else 0.0,
            "p95_first_token_ms": _p95(first),
            "vram_mib": max(float(item["vram_mib"]) for item in subset),
            "ram_mib": max(float(item["ram_mib"]) for item in subset),
            "error_rate": errors / len(subset),
        }

    all_pass = all(item["status"] == "ok" for item in case_results)
    prompt_hashes = sorted({str(item["prompt_sha256"]) for item in case_results})
    payload = {
        "schema_version": "1.0.0",
        "run_id": datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ"),
        "created_at": datetime.now(UTC).isoformat(),
        "kind": kind,
        "candidate_id": candidate_id,
        "kernel": platform.release(),
        "backend": backend,
        "models": model_payload,
        "contexts": [8192],
        "prompt_hashes": prompt_hashes,
        "functional_pass": all_pass,
        "security_pass": _loopback(endpoint),
        "metrics": {
            "max_vram_mib": max_vram,
            "max_ram_mib": max_ram,
            "cases": len(case_results),
            "passed_cases": sum(item["status"] == "ok" for item in case_results),
        },
        "cases": case_results,
        "raw_outputs_persisted": False,
        "cloud_calls_allowed": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output
