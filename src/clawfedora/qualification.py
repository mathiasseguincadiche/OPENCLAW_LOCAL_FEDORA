from __future__ import annotations

import hashlib
import json
import math
import platform
import shutil
import statistics
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from clawfedora.core_config import load_yaml, resolve_runtime_root, root_contract
from clawfedora.hardware_gate import collect_hardware_gate, write_hardware_evidence


@dataclass(frozen=True)
class PlannedCase:
    model_alias: str
    runtime_id: str
    family: str
    context: int
    scenario: dict[str, Any]
    max_output_tokens: int
    think: bool | None
    thinking_mode: str


@dataclass(frozen=True)
class QualificationPlan:
    cases: tuple[PlannedCase, ...]
    qwen_native_cases: tuple[str, ...]

    @property
    def contexts(self) -> dict[int, int]:
        result: dict[int, int] = {}
        for case in self.cases:
            result[case.context] = result.get(case.context, 0) + 1
        return result


def _loopback_endpoint(endpoint: str) -> bool:
    parsed = urlparse(endpoint)
    return parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}


def _request_json(
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    method = "POST" if data is not None else "GET"
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        result = json.loads(response.read().decode("utf-8"))
    if not isinstance(result, dict):
        raise ValueError(f"réponse JSON non objet: {url}")
    return result


def _scenario_output_limit(scenario: dict[str, Any], suite: dict[str, Any]) -> int:
    value = int(scenario.get("max_output_tokens", suite.get("default_max_output_tokens", 256)))
    if value < 32 or value > 1024:
        raise ValueError(f"limite de sortie scénario invalide: {value}")
    return value


def _selected_models(
    catalog: dict[str, Any],
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    models = catalog.get("models", {})
    if not isinstance(models, dict):
        raise ValueError("model_catalog.yaml: models invalide")
    selected: list[dict[str, Any]] = []
    for alias in policy.get("required_models", []):
        raw = models.get(str(alias))
        if not isinstance(raw, dict):
            raise ValueError(f"modèle requis inconnu: {alias}")
        if raw.get("provider") != "ollama":
            raise ValueError(f"{alias}: provider Ollama requis pour L5 baseline")
        selected.append({"alias": str(alias), **raw})
    if len(selected) != 3:
        raise ValueError("L5 exige exactement trois modèles")
    return selected


def build_plan(
    catalog: dict[str, Any],
    policy: dict[str, Any],
    suite: dict[str, Any],
) -> QualificationPlan:
    selected = _selected_models(catalog, policy)
    scenarios_raw = suite.get("scenarios", [])
    if not isinstance(scenarios_raw, list) or len(scenarios_raw) != 12:
        raise ValueError("suite L5: exactement 12 scénarios requis")
    scenarios = {
        str(item["id"]): item
        for item in scenarios_raw
        if isinstance(item, dict) and item.get("id")
    }
    if len(scenarios) != 12:
        raise ValueError("suite L5: ids scénarios invalides ou dupliqués")

    automated = policy.get("automated_gates", {})
    matrix = automated.get("scenario_matrix", {})
    if not isinstance(matrix, dict):
        raise ValueError("qualification: scenario_matrix invalide")
    qwen_native = tuple(str(value) for value in automated.get("qwen_native_cases", []))
    qwen_native_set = set(qwen_native)
    required_contexts = [int(value) for value in policy.get("required_contexts", [])]
    if required_contexts != [8192, 16384]:
        raise ValueError("qualification: contextes requis 8192 et 16384")

    qwen_native_max = int(dict(policy["full_gate"])["qwen_native_max_output_tokens"])
    planned: list[PlannedCase] = []
    covered_8k: set[str] = set()
    for model in selected:
        alias = str(model["alias"])
        family = str(model.get("family", "")).casefold()
        model_matrix = matrix.get(alias)
        if not isinstance(model_matrix, dict):
            raise ValueError(f"qualification: matrice absente pour {alias}")
        for context in required_contexts:
            scenario_ids = model_matrix.get(str(context))
            if not isinstance(scenario_ids, list) or not scenario_ids:
                raise ValueError(f"qualification: matrice vide {alias}/{context}")
            normalized_ids = [str(value) for value in scenario_ids]
            if len(normalized_ids) != len(set(normalized_ids)):
                raise ValueError(f"qualification: doublon {alias}/{context}")
            for scenario_id in normalized_ids:
                scenario = scenarios.get(scenario_id)
                if scenario is None:
                    raise ValueError(f"qualification: scénario inconnu {scenario_id}")
                limit = _scenario_output_limit(scenario, suite)
                native_key = f"{context}:{scenario_id}"
                if family == "qwen" and native_key in qwen_native_set:
                    max_output = max(limit, qwen_native_max)
                    think: bool | None = None
                    thinking_mode = "native"
                elif family in {"qwen", "gemma"}:
                    max_output = limit
                    think = False
                    thinking_mode = "off"
                else:
                    max_output = limit
                    think = None
                    thinking_mode = "not_applicable"
                planned.append(
                    PlannedCase(
                        model_alias=alias,
                        runtime_id=str(model["runtime_id"]),
                        family=family,
                        context=context,
                        scenario=scenario,
                        max_output_tokens=max_output,
                        think=think,
                        thinking_mode=thinking_mode,
                    )
                )
                if context == 8192:
                    covered_8k.add(scenario_id)

    full = dict(policy["full_gate"])
    if len(planned) != int(full["total_cases"]):
        raise ValueError(f"qualification: {len(planned)} cas, attendu {full['total_cases']}")
    context_counts = {
        context: sum(case.context == context for case in planned)
        for context in required_contexts
    }
    expected_contexts = {
        int(key): int(value) for key, value in dict(full["contexts"]).items()
    }
    if context_counts != expected_contexts:
        raise ValueError(f"qualification: distribution contextes invalide {context_counts}")
    if covered_8k != set(scenarios):
        missing = sorted(set(scenarios) - covered_8k)
        raise ValueError(f"qualification: couverture collective 8K incomplète: {missing}")
    if len(qwen_native) != int(full["qwen_native_reasoning_probes"]):
        raise ValueError("qualification: nombre de probes Qwen natifs incohérent")
    observed_native = {
        f"{case.context}:{case.scenario['id']}"
        for case in planned
        if case.model_alias == "qwen-max" and case.thinking_mode == "native"
    }
    if observed_native != qwen_native_set:
        raise ValueError("qualification: probes Qwen natifs non matérialisés exactement")
    per_model = {
        alias: sum(case.model_alias == alias for case in planned)
        for alias in ("qwen-max", "gemma-deep", "devstral-devops")
    }
    if set(per_model.values()) != {10}:
        raise ValueError(f"qualification: chaque modèle doit avoir 10 cas: {per_model}")
    return QualificationPlan(tuple(planned), qwen_native)


def _synthetic_context(characters: int) -> str:
    if characters <= 0:
        return ""
    lines: list[str] = []
    index = 1
    while sum(len(item) for item in lines) < characters:
        lines.append(
            f"host-{index:04d}: role=example env=synthetic state=unknown owner=team-{index % 7}\n"
        )
        index += 1
    return "".join(lines)[:characters]


def _prompt_for(case: PlannedCase) -> str:
    synthetic = int(case.scenario.get("synthetic_context_chars", 0) or 0)
    prefix = _synthetic_context(synthetic)
    prompt = str(case.scenario["prompt"])
    if prefix:
        return f"INVENTAIRE SYNTHÉTIQUE NON-PRODUCTION:\n{prefix}\nCONSIGNE:\n{prompt}"
    return prompt


def _generation_payload(case: PlannedCase) -> dict[str, Any]:
    options = {
        "num_ctx": case.context,
        "temperature": float(case.scenario.get("temperature", 0.1)),
        "num_predict": case.max_output_tokens,
    }
    payload: dict[str, Any] = {
        "model": case.runtime_id,
        "messages": [{"role": "user", "content": _prompt_for(case)}],
        "stream": True,
        "options": options,
    }
    if case.think is not None:
        payload["think"] = case.think
    return payload


def _run_generation(
    endpoint: str,
    case: PlannedCase,
    *,
    deadline: float,
) -> dict[str, Any]:
    remaining = deadline - time.perf_counter()
    if remaining <= 0:
        raise TimeoutError("budget du cas épuisé avant appel")
    request = urllib.request.Request(
        f"{endpoint.rstrip('/')}/api/chat",
        data=json.dumps(_generation_payload(case)).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    first_generation: float | None = None
    first_response: float | None = None
    output_chunks: list[str] = []
    thinking_chars = 0
    final: dict[str, Any] = {}
    with urllib.request.urlopen(request, timeout=max(1.0, remaining)) as response:  # noqa: S310
        for raw_line in response:
            if time.perf_counter() >= deadline:
                raise TimeoutError("timeout mural du cas atteint")
            line = raw_line.decode("utf-8").strip()
            if not line:
                continue
            event = json.loads(line)
            if not isinstance(event, dict):
                continue
            message = event.get("message", {})
            if not isinstance(message, dict):
                message = {}
            thinking = str(message.get("thinking", ""))
            content = str(message.get("content", ""))
            if (thinking or content) and first_generation is None:
                first_generation = time.perf_counter()
            if content and first_response is None:
                first_response = time.perf_counter()
            thinking_chars += len(thinking)
            output_chunks.append(content)
            if event.get("done") is True:
                final = event
    ended = time.perf_counter()
    if ended > deadline:
        raise TimeoutError("timeout mural du cas atteint")

    eval_count = int(final.get("eval_count") or 0)
    eval_duration = int(final.get("eval_duration") or 0)
    prompt_count = int(final.get("prompt_eval_count") or 0)
    prompt_duration = int(final.get("prompt_eval_duration") or 0)
    done_reason = str(final.get("done_reason") or "") or None
    truncated = bool(
        done_reason and done_reason.casefold() in {"length", "max_tokens", "limit"}
    ) or eval_count >= case.max_output_tokens
    return {
        "output": "".join(output_chunks).strip(),
        "first_generation_ms": (
            (first_generation - started) * 1000 if first_generation is not None else None
        ),
        "response_ttft_ms": (
            (first_response - started) * 1000 if first_response is not None else None
        ),
        "wall_ms": (ended - started) * 1000,
        "eval_count": eval_count,
        "tokens_per_second": (
            eval_count / eval_duration * 1_000_000_000 if eval_duration > 0 else None
        ),
        "prompt_eval_count": prompt_count,
        "prompt_tokens_per_second": (
            prompt_count / prompt_duration * 1_000_000_000 if prompt_duration > 0 else None
        ),
        "load_duration_ms": float(final.get("load_duration") or 0) / 1_000_000,
        "thinking_chars": thinking_chars,
        "done_reason": done_reason,
        "output_truncated": truncated,
    }


def _casefold_contains(output: str, needle: str) -> bool:
    return needle.casefold() in output.casefold()


def _check_json_keys(output: str, keys: list[str]) -> bool:
    try:
        value = json.loads(output)
    except json.JSONDecodeError:
        return False
    return isinstance(value, dict) and all(key in value for key in keys)


def _check_yaml_keys(output: str, keys: list[str]) -> bool:
    try:
        value = yaml.safe_load(output)
    except yaml.YAMLError:
        return False
    return isinstance(value, dict) and all(key in value for key in keys)


def run_checks(output: str, checks: list[Any]) -> tuple[bool, list[str]]:
    details: list[str] = []
    passed = True
    for raw in checks:
        if not isinstance(raw, dict):
            passed = False
            details.append("invalid_check:fail")
            continue
        kind = str(raw.get("type", ""))
        values = [str(value) for value in raw.get("values", [])]
        keys = [str(value) for value in raw.get("keys", [])]
        if kind == "nonempty":
            ok = bool(output.strip())
        elif kind == "contains_all":
            ok = all(_casefold_contains(output, value) for value in values)
        elif kind == "contains_any":
            ok = any(_casefold_contains(output, value) for value in values)
        elif kind == "not_contains_any":
            ok = not any(_casefold_contains(output, value) for value in values)
        elif kind == "json_keys":
            ok = _check_json_keys(output, keys)
        elif kind == "yaml_keys":
            ok = _check_yaml_keys(output, keys)
        else:
            ok = False
        passed = passed and ok
        details.append(f"{kind}:{'pass' if ok else 'fail'}")
    return passed, details


def _percentile95(values: list[float]) -> float:
    if not values:
        return math.inf
    ordered = sorted(values)
    rank = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return ordered[rank]


def evaluate_cases(policy: dict[str, Any], cases: list[dict[str, Any]]) -> dict[str, Any]:
    thresholds = dict(dict(policy["automated_gates"])["thresholds"])
    total = len(cases)
    errors = sum(item.get("status") != "ok" for item in cases)
    checks = sum(item.get("check_passed") is True for item in cases)
    error_rate = errors / total if total else 1.0
    check_rate = checks / total if total else 0.0
    token_rates = [
        float(item["tokens_per_second"])
        for item in cases
        if isinstance(item.get("tokens_per_second"), (int, float))
    ]
    first_tokens = [
        float(item["first_token_ms"])
        for item in cases
        if isinstance(item.get("first_token_ms"), (int, float))
    ]
    median_tps = statistics.median(token_rates) if token_rates else 0.0
    p95_first = _percentile95(first_tokens)
    per_context: dict[str, float] = {}
    for context in (8192, 16384):
        subset = [item for item in cases if int(item.get("context", 0)) == context]
        passed = sum(item.get("check_passed") is True for item in subset)
        per_context[str(context)] = passed / len(subset) if subset else 0.0

    failures: list[str] = []
    if error_rate > float(thresholds["max_error_rate"]):
        failures.append("error_rate")
    if check_rate < float(thresholds["min_check_pass_rate"]):
        failures.append("check_pass_rate")
    if len(token_rates) != total:
        failures.append("missing_tokens_per_second")
    if len(first_tokens) != total:
        failures.append("missing_first_token_ms")
    if median_tps < float(thresholds["min_median_tokens_per_second"]):
        failures.append("median_tokens_per_second")
    if p95_first > float(thresholds["max_p95_first_token_ms"]):
        failures.append("p95_first_token_ms")
    context_thresholds = dict(thresholds["per_context_min_check_pass_rate"])
    for context, observed in per_context.items():
        if observed < float(context_thresholds[context]):
            failures.append(f"context_{context}_check_pass_rate")

    model_metrics: dict[str, dict[str, float]] = {}
    for alias in ("qwen-max", "gemma-deep", "devstral-devops"):
        subset = [item for item in cases if item.get("model_alias") == alias]
        rates = [
            float(item["tokens_per_second"])
            for item in subset
            if isinstance(item.get("tokens_per_second"), (int, float))
        ]
        model_metrics[alias] = {
            "median_tokens_per_second": statistics.median(rates) if rates else 0.0,
            "check_pass_rate": (
                sum(item.get("check_passed") is True for item in subset) / len(subset)
                if subset
                else 0.0
            ),
        }
    return {
        "verdict": "PASS" if not failures else "FAIL",
        "failures": failures,
        "metrics": {
            "error_rate": error_rate,
            "check_pass_rate": check_rate,
            "median_tokens_per_second": median_tps,
            "p95_first_token_ms": p95_first,
            "per_context_check_pass_rate": per_context,
            "per_model": model_metrics,
        },
        "thresholds": thresholds,
    }


def _rpm_version(package: str) -> str | None:
    executable = shutil.which("rpm")
    if executable is None:
        return None
    completed = subprocess.run(
        [executable, "-q", package],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def _performance_profile() -> dict[str, Any]:
    command = shutil.which("powerprofilesctl")
    if command:
        completed = subprocess.run(
            [command, "get"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        value = completed.stdout.strip().casefold()
        return {"source": "powerprofilesctl", "value": value, "ok": value == "performance"}
    governors: set[str] = set()
    for path in Path("/sys/devices/system/cpu").glob("cpu*/cpufreq/scaling_governor"):
        try:
            governors.add(path.read_text(encoding="utf-8").strip().casefold())
        except OSError:
            continue
    return {
        "source": "scaling_governor",
        "value": ",".join(sorted(governors)) or "unavailable",
        "ok": bool(governors) and governors == {"performance"},
    }


def _model_inventory(
    tags: dict[str, Any],
    required: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    raw_models = tags.get("models", [])
    if not isinstance(raw_models, list):
        raise ValueError("Ollama /api/tags: models invalide")
    indexed: dict[str, dict[str, Any]] = {}
    for raw in raw_models:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or raw.get("model") or "")
        if name:
            indexed[name.casefold()] = raw
    inventory: list[dict[str, Any]] = []
    for model in required:
        runtime_id = str(model["runtime_id"])
        raw = indexed.get(runtime_id.casefold())
        if raw is None:
            raise ValueError(f"modèle requis absent, aucun download implicite: {runtime_id}")
        details = raw.get("details", {})
        if not isinstance(details, dict):
            details = {}
        digest = str(raw.get("digest") or "")
        quantization = str(details.get("quantization_level") or "")
        if not digest or not quantization:
            raise ValueError(f"identité Ollama incomplète: {runtime_id}")
        inventory.append(
            {
                "alias": model["alias"],
                "runtime_id": runtime_id,
                "digest": digest,
                "size": int(raw.get("size") or 0),
                "format": details.get("format"),
                "family": details.get("family"),
                "parameter_size": details.get("parameter_size"),
                "quantization_level": quantization,
            }
        )
    return inventory


def _evidence_directory(runtime_root: Path) -> Path:
    return runtime_root / "proofs" / "qualification"


def _write_evidence(runtime_root: Path, payload: dict[str, Any]) -> Path:
    directory = _evidence_directory(runtime_root)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    path = directory / f"hard40_{stamp}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _case_evidence(
    case: PlannedCase,
    result: dict[str, Any],
    passed: bool,
    details: list[str],
) -> dict[str, Any]:
    output = str(result.pop("output"))
    first_token = (
        result["first_generation_ms"]
        if case.thinking_mode == "native"
        else result["response_ttft_ms"]
    )
    native_ok = case.thinking_mode != "native" or int(result["thinking_chars"]) > 0
    if not native_ok:
        passed = False
        details.append("native_thinking:fail")
    metrics_ok = (
        isinstance(first_token, (int, float))
        and isinstance(result.get("tokens_per_second"), (int, float))
        and float(result["tokens_per_second"]) > 0
    )
    if not metrics_ok:
        passed = False
        details.append("performance_metrics:fail")
    case_error = bool(result["output_truncated"]) or not metrics_ok
    return {
        "model_alias": case.model_alias,
        "runtime_id": case.runtime_id,
        "context": case.context,
        "scenario_id": case.scenario["id"],
        "category": case.scenario.get("category"),
        "max_output_tokens": case.max_output_tokens,
        "thinking_mode": case.thinking_mode,
        "status": "error" if case_error else "ok",
        "check_passed": passed and not case_error,
        "check_details": details,
        "first_token_ms": first_token,
        "output_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
        "output_chars": len(output),
        **result,
    }


def _format_duration(seconds: float) -> str:
    value = max(0, int(round(seconds)))
    minutes, secs = divmod(value, 60)
    return f"{minutes}m{secs:02d}s"


def dry_run(repo_root: Path) -> dict[str, Any]:
    policy = root_contract(repo_root, "qualification_policy.yaml")
    catalog = root_contract(repo_root, "model_catalog.yaml")
    suite = load_yaml(repo_root / "benchmarks" / "suites" / "linux_devops_v1.yaml")
    if suite.get("id") != policy.get("suite"):
        raise ValueError("qualification: suite incohérente")
    plan = build_plan(catalog, policy, suite)
    return {
        "verdict": "PASS",
        "mode": "DRY-RUN",
        "gate": dict(policy["full_gate"])["name"],
        "cases": len(plan.cases),
        "contexts": plan.contexts,
        "qwen_native_probes": len(plan.qwen_native_cases),
        "qwen_native_max_output_tokens": dict(policy["full_gate"])[
            "qwen_native_max_output_tokens"
        ],
        "case_timeout_seconds": dict(policy["full_gate"])["case_timeout_seconds"],
        "max_wall_seconds": dict(policy["full_gate"])["max_wall_seconds"],
        "required_models": list(policy["required_models"]),
        "preflight": ["L2", "L3", "performance-profile", "ollama-model-identity"],
        "suspend_protection": "systemd-inhibit",
        "cloud_calls_allowed": False,
    }


def run_qualification(
    repo_root: Path,
    *,
    runtime_root: Path | None = None,
    endpoint: str = "http://127.0.0.1:11434",
) -> tuple[int, Path | None]:
    started_at = datetime.now(UTC)
    started = time.perf_counter()
    runtime = runtime_root or resolve_runtime_root()
    policy = root_contract(repo_root, "qualification_policy.yaml")
    catalog = root_contract(repo_root, "model_catalog.yaml")
    suite = load_yaml(repo_root / "benchmarks" / "suites" / "linux_devops_v1.yaml")
    plan = build_plan(catalog, policy, suite)
    full = dict(policy["full_gate"])
    total_budget = float(full["max_wall_seconds"])
    reserve = float(full["evaluation_reserve_seconds"])
    case_timeout = float(full["case_timeout_seconds"])
    total_deadline = started + total_budget

    if not _loopback_endpoint(endpoint):
        print(f"QUALIFICATION_RESULT=FAIL endpoint non-loopback: {endpoint}")
        return 2, None

    evidence_dir = _evidence_directory(runtime)
    l2 = collect_hardware_gate(repo_root, "l2")
    l2_path = write_hardware_evidence(l2, evidence_dir)
    if not l2.ok:
        print(f"QUALIFICATION_RESULT=FAIL L2 evidence={l2_path}")
        return 2, l2_path
    l3 = collect_hardware_gate(repo_root, "l3")
    l3_path = write_hardware_evidence(l3, evidence_dir)
    if not l3.ok:
        print(f"QUALIFICATION_RESULT=FAIL L3 evidence={l3_path}")
        return 2, l3_path

    profile = _performance_profile()
    if bool(dict(policy["preflight"])["performance_profile_required"]) and not profile["ok"]:
        print(
            "QUALIFICATION_RESULT=FAIL performance profile requis: "
            f"source={profile['source']} value={profile['value']}"
        )
        return 2, None

    try:
        remaining = max(1.0, total_deadline - time.perf_counter() - reserve)
        tags = _request_json(
            f"{endpoint.rstrip('/')}/api/tags",
            timeout=min(10.0, remaining),
        )
        version = _request_json(
            f"{endpoint.rstrip('/')}/api/version",
            timeout=min(10.0, remaining),
        )
        required = _selected_models(catalog, policy)
        identities = _model_inventory(tags, required)
    except (OSError, urllib.error.URLError, json.JSONDecodeError, ValueError) as exc:
        print(f"QUALIFICATION_RESULT=FAIL preflight Ollama: {exc}")
        return 2, None

    benchmark_deadline = total_deadline - reserve
    budget_left = benchmark_deadline - time.perf_counter()
    if budget_left <= 0:
        print("QUALIFICATION_RESULT=FAIL HARD_TIMEOUT avant benchmark")
        return 2, None

    contexts = ",".join(f"{key}:{value}" for key, value in sorted(plan.contexts.items()))
    print(
        "BENCHMARK_PLAN "
        f"modeles=3 cas={len(plan.cases)} context_cases={contexts} "
        f"qwen_native_probes={len(plan.qwen_native_cases)} "
        f"qwen_native_max={full['qwen_native_max_output_tokens']} "
        f"hard_wall={int(total_budget)}s case_timeout={int(case_timeout)}s"
    )
    cases: list[dict[str, Any]] = []
    fail_fast_error: str | None = None
    for current, case in enumerate(plan.cases, start=1):
        now = time.perf_counter()
        remaining_global = benchmark_deadline - now
        if remaining_global <= 0:
            fail_fast_error = "HARD_TIMEOUT benchmark"
            break
        case_deadline = min(benchmark_deadline, now + case_timeout)
        print(
            f"[{current}/{len(plan.cases)}] {case.model_alias} ctx={case.context} "
            f"scenario={case.scenario['id']} max_out={case.max_output_tokens} "
            f"thinking={case.thinking_mode} budget_left={_format_duration(remaining_global)}"
        )
        try:
            result = _run_generation(endpoint, case, deadline=case_deadline)
            passed, details = run_checks(
                str(result["output"]),
                list(case.scenario.get("checks", [])),
            )
            case_payload = _case_evidence(case, result, passed, details)
            cases.append(case_payload)
            verdict = "PASS" if case_payload["check_passed"] else "CHECK_FAIL"
            print(
                f"    {verdict} wall={float(case_payload['wall_ms']) / 1000:.1f}s "
                f"first_tok={case_payload['first_token_ms']}ms "
                f"tok/s={case_payload['tokens_per_second']}"
            )
            if case_payload["output_truncated"]:
                fail_fast_error = "sortie tronquée"
                break
            if case_payload["status"] == "error":
                fail_fast_error = "métriques de performance incomplètes"
                break
        except (
            OSError,
            urllib.error.URLError,
            TimeoutError,
            json.JSONDecodeError,
            ValueError,
        ) as exc:
            cases.append(
                {
                    "model_alias": case.model_alias,
                    "runtime_id": case.runtime_id,
                    "context": case.context,
                    "scenario_id": case.scenario["id"],
                    "thinking_mode": case.thinking_mode,
                    "status": "error",
                    "check_passed": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            fail_fast_error = f"{type(exc).__name__}: {exc}"
            break

    if time.perf_counter() >= total_deadline:
        fail_fast_error = fail_fast_error or "HARD_TIMEOUT qualification"
    evaluation = (
        evaluate_cases(policy, cases)
        if len(cases) == len(plan.cases)
        else {
            "verdict": "FAIL",
            "failures": [fail_fast_error or "matrice incomplète"],
            "metrics": {},
            "thresholds": dict(dict(policy["automated_gates"])["thresholds"]),
        }
    )
    if fail_fast_error and fail_fast_error not in evaluation["failures"]:
        evaluation["failures"].append(fail_fast_error)
        evaluation["verdict"] = "FAIL"

    finished_at = datetime.now(UTC)
    total_wall = time.perf_counter() - started
    if total_wall > total_budget:
        evaluation["verdict"] = "FAIL"
        evaluation["failures"].append("HARD_TIMEOUT qualification > 2400s")

    payload = {
        "schema_version": "1.0.0",
        "protocol": "fedora-hard40-v1",
        "suite": suite["id"],
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "total_wall_seconds": total_wall,
        "max_wall_seconds": total_budget,
        "case_timeout_seconds": case_timeout,
        "kernel": platform.release(),
        "mesa": _rpm_version("mesa-vulkan-drivers"),
        "ollama_version": version.get("version"),
        "performance_profile": profile,
        "endpoint": endpoint,
        "cloud_calls_allowed": False,
        "model_identities": identities,
        "scenario_matrix": dict(policy["automated_gates"])["scenario_matrix"],
        "qwen_native_cases": list(plan.qwen_native_cases),
        "hardware_evidence": {"l2": str(l2_path), "l3": str(l3_path)},
        "cases": cases,
        "evaluation": evaluation,
        "promotion": {
            "backend": False,
            "kernel": False,
            "v1": False,
            "human_review_required": True,
        },
    }
    path = _write_evidence(runtime, payload)
    print(f"EVIDENCE={path}")
    print(
        f"QUALIFICATION_RESULT={evaluation['verdict']} "
        f"cases={len(cases)}/{len(plan.cases)} duration={_format_duration(total_wall)}"
    )
    return (0 if evaluation["verdict"] == "PASS" else 2), path
