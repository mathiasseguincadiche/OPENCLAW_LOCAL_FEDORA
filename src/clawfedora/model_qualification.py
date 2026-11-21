"""Compare the same public InfraOps tasks across three models, without model calls.

This report only aggregates human-reviewed measurements. It cannot certify
quality, execute a validation or automatically disable local inference.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any

MODELS = (
    "qwen3.5:9b-q4_K_M",
    "deepseek/deepseek-v4.1-flash-1017",
    "openai/gpt-6.2-sol",
)
SCORES = ("technical", "clarity", "proof", "safety")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
COMMIT = re.compile(r"[0-9a-f]{40}\Z")


class QualificationRefused(ValueError):
    """Metrics are missing, incomparable or unsafe to interpret."""


def _real_number(value: Any, label: str) -> float:
    if type(value) not in (float, int):
        raise QualificationRefused(f"{label}: nombre réel requis")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise QualificationRefused(f"{label}: valeur non finie ou négative")
    return result


def _validate_result(result: Any, model: str) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise QualificationRefused("observation: objet requis")
    case_id = result.get("case_id")
    if not isinstance(case_id, str) or not re.fullmatch(r"[a-z][a-z0-9-]{2,63}", case_id):
        raise QualificationRefused("case_id invalide")
    if type(result.get("accepted")) is not bool:
        raise QualificationRefused(f"{model}/{case_id}: acceptation humaine manquante")
    scores = result.get("scores")
    if not isinstance(scores, dict) or set(scores) != set(SCORES):
        raise QualificationRefused(f"{model}/{case_id}: quatre notes requises")
    if any(type(scores[key]) is not int or not 0 <= scores[key] <= 4 for key in SCORES):
        raise QualificationRefused(f"{model}/{case_id}: notes de 0 à 4 requises")
    elapsed = result.get("elapsed_ms")
    if type(elapsed) is not int or elapsed <= 0:
        raise QualificationRefused(f"{model}/{case_id}: durée mesurée requise")
    cost = _real_number(result.get("cost_usd"), f"{model}/{case_id}: coût")
    if model == MODELS[0] and cost != 0:
        raise QualificationRefused("Qwen local: coût API différent de zéro")
    return {
        "case_id": case_id,
        "accepted": result["accepted"],
        "scores": scores,
        "elapsed_ms": elapsed,
        "cost_usd": cost,
    }


def evaluate(payload: Any) -> dict[str, Any]:
    """Return aggregate indicators only; never silently select or remove a model."""
    if not isinstance(payload, dict) or payload.get("classification") != "synthetic_public":
        raise QualificationRefused("seuls les scénarios publics synthétiques sont comparables")
    revision, fingerprint = payload.get("commit"), payload.get("suite_sha256")
    if not isinstance(revision, str) or not COMMIT.fullmatch(revision):
        raise QualificationRefused("commit SHA Git exact requis")
    if not isinstance(fingerprint, str) or not SHA256.fullmatch(fingerprint):
        raise QualificationRefused("empreinte SHA-256 de suite requise")
    models = payload.get("models")
    if not isinstance(models, dict) or set(models) != set(MODELS):
        raise QualificationRefused("trois modèles exacts requis, aucun substitut")
    normalized: dict[str, dict[str, dict[str, Any]]] = {}
    for model in MODELS:
        observations = models[model]
        if not isinstance(observations, list) or len(observations) < 4:
            raise QualificationRefused(f"{model}: au moins quatre essais requis")
        observations_by_case: dict[str, dict[str, Any]] = {}
        for raw in observations:
            item = _validate_result(raw, model)
            if item["case_id"] in observations_by_case:
                raise QualificationRefused(f"{model}: cas répété")
            observations_by_case[item["case_id"]] = item
        normalized[model] = observations_by_case
    cases = set(normalized[MODELS[0]])
    if any(set(data) != cases for data in normalized.values()):
        raise QualificationRefused("mêmes cas et mêmes versions requis pour les trois modèles")

    summary: dict[str, dict[str, Any]] = {}
    for model, observations in normalized.items():
        rows = list(observations.values())
        summary[model] = {
            "total": len(rows),
            "accepted": sum(bool(row["accepted"]) for row in rows),
            "technical_at_least_3": sum(
                row["accepted"] and row["scores"]["technical"] >= 3
                and row["scores"]["proof"] >= 3 and row["scores"]["safety"] >= 3
                for row in rows
            ),
            "elapsed_ms_total": sum(row["elapsed_ms"] for row in rows),
            "cost_usd_total": round(sum(row["cost_usd"] for row in rows), 8),
        }

    local = normalized[MODELS[0]]
    # Each case compares local only with cloud responses meeting the same quality gate.
    local_competitive: list[str] = []
    for case_id in sorted(cases):
        local_row = local[case_id]
        cloud_rows = [normalized[model][case_id] for model in MODELS[1:]]
        cloud_accepted = [
            row for row in cloud_rows if row["accepted"] and row["scores"]["technical"] >= 3
            and row["scores"]["proof"] >= 3 and row["scores"]["safety"] >= 3
        ]
        if (
            cloud_accepted and local_row["accepted"]
            and min(local_row["scores"][key] for key in ("technical", "proof", "safety")) >= 3
            and local_row["elapsed_ms"] <= 1.5 * min(row["elapsed_ms"] for row in cloud_accepted)
        ):
            local_competitive.append(case_id)

    if len(local_competitive) >= len(cases) // 2 + 1:
        advice = "local_possibly_useful"
    elif not local_competitive and summary[MODELS[0]]["technical_at_least_3"] == 0:
        advice = "consider_disabling_local_after_human_review"
    else:
        advice = "inconclusive"
    return {
        "commit": revision,
        "suite_sha256": fingerprint,
        "cases": sorted(cases),
        "summary": summary,
        "local_competitive_cases": local_competitive,
        "advice": advice,
        "limitations": (
            "Notes et factures déclarées par un humain, non vérifiées par ce programme. "
            "Aucun modèle n'est désinstallé. Les données privées ne doivent pas être "
            "envoyées au cloud pour réaliser cette comparaison."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Comparer Qwen, DeepSeek et Sol, hors ligne")
    parser.add_argument("report", type=Path, help="JSON de mesures humaines hors dépôt")
    args = parser.parse_args(argv)
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        print(json.dumps(evaluate(report), ensure_ascii=False, indent=2, sort_keys=True))
    except (OSError, ValueError, TypeError) as exc:
        print(f"MODEL_QUALIFICATION=REFUSED reason={exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
