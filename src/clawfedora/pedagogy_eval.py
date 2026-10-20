"""Human-reviewed, multi-turn pedagogical evaluation; no model or API calls.

The scoring format is intentionally separate from the seven-agent technical suite.
A recorded conversation is evidence to review, not proof that its claims are true.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).resolve().parents[2]
CRITERIA = ("clarity", "depth", "interaction", "accuracy")
ROUTES = ("local", "cloud", "reference")


class PedagogyEvaluationError(ValueError):
    """Invalid scenario suite or unsubstantiated evaluation record."""


def load_suite(root: Path) -> dict[str, Any]:
    raw: object = yaml.safe_load(
        (root / "config/evals/pedagogy_conversations.yaml").read_text(encoding="utf-8")
    )
    if not isinstance(raw, dict):
        raise PedagogyEvaluationError("suite pédagogique invalide")
    suite = cast(dict[str, Any], raw)
    cases = suite.get("scenarios")
    if suite.get("data_classification") != "synthetic_public" or not isinstance(cases, list):
        raise PedagogyEvaluationError("scénarios publics requis")
    if len(cases) < 4:
        raise PedagogyEvaluationError("au moins quatre scénarios multi-tours requis")
    seen: set[str] = set()
    for item in cases:
        if not isinstance(item, dict):
            raise PedagogyEvaluationError("scénario invalide")
        key, turns = item.get("id"), item.get("turns")
        if not isinstance(key, str) or not key or key in seen:
            raise PedagogyEvaluationError("identifiant scénario absent ou dupliqué")
        if not isinstance(turns, list) or len(turns) < 3 or not all(
            isinstance(turn, str) and len(turn.strip()) >= 15 for turn in turns
        ):
            raise PedagogyEvaluationError("trois tours utilisateur détaillés requis")
        if not isinstance(item.get("expected"), list) or len(item["expected"]) < 2:
            raise PedagogyEvaluationError("attentes pédagogiques absentes")
        seen.add(key)
    return suite


def evaluate(suite: dict[str, Any], report: object) -> dict[str, Any]:
    if not isinstance(report, dict):
        raise PedagogyEvaluationError("rapport JSON invalide")
    payload = cast(dict[str, Any], report)
    route = payload.get("route")
    if route not in ROUTES:
        raise PedagogyEvaluationError("route local, cloud ou reference requise")
    cases = cast(list[dict[str, Any]], suite["scenarios"])
    by_id = {str(case["id"]): case for case in cases}
    results = payload.get("results")
    if not isinstance(results, list) or len(results) != len(cases):
        raise PedagogyEvaluationError("un dialogue enregistré par scénario est requis")
    seen: set[str] = set()
    sums = {criterion: 0 for criterion in CRITERIA}
    usage_cost = 0.0
    measured_usage = 0
    for item in results:
        if not isinstance(item, dict):
            raise PedagogyEvaluationError("résultat invalide")
        key = item.get("scenario")
        if not isinstance(key, str) or key not in by_id or key in seen:
            raise PedagogyEvaluationError("scénario absent, inconnu ou dupliqué")
        seen.add(key)
        if not isinstance(item.get("reviewer"), str) or not item["reviewer"].strip():
            raise PedagogyEvaluationError("évaluateur humain requis")
        if not isinstance(item.get("notes"), str) or len(item["notes"].strip()) < 20:
            raise PedagogyEvaluationError("justification humaine détaillée requise")
        evidence = item.get("evidence")
        if not isinstance(evidence, list) or not evidence or not all(
            isinstance(ref, str) and ref.strip() for ref in evidence
        ):
            raise PedagogyEvaluationError("références vers les réponses requises")
        dialogue = item.get("dialogue")
        expected_turns = by_id[key]["turns"]
        if not isinstance(dialogue, list) or len(dialogue) != len(expected_turns):
            raise PedagogyEvaluationError("dialogue multi-tours incomplet")
        for actual, expected in zip(dialogue, expected_turns, strict=True):
            if not isinstance(actual, dict) or actual.get("user") != expected:
                raise PedagogyEvaluationError("questions modifiées ou dans le mauvais ordre")
            answer = actual.get("assistant")
            if not isinstance(answer, str) or len(answer.strip()) < 20:
                raise PedagogyEvaluationError("réponse réelle manquante")
        scores = item.get("scores")
        if not isinstance(scores, dict) or set(scores) != set(CRITERIA):
            raise PedagogyEvaluationError("quatre critères pédagogiques requis")
        for criterion in CRITERIA:
            score = scores[criterion]
            if type(score) is not int or not 0 <= score <= 5:
                raise PedagogyEvaluationError("notes entières entre 0 et 5 uniquement")
            sums[criterion] += score
        usage = item.get("usage")
        if usage is not None:
            if not isinstance(usage, dict) or set(usage) != {
                "input_tokens", "output_tokens", "cost_usd"
            } or any(
                type(usage[k]) is not int or usage[k] < 0
                for k in ("input_tokens", "output_tokens")
            ) or (
                type(usage["cost_usd"]) not in (int, float)
                or not 0 <= usage["cost_usd"] < 1000000
            ):
                raise PedagogyEvaluationError("usage manuel invalide")
            measured_usage += 1
            usage_cost += float(usage["cost_usd"])
    means = {name: round(total / len(cases), 2) for name, total in sums.items()}
    return {
        "route": route,
        "scenarios": len(cases),
        "criteria_means_out_of_5": means,
        "global_out_of_20": round(sum(sums.values()) / len(cases), 2),
        "all_four_at_five": all(score == 5 for score in means.values()),
        "usage_declared_scenarios": measured_usage,
        "declared_cost_usd": round(usage_cost, 6) if measured_usage else None,
        "assessment": "HUMAN_DIALOGUE_REVIEW_NOT_RUNTIME_PROOF",
        "warning": (
            "Notes et coût déclarés par l'évaluateur: ni exécution, ni facturation "
            "OpenRouter, ni supériorité face à Gemini démontrées automatiquement."
        ),
    }


def compare(suite: dict[str, Any], first: object, second: object) -> dict[str, Any]:
    left, right = evaluate(suite, first), evaluate(suite, second)
    if left["route"] == right["route"]:
        raise PedagogyEvaluationError("routes distinctes requises pour la comparaison")
    a = cast(dict[str, float], left["criteria_means_out_of_5"])
    b = cast(dict[str, float], right["criteria_means_out_of_5"])
    return {
        "first_route": left["route"],
        "second_route": right["route"],
        "delta_second_minus_first": {
            key: round(b[key] - a[key], 2) for key in CRITERIA
        },
        "global_delta_out_of_20": round(
            float(right["global_out_of_20"]) - float(left["global_out_of_20"]), 2
        ),
        "assessment": "HUMAN_COMPARISON_NOT_MODEL_BENCHMARK",
        "warning": "Comparer des appréciations humaines; aucune supériorité garantie.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Grille pédagogique multi-tours /20, hors ligne")
    parser.add_argument("--root", type=Path, default=ROOT)
    choices = parser.add_mutually_exclusive_group(required=True)
    choices.add_argument("--plan", action="store_true")
    choices.add_argument("--report", type=Path)
    choices.add_argument("--compare", nargs=2, type=Path, metavar=("A_JSON", "B_JSON"))
    args = parser.parse_args(argv)
    try:
        suite = load_suite(args.root)
        if args.plan:
            output: object = {
                "criteria": list(CRITERIA),
                "scale": "0-5 each, 20 total",
                "scenarios": suite["scenarios"],
                "status": "PLAN_ONLY_NO_MODEL_CALLS",
            }
        elif args.report:
            output = evaluate(suite, json.loads(args.report.read_text(encoding="utf-8")))
        else:
            a_path, b_path = cast(list[Path], args.compare)
            output = compare(
                suite,
                json.loads(a_path.read_text(encoding="utf-8")),
                json.loads(b_path.read_text(encoding="utf-8")),
            )
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, yaml.YAMLError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
