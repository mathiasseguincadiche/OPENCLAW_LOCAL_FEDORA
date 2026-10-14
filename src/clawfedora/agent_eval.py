"""Offline, human-reviewed evaluation framework for seven specialist roles.

No model is called here. A high score is an evaluation record, never proof
that Terraform, Ansible, a deployment, or OpenRouter was actually executed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, cast

import yaml

CRITERIA = ("technical", "clarity", "proof", "safety")
ROUTES = ("local", "cloud")
ROOT = Path(__file__).resolve().parents[2]


class EvaluationError(ValueError):
    pass


def load_suite(root: Path) -> dict[str, Any]:
    path = root / "config/evals/devops_synthetic.yaml"
    payload: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise EvaluationError("La suite doit être un objet YAML")
    suite = cast(dict[str, Any], payload)
    roles: dict[str, Any] = yaml.safe_load(
        (root / "config/core/agents.yaml").read_text(encoding="utf-8")
    )["agents"]
    raw_cases = suite.get("scenarios")
    if not isinstance(raw_cases, list) or len(raw_cases) != len(roles):
        raise EvaluationError("Une évaluation est requise pour chacun des sept rôles")
    seen: set[str] = set()
    role_seen: set[str] = set()
    for raw in raw_cases:
        if not isinstance(raw, dict):
            raise EvaluationError("Scénario invalide")
        case = cast(dict[str, Any], raw)
        key, role = case.get("id"), case.get("role")
        if not isinstance(key, str) or not key or key in seen:
            raise EvaluationError("Identifiant de scénario absent ou répété")
        if not isinstance(role, str) or role not in roles or role in role_seen:
            raise EvaluationError("Rôle manquant, inconnu ou répété")
        if (
            not isinstance(case.get("prompt"), str)
            or len(case["prompt"].strip()) < 30
            or not isinstance(case.get("expected"), list)
            or len(case["expected"]) < 2
            or not all(isinstance(item, str) and item.strip() for item in case["expected"])
        ):
            raise EvaluationError(f"Contrat incomplet: {key}")
        seen.add(key)
        role_seen.add(role)
    if suite.get("data_classification") != "synthetic_public":
        raise EvaluationError("La suite doit contenir uniquement des données synthétiques")
    return suite


def evaluate_report(suite: dict[str, Any], report: object) -> dict[str, Any]:
    """Validate and aggregate *human* scores without treating them as CI proofs."""
    if not isinstance(report, dict):
        raise EvaluationError("Rapport JSON invalide")
    payload = cast(dict[str, Any], report)
    route = payload.get("route")
    if route not in ROUTES:
        raise EvaluationError("route doit être local ou cloud")
    cases = cast(list[dict[str, Any]], suite["scenarios"])
    expected = {str(case["id"]) for case in cases}
    results = payload.get("results")
    if not isinstance(results, list) or len(results) != len(expected):
        raise EvaluationError("Un résultat humain est requis par scénario")
    seen: set[str] = set()
    totals = {name: 0 for name in CRITERIA}
    for item in results:
        if not isinstance(item, dict):
            raise EvaluationError("Résultat de scénario invalide")
        result = cast(dict[str, Any], item)
        key = result.get("scenario")
        if not isinstance(key, str) or key not in expected or key in seen:
            raise EvaluationError("Résultat absent, inconnu ou répété")
        seen.add(key)
        if not isinstance(result.get("reviewer"), str) or not result["reviewer"].strip():
            raise EvaluationError(f"{key}: évaluateur humain requis")
        if not isinstance(result.get("notes"), str) or len(result["notes"].strip()) < 15:
            raise EvaluationError(f"{key}: explication détaillée requise")
        if not isinstance(result.get("evidence"), list) or not result["evidence"]:
            raise EvaluationError(f"{key}: références vers les éléments examinés requises")
        if not all(isinstance(x, str) and x.strip() for x in result["evidence"]):
            raise EvaluationError(f"{key}: références invalides")
        scores = result.get("scores")
        if not isinstance(scores, dict) or set(scores) != set(CRITERIA):
            raise EvaluationError(f"{key}: grille de notation incomplète")
        for name in CRITERIA:
            number = scores[name]
            if type(number) is not int or not 0 <= number <= 4:
                raise EvaluationError(f"{key}: score {name} doit être entier entre 0 et 4")
            totals[name] += number
    count = len(expected)
    return {
        "route": route,
        "scenarios": count,
        "criterion_means": {name: round(total / count, 2) for name, total in totals.items()},
        "mean_out_of_4": round(sum(totals.values()) / (count * len(CRITERIA)), 2),
        "assessment": "HUMAN_REVIEWED_UNVERIFIED_BY_RUNTIME",
        "warning": (
            "Les notes humaines ne certifient ni l'exécution des scripts, "
            "ni les dépenses OpenRouter, ni la supériorité d'un modèle."
        ),
    }



def compare_reports(
    suite: dict[str, Any], local_report: object, cloud_report: object,
) -> dict[str, Any]:
    """Compare *human* scoring for identical scenarios; never claim a model winner."""
    local = evaluate_report(suite, local_report)
    cloud = evaluate_report(suite, cloud_report)
    if local["route"] != "local" or cloud["route"] != "cloud":
        raise EvaluationError("comparaison : fournir un rapport local puis un rapport cloud")
    assert isinstance(local_report, dict) and isinstance(cloud_report, dict)
    left = cast(dict[str, Any], local_report)
    right = cast(dict[str, Any], cloud_report)
    local_cases = {item["scenario"]: item for item in left["results"]}
    cloud_cases = {item["scenario"]: item for item in right["results"]}
    scenario_deltas = {}
    for scenario in sorted(local_cases):
        a = local_cases[scenario]["scores"]
        b = cloud_cases[scenario]["scores"]
        scenario_deltas[scenario] = {
            name: b[name] - a[name] for name in CRITERIA
        }
    return {
        "scenarios": local["scenarios"],
        "local_mean_out_of_4": local["mean_out_of_4"],
        "cloud_mean_out_of_4": cloud["mean_out_of_4"],
        "delta_cloud_minus_local": round(
            cloud["mean_out_of_4"] - local["mean_out_of_4"], 2
        ),
        "per_scenario_deltas": scenario_deltas,
        "assessment": "HUMAN_SCORE_COMPARISON_NOT_RUNTIME_QUALIFICATION",
        "warning": (
            "Comparaison de jugements humains uniquement ; ni classement objectif, "
            "ni supériorité démontrée, ni mesure de coût, latence ou GPU."
        ),
    }

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Qualifier les sept agents sans API ni réseau")
    parser.add_argument("--root", type=Path, default=ROOT)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--plan", action="store_true", help="afficher les sept cas synthétiques")
    group.add_argument("--report", type=Path, help="agréger des notes humaines complètes")
    group.add_argument(
        "--compare", nargs=2, type=Path, metavar=("LOCAL_JSON", "CLOUD_JSON"),
        help="comparer hors ligne deux rapports humains (mêmes sept scénarios)",
    )
    args = parser.parse_args(argv)
    try:
        suite = load_suite(args.root)
        if args.plan:
            data: object = {
                "suite": suite["name"],
                "routes_to_compare": list(ROUTES),
                "consent_required_for_cloud": True,
                "scenarios": suite["scenarios"],
                "rubric": suite["rubric"],
                "status": "PLAN_ONLY_NO_MODEL_CALLS",
            }
        elif args.report:
            path = cast(Path, args.report)
            data = evaluate_report(
                suite, json.loads(path.read_text(encoding="utf-8"))
            )
        else:
            local_path, cloud_path = cast(list[Path], args.compare)
            data = compare_reports(
                suite,
                json.loads(local_path.read_text(encoding="utf-8")),
                json.loads(cloud_path.read_text(encoding="utf-8")),
            )
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, yaml.YAMLError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
