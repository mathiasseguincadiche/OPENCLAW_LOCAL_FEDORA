from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any, Iterable

from clawfedora.core_config import root_contract

EVIDENCE_SCHEMA = "1.0.0"
DECISION_VERDICTS = {"KEEP_BASELINE", "ELIGIBLE_FOR_HUMAN_PROMOTION"}


@dataclass(frozen=True)
class ComparisonReport:
    kind: str
    candidate_id: str
    verdict: str
    aggregate_improvement_pct: float
    per_model_change_pct: dict[str, float]
    reasons: tuple[str, ...]
    baseline_runs: tuple[str, ...]
    candidate_runs: tuple[str, ...]

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": EVIDENCE_SCHEMA,
            "generated_at": datetime.now(UTC).isoformat(),
            "kind": self.kind,
            "candidate_id": self.candidate_id,
            "verdict": self.verdict,
            "aggregate_improvement_pct": self.aggregate_improvement_pct,
            "per_model_change_pct": self.per_model_change_pct,
            "reasons": list(self.reasons),
            "baseline_runs": list(self.baseline_runs),
            "candidate_runs": list(self.candidate_runs),
            "automatic_promotion": False,
        }


def _mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("L6: objet JSON attendu")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative(root: Path, relative: str) -> Path:
    value = Path(relative)
    if not relative or value.is_absolute() or ".." in value.parts:
        raise ValueError(f"L6: chemin relatif interdit: {relative}")
    resolved_root = root.resolve()
    target = (resolved_root / value).resolve(strict=False)
    if target == resolved_root or resolved_root not in target.parents:
        raise ValueError(f"L6: chemin hors runtime: {relative}")
    return target


def _required_models(repo_root: Path) -> list[tuple[str, dict[str, Any]]]:
    catalog = root_contract(repo_root, "model_catalog.yaml")
    models = _mapping(catalog.get("models"))
    required: list[tuple[str, dict[str, Any]]] = []
    for alias, raw in models.items():
        if isinstance(raw, dict) and raw.get("required") is True:
            required.append((str(alias), raw))
    if len(required) != 3:
        raise ValueError("L6: exactement trois modèles nominaux requis")
    return required


def _modelfile_refs(text: str) -> list[tuple[str, Path]]:
    refs: list[tuple[str, Path]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            parts = shlex.split(line)
        except ValueError as exc:
            raise ValueError(f"L6: Modelfile invalide: {raw_line}") from exc
        if len(parts) < 2:
            continue
        directive = parts[0].upper()
        if directive not in {"FROM", "PROJECTOR", "ADAPTER"}:
            continue
        candidate = Path(parts[1]).expanduser()
        if candidate.is_file():
            refs.append((directive, candidate.resolve()))
    return refs


def stage_ollama_artifacts(
    repo_root: Path,
    runtime_root: Path,
    *,
    apply: bool,
) -> dict[str, Any]:
    policy = root_contract(repo_root, "optimization_policy.yaml")
    paths = _mapping(policy.get("paths"))
    staging = _mapping(policy.get("artifact_staging"))
    if staging.get("network_downloads_allowed") is not False:
        raise ValueError("L6: staging réseau interdit par contrat")
    destination = _safe_relative(runtime_root, str(paths.get("llama_models", "")))
    plan: dict[str, Any] = {
        "schema_version": EVIDENCE_SCHEMA,
        "apply": apply,
        "destination": str(destination),
        "models": {},
    }
    for alias, model in _required_models(repo_root):
        runtime_id = str(model.get("runtime_id", ""))
        if not runtime_id:
            raise ValueError(f"L6: runtime_id absent pour {alias}")
        completed = subprocess.run(
            ["ollama", "show", runtime_id, "--modelfile"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if completed.returncode != 0:
            raise ValueError(
                f"L6: modèle Ollama local requis absent/inaccessible: {runtime_id}: "
                f"{completed.stderr.strip()[:200]}"
            )
        refs = _modelfile_refs(completed.stdout)
        primary = [path for directive, path in refs if directive == "FROM"]
        if len(primary) != 1:
            raise ValueError(f"L6: exactement un artefact FROM local requis pour {alias}")
        model_entry: dict[str, Any] = {
            "runtime_id": runtime_id,
            "source": str(primary[0]),
            "sha256": _sha256(primary[0]),
            "auxiliary": [],
        }
        for directive, source in refs:
            if directive == "FROM":
                continue
            model_entry["auxiliary"].append(
                {"directive": directive, "source": str(source), "sha256": _sha256(source)}
            )
        plan["models"][alias] = model_entry
        if not apply:
            continue
        alias_dir = destination / alias
        alias_dir.mkdir(parents=True, exist_ok=True)
        target = alias_dir / f"{alias}.gguf"
        if target.exists() or target.is_symlink():
            target.unlink()
        os.symlink(primary[0], target)
        for index, auxiliary in enumerate(model_entry["auxiliary"], start=1):
            source = Path(str(auxiliary["source"]))
            prefix = "mmproj" if auxiliary["directive"] == "PROJECTOR" else "aux"
            aux_target = alias_dir / f"{prefix}-{alias}-{index}.gguf"
            if aux_target.exists() or aux_target.is_symlink():
                aux_target.unlink()
            os.symlink(source, aux_target)
    if apply:
        destination.mkdir(parents=True, exist_ok=True)
        manifest_path = destination / "ARTIFACT_MANIFEST.json"
        manifest_path.write_text(
            json.dumps(plan, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        plan["manifest"] = str(manifest_path)
    return plan


def load_evidence(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    evidence = _mapping(value)
    if evidence.get("schema_version") != EVIDENCE_SCHEMA:
        raise ValueError(f"L6: schéma preuve invalide: {path}")
    required = {
        "run_id",
        "kind",
        "candidate_id",
        "kernel",
        "backend",
        "models",
        "contexts",
        "prompt_hashes",
        "functional_pass",
        "security_pass",
        "metrics",
    }
    missing = sorted(required - set(evidence))
    if missing:
        raise ValueError(f"L6: preuve incomplète {path}: {missing}")
    models = _mapping(evidence.get("models"))
    if not models:
        raise ValueError(f"L6: preuve sans modèles: {path}")
    for alias, raw in models.items():
        model = _mapping(raw)
        for key in (
            "runtime_id",
            "digest",
            "quantization",
            "median_tokens_per_second",
            "p95_first_token_ms",
            "vram_mib",
            "ram_mib",
            "error_rate",
        ):
            if key not in model:
                raise ValueError(f"L6: {path}: {alias}.{key} absent")
    return evidence


def _load_many(paths: Iterable[Path]) -> list[dict[str, Any]]:
    result = [load_evidence(path) for path in paths]
    if not result:
        raise ValueError("L6: au moins une preuve requise")
    return result


def _identity(run: dict[str, Any]) -> dict[str, Any]:
    models = _mapping(run["models"])
    return {
        "contexts": list(run["contexts"]),
        "prompt_hashes": list(run["prompt_hashes"]),
        "models": {
            alias: {
                "runtime_id": str(_mapping(model)["runtime_id"]),
                "digest": str(_mapping(model)["digest"]),
                "quantization": str(_mapping(model)["quantization"]),
            }
            for alias, model in sorted(models.items())
        },
    }


def _assert_internal_consistency(runs: list[dict[str, Any]], label: str) -> None:
    expected = _identity(runs[0])
    kind = runs[0]["kind"]
    candidate = runs[0]["candidate_id"]
    kernel = runs[0]["kernel"]
    backend = runs[0]["backend"]
    for run in runs[1:]:
        if run["kind"] != kind or run["candidate_id"] != candidate:
            raise ValueError(f"L6: série {label} mélange kind/candidate")
        if run["kernel"] != kernel or run["backend"] != backend:
            raise ValueError(f"L6: série {label} mélange kernel/backend")
        if _identity(run) != expected:
            raise ValueError(f"L6: série {label} identité modèle/corpus divergente")


def _tps_by_model(runs: list[dict[str, Any]]) -> dict[str, float]:
    aliases = set(_mapping(runs[0]["models"]))
    for run in runs:
        if set(_mapping(run["models"])) != aliases:
            raise ValueError("L6: ensemble de modèles divergent entre runs")
    return {
        alias: median(
            float(_mapping(_mapping(run["models"])[alias])["median_tokens_per_second"])
            for run in runs
        )
        for alias in sorted(aliases)
    }


def _comparison_changes(
    baseline: list[dict[str, Any]],
    candidate: list[dict[str, Any]],
) -> tuple[float, dict[str, float]]:
    base_tps = _tps_by_model(baseline)
    candidate_tps = _tps_by_model(candidate)
    if set(base_tps) != set(candidate_tps):
        raise ValueError("L6: modèles baseline/candidat divergents")
    changes: dict[str, float] = {}
    for alias in sorted(base_tps):
        if base_tps[alias] <= 0:
            raise ValueError(f"L6: TPS baseline invalide pour {alias}")
        changes[alias] = round((candidate_tps[alias] / base_tps[alias] - 1.0) * 100.0, 4)
    aggregate = round(sum(changes.values()) / len(changes), 4)
    return aggregate, changes


def _all_gates_pass(runs: list[dict[str, Any]]) -> bool:
    return all(run.get("functional_pass") is True and run.get("security_pass") is True for run in runs)


def compare_runtime(
    repo_root: Path,
    baseline_paths: Iterable[Path],
    candidate_paths: Iterable[Path],
) -> ComparisonReport:
    policy = root_contract(repo_root, "optimization_policy.yaml")
    cfg = _mapping(policy.get("runtime_comparison"))
    baseline = _load_many(baseline_paths)
    candidate = _load_many(candidate_paths)
    minimum = int(cfg.get("minimum_repeated_runs", 0))
    if len(baseline) < minimum or len(candidate) < minimum:
        raise ValueError(f"L6: {minimum} runs minimum requis pour runtime")
    _assert_internal_consistency(baseline, "baseline")
    _assert_internal_consistency(candidate, "candidate")
    if baseline[0]["backend"] != cfg.get("baseline"):
        raise ValueError("L6: backend baseline runtime invalide")
    candidate_id = str(candidate[0]["candidate_id"])
    if candidate_id not in cfg.get("candidates", []):
        raise ValueError(f"L6: candidat runtime non autorisé: {candidate_id}")
    if baseline[0]["kernel"] != candidate[0]["kernel"]:
        raise ValueError("L6: comparaison runtime exige le même kernel")
    if _identity(baseline[0]) != _identity(candidate[0]):
        raise ValueError("L6: comparaison runtime identité modèle/corpus divergente")
    aggregate, changes = _comparison_changes(baseline, candidate)
    reasons: list[str] = []
    if not _all_gates_pass(baseline + candidate):
        reasons.append("functional_or_security_gate_failed")
    target = float(cfg.get("aggregate_improvement_target_pct", 0))
    if aggregate < target:
        reasons.append(f"aggregate_improvement_below_{target:g}_pct")
    max_regression = float(cfg.get("maximum_single_model_regression_pct", 0))
    for alias, change in changes.items():
        if change < -max_regression:
            reasons.append(f"{alias}_regression_exceeds_{max_regression:g}_pct")
    verdict = "ELIGIBLE_FOR_HUMAN_PROMOTION" if not reasons else "KEEP_BASELINE"
    return ComparisonReport(
        kind="runtime",
        candidate_id=candidate_id,
        verdict=verdict,
        aggregate_improvement_pct=aggregate,
        per_model_change_pct=changes,
        reasons=tuple(reasons),
        baseline_runs=tuple(str(run["run_id"]) for run in baseline),
        candidate_runs=tuple(str(run["run_id"]) for run in candidate),
    )


def compare_kernel(
    repo_root: Path,
    baseline_paths: Iterable[Path],
    candidate_paths: Iterable[Path],
) -> ComparisonReport:
    policy = root_contract(repo_root, "optimization_policy.yaml")
    cfg = _mapping(policy.get("kernel_comparison"))
    baseline = _load_many(baseline_paths)
    candidate = _load_many(candidate_paths)
    minimum = int(cfg.get("minimum_repeated_runs", 0))
    if len(baseline) < minimum or len(candidate) < minimum:
        raise ValueError(f"L6: {minimum} runs minimum requis pour kernel")
    _assert_internal_consistency(baseline, "kernel-baseline")
    _assert_internal_consistency(candidate, "kernel-candidate")
    if baseline[0]["backend"] != candidate[0]["backend"]:
        raise ValueError("L6: comparaison kernel exige le même backend")
    if _identity(baseline[0]) != _identity(candidate[0]):
        raise ValueError("L6: comparaison kernel identité modèle/corpus divergente")
    if str(candidate[0]["kernel"]) != "7.2.3":
        raise ValueError("L6: candidat kernel doit être 7.2.3")
    aggregate, changes = _comparison_changes(baseline, candidate)
    reasons: list[str] = []
    if not _all_gates_pass(baseline + candidate):
        reasons.append("functional_or_security_gate_failed")
    target = float(cfg.get("minimum_aggregate_improvement_pct", 0))
    if aggregate < target:
        reasons.append(f"aggregate_improvement_below_{target:g}_pct")
    max_regression = float(cfg.get("maximum_single_model_regression_pct", 0))
    for alias, change in changes.items():
        if change < -max_regression:
            reasons.append(f"{alias}_regression_exceeds_{max_regression:g}_pct")
    verdict = "ELIGIBLE_FOR_HUMAN_PROMOTION" if not reasons else "KEEP_BASELINE"
    return ComparisonReport(
        kind="kernel",
        candidate_id="upstream-7.2.3",
        verdict=verdict,
        aggregate_improvement_pct=aggregate,
        per_model_change_pct=changes,
        reasons=tuple(reasons),
        baseline_runs=tuple(str(run["run_id"]) for run in baseline),
        candidate_runs=tuple(str(run["run_id"]) for run in candidate),
    )


def compare_model_challenger(
    repo_root: Path,
    incumbent_paths: Iterable[Path],
    challenger_paths: Iterable[Path],
) -> ComparisonReport:
    policy = root_contract(repo_root, "optimization_policy.yaml")
    cfg = _mapping(policy.get("model_challenger"))
    incumbent = _load_many(incumbent_paths)
    challenger = _load_many(challenger_paths)
    minimum = int(cfg.get("minimum_repeated_runs", 0))
    if len(incumbent) < minimum or len(challenger) < minimum:
        raise ValueError(f"L6: {minimum} runs minimum requis pour challenger")
    _assert_internal_consistency(incumbent, "incumbent")
    _assert_internal_consistency(challenger, "challenger")
    if incumbent[0]["backend"] != challenger[0]["backend"]:
        raise ValueError("L6: challenger exige le même backend")
    if incumbent[0]["kernel"] != challenger[0]["kernel"]:
        raise ValueError("L6: challenger exige le même kernel")
    if list(incumbent[0]["contexts"]) != list(challenger[0]["contexts"]):
        raise ValueError("L6: challenger contextes divergents")
    if list(incumbent[0]["prompt_hashes"]) != list(challenger[0]["prompt_hashes"]):
        raise ValueError("L6: challenger corpus de prompts divergent")
    slot = str(cfg.get("slot", "gemma-deep"))
    incumbent_models = _mapping(incumbent[0]["models"])
    challenger_models = _mapping(challenger[0]["models"])
    if set(incumbent_models) != {slot} or set(challenger_models) != {slot}:
        raise ValueError("L6: preuve challenger doit contenir uniquement le slot documentaire")
    if _mapping(incumbent_models[slot])["runtime_id"] != cfg.get("incumbent"):
        raise ValueError("L6: incumbent inattendu")
    if _mapping(challenger_models[slot])["runtime_id"] != cfg.get("challenger"):
        raise ValueError("L6: challenger inattendu")
    base_tps = _tps_by_model(incumbent)[slot]
    challenger_tps = _tps_by_model(challenger)[slot]
    change = round((challenger_tps / base_tps - 1.0) * 100.0, 4)
    reasons: list[str] = []
    if not _all_gates_pass(incumbent + challenger):
        reasons.append("functional_or_security_gate_failed")
    for required_flag in ("vision_pass", "document_quality_pass", "tool_calling_pass"):
        if any(run.get(required_flag) is not True for run in challenger):
            reasons.append(f"challenger_{required_flag}_failed")
    max_regression = float(cfg.get("maximum_performance_regression_pct", 0))
    if change < -max_regression:
        reasons.append(f"performance_regression_exceeds_{max_regression:g}_pct")
    verdict = "ELIGIBLE_FOR_HUMAN_PROMOTION" if not reasons else "KEEP_BASELINE"
    return ComparisonReport(
        kind="model-challenger",
        candidate_id=str(cfg.get("challenger")),
        verdict=verdict,
        aggregate_improvement_pct=change,
        per_model_change_pct={slot: change},
        reasons=tuple(reasons),
        baseline_runs=tuple(str(run["run_id"]) for run in incumbent),
        candidate_runs=tuple(str(run["run_id"]) for run in challenger),
    )


def write_decision(report: ComparisonReport, output: Path) -> Path:
    if report.verdict not in DECISION_VERDICTS:
        raise ValueError("L6: verdict décision invalide")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report.payload(), indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output
