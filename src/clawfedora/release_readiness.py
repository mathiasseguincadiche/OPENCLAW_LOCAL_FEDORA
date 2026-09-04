from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from clawfedora.contracts import validate_repository
from clawfedora.core_config import AGENT_IDS, root_contract
from clawfedora.core_contracts import validate_core_contracts
from clawfedora.golden_contracts import validate_golden_contracts
from clawfedora.lifecycle_contracts import validate_lifecycle_contracts
from clawfedora.optimization import (
    ComparisonReport,
    compare_kernel,
    compare_model_challenger,
    compare_runtime,
    load_evidence,
)
from clawfedora.optimization_contracts import validate_optimization_contracts
from clawfedora.qualification_contracts import validate_qualification_contracts
from clawfedora.release_readiness_contracts import validate_release_readiness_contracts

REPORT_SCHEMA = "1.0.0"
READY = "READY_FOR_HUMAN_REVIEW"
BLOCKED = "BLOCKED"
APPROVED = "APPROVED_FOR_V1_PREPARATION"


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"L8: {label} doit être un objet")
    return value


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return _mapping(value, str(path))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_hash(value: Any) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _safe_evidence_path(runtime_root: Path, value: Path) -> Path:
    runtime = runtime_root.resolve()
    proofs = (runtime / "proofs").resolve()
    candidate = value if value.is_absolute() else runtime / value
    target = candidate.resolve(strict=True)
    if target == proofs or proofs not in target.parents:
        raise ValueError(f"L8: preuve hors runtime/proofs interdite: {target}")
    if not target.is_file():
        raise ValueError(f"L8: preuve non fichier: {target}")
    return target


def _reference_path(runtime_root: Path, raw: Any) -> Path:
    value = str(raw or "").strip()
    if not value:
        raise ValueError("L8: référence de preuve vide")
    path = Path(value)
    if not path.is_absolute() and not value.startswith("proofs/"):
        raise ValueError(f"L8: référence relative non canonique: {value}")
    return _safe_evidence_path(runtime_root, path)


def _relative(runtime_root: Path, path: Path) -> str:
    return path.resolve().relative_to(runtime_root.resolve()).as_posix()


def _latest(paths: list[Path]) -> Path:
    if not paths:
        raise FileNotFoundError("aucune preuve correspondante")
    return max(paths, key=lambda path: (path.stat().st_mtime_ns, path.as_posix()))


def _glob(runtime_root: Path, pattern: str) -> list[Path]:
    relative = Path(pattern)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"L8: glob interdit: {pattern}")
    return [path for path in runtime_root.resolve().glob(pattern) if path.is_file()]


def _manifest_entry(
    runtime_root: Path,
    gate: str,
    role: str,
    path: Path,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "gate": gate,
        "role": role,
        "path": _relative(runtime_root, path),
        "sha256": _sha256(path),
        "schema_version": payload.get("schema_version"),
        "verdict": payload.get("verdict") or _mapping(
            payload.get("evaluation", {}), "evaluation"
        ).get("verdict"),
    }


def _component(
    failures: tuple[str, ...] | list[str],
    warnings: tuple[str, ...] | list[str],
) -> dict[str, Any]:
    return {
        "verdict": "PASS" if not failures else "FAIL",
        "failures": list(failures),
        "warnings": list(warnings),
    }


def _software_contracts(repo_root: Path) -> tuple[dict[str, Any], list[str], list[str]]:
    components: dict[str, Any] = {}
    all_failures: list[str] = []
    all_warnings: list[str] = []

    try:
        repository = validate_repository(repo_root)
        components["repository"] = _component(repository.failures, repository.warnings)
    except (FileNotFoundError, ValueError) as exc:
        components["repository"] = _component([str(exc)], [])

    validators = (
        ("core", validate_core_contracts),
        ("lifecycle", validate_lifecycle_contracts),
        ("qualification", validate_qualification_contracts),
        ("optimization", validate_optimization_contracts),
        ("golden_projects", validate_golden_contracts),
        ("release_readiness", validate_release_readiness_contracts),
    )
    for name, validator in validators:
        try:
            failures, warnings = validator(repo_root)
            components[name] = _component(failures, warnings)
        except (FileNotFoundError, ValueError) as exc:
            components[name] = _component([str(exc)], [])

    for name, component in components.items():
        for failure in component["failures"]:
            all_failures.append(f"software.{name}: {failure}")
        for warning in component["warnings"]:
            all_warnings.append(f"software.{name}: {warning}")
    return components, all_failures, all_warnings


def _validate_hardware(payload: dict[str, Any], gate: str) -> list[str]:
    failures: list[str] = []
    if payload.get("schema_version") != "1.0.0":
        failures.append(f"{gate}: schema_version invalide")
    if payload.get("gate") != gate:
        failures.append(f"{gate}: gate de preuve invalide")
    if payload.get("verdict") != "PASS":
        failures.append(f"{gate}: verdict réel non PASS")
    checks = payload.get("checks", [])
    if not isinstance(checks, list) or not checks:
        failures.append(f"{gate}: checks matériels absents")
    elif any(isinstance(item, dict) and item.get("status") == "FAIL" for item in checks):
        failures.append(f"{gate}: au moins un check matériel FAIL")
    return failures


def _validate_l4(
    repo_root: Path,
    payload: dict[str, Any],
    cfg: dict[str, Any],
) -> list[str]:
    failures: list[str] = []
    if payload.get("schema_version") != "1.0.0" or payload.get("gate") != "L4":
        failures.append("L4: schéma/gate invalide")
    if payload.get("verdict") != cfg.get("required_verdict"):
        failures.append("L4: verdict réel non PASS")
    if payload.get("backend") != cfg.get("required_backend"):
        failures.append("L4: backend doit rester la baseline Ollama Vulkan")
    if payload.get("cloud_enabled") is not False:
        failures.append("L4: cloud_enabled doit rester false")
    if payload.get("transport") != "gateway":
        failures.append("L4: transport Gateway requis")
    smokes = payload.get("agent_smokes", [])
    if not isinstance(smokes, list) or len(smokes) != int(cfg["required_agent_smokes"]):
        failures.append("L4: exactement 8 smokes agents requis")
    else:
        observed = {
            str(item.get("agent"))
            for item in smokes
            if isinstance(item, dict) and item.get("agent")
        }
        if observed != set(AGENT_IDS):
            failures.append("L4: inventaire des 8 agents divergent")
    if not isinstance(payload.get("tool_call"), dict):
        failures.append("L4: preuve tool-calling absente")
    if not isinstance(payload.get("repair"), dict):
        failures.append("L4: preuve réparation outil absente")
    stability = payload.get("stability", [])
    if not isinstance(stability, list) or len(stability) != int(cfg["required_stability_runs"]):
        failures.append("L4: exactement 3 runs de stabilité requis")
    versions = root_contract(repo_root, "runtime_versions.yaml")
    expected = str(_mapping(versions.get("openclaw"), "runtime_versions.openclaw").get(
        "initial_qualification_pin", ""
    ))
    if expected and expected not in str(payload.get("openclaw_version", "")):
        failures.append("L4: version OpenClaw ne correspond pas au pin courant")
    return failures


def _loopback(value: Any) -> bool:
    parsed = urlparse(str(value or ""))
    return parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}


def _validate_l5(repo_root: Path, payload: dict[str, Any], cfg: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if payload.get("schema_version") != "1.0.0":
        failures.append("L5: schema_version invalide")
    if payload.get("protocol") != cfg.get("required_protocol"):
        failures.append("L5: protocole HARD-40M inattendu")
    evaluation = _mapping(payload.get("evaluation"), "L5.evaluation")
    if evaluation.get("verdict") != cfg.get("required_verdict"):
        failures.append("L5: verdict HARD-40M non PASS")
    if payload.get("cloud_calls_allowed") is not False:
        failures.append("L5: cloud calls interdits")
    if not _loopback(payload.get("endpoint")):
        failures.append("L5: endpoint non-loopback")

    policy = root_contract(repo_root, "qualification_policy.yaml")
    full = _mapping(policy.get("full_gate"), "qualification.full_gate")
    expected_thresholds = _mapping(
        _mapping(policy.get("automated_gates"), "qualification.automated_gates").get("thresholds"),
        "qualification.thresholds",
    )
    observed_thresholds = _mapping(evaluation.get("thresholds"), "L5.evaluation.thresholds")
    if observed_thresholds != expected_thresholds:
        failures.append("L5: seuils de preuve différents du contrat courant")
    if float(payload.get("max_wall_seconds", 0)) != float(full.get("max_wall_seconds", 0)):
        failures.append("L5: plafond HARD-40M différent du contrat courant")
    if float(payload.get("case_timeout_seconds", 0)) != float(full.get("case_timeout_seconds", 0)):
        failures.append("L5: timeout/cas différent du contrat courant")
    if float(payload.get("total_wall_seconds", 0)) > float(full.get("max_wall_seconds", 0)):
        failures.append("L5: durée réelle au-delà du plafond HARD-40M")
    if payload.get("scenario_matrix") != _mapping(
        policy.get("automated_gates"), "qualification.automated_gates"
    ).get("scenario_matrix"):
        failures.append("L5: matrice de scénarios différente du contrat courant")

    cases = payload.get("cases", [])
    if not isinstance(cases, list) or len(cases) != int(cfg["required_cases"]):
        failures.append("L5: exactement 30 cas mesurés requis")
    promotion = _mapping(payload.get("promotion"), "L5.promotion")
    if promotion.get("v1") is not False or promotion.get("human_review_required") is not True:
        failures.append("L5: verrou humain de promotion V1 absent")

    catalog = root_contract(repo_root, "model_catalog.yaml")
    models = _mapping(catalog.get("models"), "model_catalog.models")
    expected_models = {
        str(alias): raw
        for alias, raw in models.items()
        if isinstance(raw, dict) and raw.get("required") is True
    }
    identities = payload.get("model_identities", [])
    if not isinstance(identities, list) or len(identities) != 3:
        failures.append("L5: exactement 3 identités modèles requises")
    else:
        indexed = {
            str(item.get("alias")): item
            for item in identities
            if isinstance(item, dict) and item.get("alias")
        }
        if set(indexed) != set(expected_models):
            failures.append("L5: alias modèles divergents")
        for alias, expected in expected_models.items():
            actual = indexed.get(alias, {})
            if str(actual.get("runtime_id", "")) != str(expected.get("runtime_id", "")):
                failures.append(f"L5: runtime_id divergent pour {alias}")
            if str(actual.get("quantization_level", "")) != str(expected.get("quantization", "")):
                failures.append(f"L5: quantification divergente pour {alias}")
            if not str(actual.get("digest", "")):
                failures.append(f"L5: digest modèle absent pour {alias}")
    return failures


def _snapshot_index(
    runtime_root: Path,
    paths: list[Path],
) -> tuple[dict[str, Path], list[str]]:
    result: dict[str, Path] = {}
    failures: list[str] = []
    for raw_path in paths:
        try:
            path = _safe_evidence_path(runtime_root, raw_path)
            payload = _json(path)
        except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError) as exc:
            failures.append(f"L6: preuve illisible {raw_path}: {exc}")
            continue
        run_id = payload.get("run_id")
        if not run_id:
            continue
        key = str(run_id)
        if key in result:
            failures.append(f"L6: run_id dupliqué: {key}")
            continue
        try:
            load_evidence(path)
        except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError) as exc:
            failures.append(f"L6: snapshot invalide {path}: {exc}")
            continue
        result[key] = path
    return result, failures


def _recompute_decision(
    repo_root: Path,
    kind: str,
    baseline: list[Path],
    candidate: list[Path],
) -> ComparisonReport:
    if kind == "runtime":
        return compare_runtime(repo_root, baseline, candidate)
    if kind == "kernel":
        return compare_kernel(repo_root, baseline, candidate)
    if kind == "model-challenger":
        return compare_model_challenger(repo_root, baseline, candidate)
    raise ValueError(f"L8: kind L6 inconnu: {kind}")


def _validate_l6_decision(
    repo_root: Path,
    runtime_root: Path,
    decision_path: Path,
    decision: dict[str, Any],
    snapshots: dict[str, Path],
    accepted: set[str],
) -> tuple[list[str], list[Path]]:
    failures: list[str] = []
    if decision.get("schema_version") != "1.0.0":
        failures.append(f"L6: schema décision invalide: {decision_path}")
    if str(decision.get("verdict")) not in accepted:
        failures.append(f"L6: verdict décision interdit: {decision_path}")
    if decision.get("automatic_promotion") is not False:
        failures.append(f"L6: promotion automatique détectée: {decision_path}")

    baseline_ids = decision.get("baseline_runs", [])
    candidate_ids = decision.get("candidate_runs", [])
    if not isinstance(baseline_ids, list) or not isinstance(candidate_ids, list):
        failures.append(f"L6: listes de runs invalides: {decision_path}")
        return failures, []
    optimization = root_contract(repo_root, "optimization_policy.yaml")
    kind = str(decision.get("kind", ""))
    section = {
        "runtime": "runtime_comparison",
        "kernel": "kernel_comparison",
        "model-challenger": "model_challenger",
    }.get(kind)
    if section is None:
        failures.append(f"L6: kind décision inconnu: {kind}")
        return failures, []
    minimum = int(_mapping(optimization.get(section), f"optimization.{section}").get(
        "minimum_repeated_runs", 0
    ))
    if len(baseline_ids) < minimum or len(candidate_ids) < minimum:
        failures.append(f"L6: {kind} exige au moins {minimum} runs par série")

    input_paths: list[Path] = []
    baseline_paths: list[Path] = []
    candidate_paths: list[Path] = []
    for raw in baseline_ids:
        path = snapshots.get(str(raw))
        if path is None:
            failures.append(f"L6: snapshot baseline introuvable run_id={raw}")
        else:
            baseline_paths.append(path)
            input_paths.append(path)
    for raw in candidate_ids:
        path = snapshots.get(str(raw))
        if path is None:
            failures.append(f"L6: snapshot candidat introuvable run_id={raw}")
        else:
            candidate_paths.append(path)
            input_paths.append(path)
    if failures:
        return failures, input_paths

    try:
        computed = _recompute_decision(repo_root, kind, baseline_paths, candidate_paths)
    except (FileNotFoundError, KeyError, OSError, ValueError, ZeroDivisionError) as exc:
        failures.append(f"L6: décision non reproductible {decision_path}: {exc}")
        return failures, input_paths
    if computed.verdict != decision.get("verdict"):
        failures.append(f"L6: verdict enregistré différent du recalcul courant: {decision_path}")
    if computed.candidate_id != str(decision.get("candidate_id", "")):
        failures.append(f"L6: candidate_id enregistré différent du recalcul: {decision_path}")
    if computed.baseline_runs != tuple(str(value) for value in baseline_ids):
        failures.append(f"L6: baseline_runs divergent du recalcul: {decision_path}")
    if computed.candidate_runs != tuple(str(value) for value in candidate_ids):
        failures.append(f"L6: candidate_runs divergent du recalcul: {decision_path}")
    return failures, input_paths


def _validate_l7(payload: dict[str, Any], cfg: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if payload.get("schema_version") != "1.0.0" or payload.get("gate") != "L7":
        failures.append("L7: schéma/gate invalide")
    if payload.get("verdict") != cfg.get("required_verdict"):
        failures.append("L7: verdict réel non PASS")
    if int(payload.get("golden_projects_pass", 0)) != int(cfg["required_golden_projects"]):
        failures.append("L7: 5 Golden Projects PASS requis")
    if int(payload.get("representative_projects_pass", 0)) != int(
        cfg["required_representative_projects"]
    ):
        failures.append("L7: projet représentatif PASS requis")
    for key in ("cloud_calls_allowed", "remote_publication_allowed", "automatic_human_approval"):
        if payload.get(key) is not False:
            failures.append(f"L7: {key} doit rester false")
    if payload.get("final_human_completion") is not False:
        failures.append("L7: final_human_completion doit rester false")
    projects = payload.get("projects", [])
    if not isinstance(projects, list) or len(projects) != 6:
        failures.append("L7: exactement 6 projets de preuve requis")
    else:
        for project in projects:
            if not isinstance(project, dict):
                failures.append("L7: entrée projet invalide")
                continue
            if project.get("verdict") != "PASS":
                failures.append(f"L7: projet non PASS: {project.get('project_id')}")
            if project.get("terminal_status") != "PACKAGING":
                failures.append(f"L7: projet hors PACKAGING: {project.get('project_id')}")
            if project.get("human_gate_preserved") is not True:
                failures.append(f"L7: gate humain perdu: {project.get('project_id')}")
    telemetry = _mapping(payload.get("telemetry"), "L7.telemetry")
    if telemetry.get("local_only") is not True or int(telemetry.get("events", 0)) != 6:
        failures.append("L7: télémétrie locale des 6 projets requise")
    finops = _mapping(payload.get("finops"), "L7.finops")
    if float(finops.get("net_exposure_eur", 0.0)) != 0.0:
        failures.append("L7: exposition FinOps doit rester à 0 EUR")
    return failures


def collect_readiness(repo_root: Path, runtime_root: Path) -> dict[str, Any]:
    runtime = runtime_root.resolve()
    contract = root_contract(repo_root, "release_readiness.yaml")
    evidence_cfg = _mapping(contract.get("evidence"), "release_readiness.evidence")
    software, failures, warnings = _software_contracts(repo_root)
    manifest: list[dict[str, Any]] = []
    gates: dict[str, dict[str, Any]] = {
        "L0": {
            "status": "PASS"
            if software.get("repository", {}).get("verdict") == "PASS"
            and software.get("lifecycle", {}).get("verdict") == "PASS"
            else "BLOCKED",
            "source": "repository+lifecycle contracts",
        },
        "L1": {
            "status": "PASS" if software.get("core", {}).get("verdict") == "PASS" else "BLOCKED",
            "source": "core contracts",
        },
    }

    l5_payload: dict[str, Any] | None = None
    l5_path: Path | None = None
    try:
        l5_cfg = _mapping(evidence_cfg.get("l5"), "evidence.l5")
        l5_path = _safe_evidence_path(runtime, _latest(_glob(runtime, str(l5_cfg["glob"]))))
        l5_payload = _json(l5_path)
        l5_failures = _validate_l5(repo_root, l5_payload, l5_cfg)
        failures.extend(l5_failures)
        gates["L5"] = {
            "status": "PASS" if not l5_failures else "BLOCKED",
            "evidence": _relative(runtime, l5_path),
        }
        manifest.append(_manifest_entry(runtime, "L5", "hard40", l5_path, l5_payload))
    except (FileNotFoundError, KeyError, json.JSONDecodeError, OSError, ValueError) as exc:
        failures.append(f"L5: {exc}")
        gates["L5"] = {"status": "BLOCKED", "reason": str(exc)}

    hardware_refs = (
        _mapping(l5_payload.get("hardware_evidence"), "L5.hardware_evidence")
        if l5_payload is not None and isinstance(l5_payload.get("hardware_evidence"), dict)
        else {}
    )
    for gate_name, key in (("L2", "l2"), ("L3", "l3")):
        cfg = _mapping(evidence_cfg.get(key), f"evidence.{key}")
        try:
            raw_ref = hardware_refs.get(key)
            if raw_ref:
                path = _reference_path(runtime, raw_ref)
            else:
                path = _safe_evidence_path(
                    runtime,
                    _latest(_glob(runtime, str(cfg["fallback_glob"]))),
                )
            payload = _json(path)
            gate_failures = _validate_hardware(payload, gate_name)
            if l5_payload is not None and not raw_ref:
                gate_failures.append(f"{gate_name}: L5 ne référence pas explicitement cette preuve")
            failures.extend(gate_failures)
            gates[gate_name] = {
                "status": "PASS" if not gate_failures else "BLOCKED",
                "evidence": _relative(runtime, path),
                "linked_from_l5": bool(raw_ref),
            }
            manifest.append(_manifest_entry(runtime, gate_name, "hardware", path, payload))
        except (FileNotFoundError, KeyError, json.JSONDecodeError, OSError, ValueError) as exc:
            failures.append(f"{gate_name}: {exc}")
            gates[gate_name] = {"status": "BLOCKED", "reason": str(exc)}

    try:
        l4_cfg = _mapping(evidence_cfg.get("l4"), "evidence.l4")
        l4_path = _safe_evidence_path(runtime, _latest(_glob(runtime, str(l4_cfg["glob"]))))
        l4_payload = _json(l4_path)
        l4_failures = _validate_l4(repo_root, l4_payload, l4_cfg)
        failures.extend(l4_failures)
        gates["L4"] = {
            "status": "PASS" if not l4_failures else "BLOCKED",
            "evidence": _relative(runtime, l4_path),
        }
        manifest.append(_manifest_entry(runtime, "L4", "openclaw-e2e", l4_path, l4_payload))
    except (FileNotFoundError, KeyError, json.JSONDecodeError, OSError, ValueError) as exc:
        failures.append(f"L4: {exc}")
        gates["L4"] = {"status": "BLOCKED", "reason": str(exc)}

    l6_failures: list[str] = []
    l6_decisions: list[dict[str, Any]] = []
    try:
        l6_cfg = _mapping(evidence_cfg.get("l6"), "evidence.l6")
        l6_paths = _glob(runtime, str(l6_cfg["glob"]))
        snapshots, snapshot_failures = _snapshot_index(runtime, l6_paths)
        l6_failures.extend(snapshot_failures)
        accepted = {str(value) for value in l6_cfg.get("accepted_decision_verdicts", [])}
        required = l6_cfg.get("required_decisions", [])
        if not isinstance(required, list):
            raise ValueError("L8: required_decisions L6 invalide")
        for raw_spec in required:
            spec = _mapping(raw_spec, "L6.required_decision")
            kind = str(spec.get("kind", ""))
            candidate_id = str(spec.get("candidate_id", ""))
            matching: list[Path] = []
            for path in l6_paths:
                try:
                    payload = _json(path)
                except (json.JSONDecodeError, OSError, ValueError):
                    continue
                if (
                    payload.get("kind") == kind
                    and str(payload.get("candidate_id", "")) == candidate_id
                    and "verdict" in payload
                    and "baseline_runs" in payload
                ):
                    matching.append(path)
            if not matching:
                l6_failures.append(f"L6: décision obligatoire absente {kind}/{candidate_id}")
                continue
            decision_path = _safe_evidence_path(runtime, _latest(matching))
            decision = _json(decision_path)
            decision_failures, input_paths = _validate_l6_decision(
                repo_root,
                runtime,
                decision_path,
                decision,
                snapshots,
                accepted,
            )
            l6_failures.extend(decision_failures)
            manifest.append(_manifest_entry(runtime, "L6", f"decision:{kind}", decision_path, decision))
            for input_path in input_paths:
                payload = _json(input_path)
                entry = _manifest_entry(runtime, "L6", f"snapshot:{kind}", input_path, payload)
                if entry not in manifest:
                    manifest.append(entry)
            l6_decisions.append(
                {
                    "kind": kind,
                    "candidate_id": candidate_id,
                    "verdict": decision.get("verdict"),
                    "evidence": _relative(runtime, decision_path),
                    "recomputed": not decision_failures,
                }
            )
        optional = l6_cfg.get("optional_decisions", [])
        if isinstance(optional, list):
            for raw_spec in optional:
                if not isinstance(raw_spec, dict):
                    continue
                kind = str(raw_spec.get("kind", ""))
                candidate_id = str(raw_spec.get("candidate_id", ""))
                present = False
                for path in l6_paths:
                    try:
                        payload = _json(path)
                    except (json.JSONDecodeError, OSError, ValueError):
                        continue
                    if (
                        payload.get("kind") == kind
                        and str(payload.get("candidate_id", "")) == candidate_id
                        and "verdict" in payload
                    ):
                        present = True
                        break
                if not present:
                    warnings.append(f"L6: candidat optionnel non mesuré {kind}/{candidate_id}")
    except (FileNotFoundError, KeyError, OSError, ValueError) as exc:
        l6_failures.append(f"L6: {exc}")
    failures.extend(l6_failures)
    gates["L6"] = {
        "status": "PASS" if not l6_failures else "BLOCKED",
        "decisions": l6_decisions,
    }

    try:
        l7_cfg = _mapping(evidence_cfg.get("l7"), "evidence.l7")
        l7_path = _safe_evidence_path(runtime, _latest(_glob(runtime, str(l7_cfg["glob"]))))
        l7_payload = _json(l7_path)
        l7_failures = _validate_l7(l7_payload, l7_cfg)
        failures.extend(l7_failures)
        gates["L7"] = {
            "status": "PASS" if not l7_failures else "BLOCKED",
            "evidence": _relative(runtime, l7_path),
        }
        manifest.append(_manifest_entry(runtime, "L7", "golden-suite", l7_path, l7_payload))
    except (FileNotFoundError, KeyError, json.JSONDecodeError, OSError, ValueError) as exc:
        failures.append(f"L7: {exc}")
        gates["L7"] = {"status": "BLOCKED", "reason": str(exc)}

    if software.get("qualification", {}).get("verdict") != "PASS":
        gates["L5"]["status"] = "BLOCKED"
    if software.get("optimization", {}).get("verdict") != "PASS":
        gates["L6"]["status"] = "BLOCKED"
    if software.get("golden_projects", {}).get("verdict") != "PASS":
        gates["L7"]["status"] = "BLOCKED"

    manifest.sort(key=lambda item: (str(item["gate"]), str(item["role"]), str(item["path"])))
    evidence_hash = _canonical_hash(manifest)
    verdict = READY if not failures and all(
        gates.get(gate, {}).get("status") == "PASS"
        for gate in ("L0", "L1", "L2", "L3", "L4", "L5", "L6", "L7")
    ) else BLOCKED
    return {
        "schema_version": REPORT_SCHEMA,
        "gate": "L8",
        "generated_at": datetime.now(UTC).isoformat(),
        "verdict": verdict,
        "runtime_root": str(runtime),
        "software_contracts": {
            "verdict": "PASS" if not any(
                component.get("verdict") == "FAIL" for component in software.values()
            ) else "FAIL",
            "components": software,
        },
        "gates": gates,
        "evidence_manifest": manifest,
        "evidence_set_sha256": evidence_hash,
        "human_approval": {
            "required": True,
            "status": "PENDING",
            "automatic": False,
        },
        "v1_approved": False,
        "automatic_config_mutation": False,
        "automatic_release_publication": False,
        "cloud_calls_allowed": False,
        "failures": failures,
        "warnings": warnings,
    }


def dry_run(repo_root: Path) -> dict[str, Any]:
    failures, warnings = validate_release_readiness_contracts(repo_root)
    if failures:
        raise ValueError("; ".join(failures))
    contract = root_contract(repo_root, "release_readiness.yaml")
    evidence = _mapping(contract.get("evidence"), "release_readiness.evidence")
    l6 = _mapping(evidence.get("l6"), "release_readiness.evidence.l6")
    return {
        "schema_version": REPORT_SCHEMA,
        "gate": "L8",
        "verdict": "READY_TO_COLLECT_EVIDENCE",
        "required_gates": list(_mapping(contract.get("policy"), "policy")["required_gates"]),
        "required_l6_decisions": list(l6["required_decisions"]),
        "automatic_human_approval": False,
        "automatic_config_mutation": False,
        "automatic_release_publication": False,
        "warnings": list(warnings),
    }


def write_readiness_report(repo_root: Path, runtime_root: Path) -> tuple[int, Path]:
    payload = collect_readiness(repo_root, runtime_root)
    contract = root_contract(repo_root, "release_readiness.yaml")
    approval = _mapping(contract.get("approval"), "release_readiness.approval")
    base = runtime_root.resolve() / str(approval["report_directory"])
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    run_root = base / run_id
    run_root.mkdir(parents=True, exist_ok=False)
    path = run_root / str(approval["readiness_report_name"])
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    return (0 if payload["verdict"] == READY else 2), path


def approve_release(
    repo_root: Path,
    runtime_root: Path,
    report_path: Path,
    *,
    approver: str,
    acknowledge: bool,
) -> Path:
    if not acknowledge:
        raise PermissionError("L8: acknowledgement humain explicite requis")
    identity = approver.strip()
    if not identity or len(identity) > 200 or any(char in identity for char in "\r\n\x00"):
        raise ValueError("L8: identité approbateur invalide")

    report = _safe_evidence_path(runtime_root, report_path)
    payload = _json(report)
    if payload.get("schema_version") != REPORT_SCHEMA or payload.get("gate") != "L8":
        raise ValueError("L8: rapport readiness invalide")
    if payload.get("verdict") != READY:
        raise PermissionError("L8: rapport non READY_FOR_HUMAN_REVIEW")
    human = _mapping(payload.get("human_approval"), "L8.human_approval")
    if human.get("required") is not True or human.get("status") != "PENDING":
        raise PermissionError("L8: rapport ne présente pas un gate humain en attente")
    if human.get("automatic") is not False or payload.get("v1_approved") is not False:
        raise PermissionError("L8: rapport contient un état d'approbation automatique interdit")

    current = collect_readiness(repo_root, runtime_root)
    if current.get("verdict") != READY:
        raise PermissionError("L8: les preuves courantes ne sont plus READY")
    if current.get("evidence_set_sha256") != payload.get("evidence_set_sha256"):
        raise PermissionError("L8: ensemble de preuves modifié depuis le rapport soumis")
    if current.get("software_contracts", {}).get("verdict") != "PASS":
        raise PermissionError("L8: contrats logiciels courants non PASS")

    contract = root_contract(repo_root, "release_readiness.yaml")
    approval_cfg = _mapping(contract.get("approval"), "release_readiness.approval")
    directory = runtime_root.resolve() / str(approval_cfg["approval_directory"])
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    path = directory / f"{approval_cfg['approval_prefix']}{stamp}.json"
    approval_payload = {
        "schema_version": REPORT_SCHEMA,
        "gate": "L8",
        "verdict": APPROVED,
        "approved_at": datetime.now(UTC).isoformat(),
        "approver": identity,
        "human_approved": True,
        "automatic": False,
        "scope": approval_cfg["approval_scope"],
        "readiness_report": _relative(runtime_root, report),
        "readiness_report_sha256": _sha256(report),
        "evidence_set_sha256": payload["evidence_set_sha256"],
        "runtime_config_mutated": False,
        "release_published": False,
        "project_complete_mutated": False,
    }
    with path.open("x", encoding="utf-8") as handle:
        handle.write(
            json.dumps(approval_payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        )
    return path
