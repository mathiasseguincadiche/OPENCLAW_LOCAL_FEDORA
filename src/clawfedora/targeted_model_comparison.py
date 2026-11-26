"""Paired factual probes with documented reference notes and bounded correction.

Only JSON fields are checked; explanatory prose still requires review.
Never executes model-proposed commands or consults private data.
"""
from __future__ import annotations

import argparse
import json
import shlex
import time
from pathlib import Path
from typing import Any

from clawfedora import local_model_comparison as mc

CASE_IDS = ("libvirt", "docker", "borg", "postgresql")
STAGES = ("closed_book", "sources", "correction")
OPTIONS = {**mc.OPTIONS, "num_predict": 600}
PILOT_DIGESTS = {
    "qwen": "56671c2ab9385f9cfcb404638e32cd62d88e3501d44822208363c010179a3c90",
    "ornith": "e5df7dcdd8a263994df62d610317e07be0d6af23f96fcbd8543273058fce575e",
}


def load(root: Path) -> dict[str, Any]:
    path = root / "config/evals/targeted_sources.json"
    if path.stat().st_size > 24_000:
        raise ValueError("suite ciblée trop volumineuse")
    suite = json.loads(path.read_text(encoding="utf-8"))
    if (
        suite["schema"] != 1 or suite["classification"] != "synthetic_public"
        or tuple(case["id"] for case in suite["cases"]) != CASE_IDS
    ):
        raise ValueError("suite ciblée inconnue")
    for case in suite["cases"]:
        if case["role"] not in mc.ROLES or len(case["fields"]) != 4:
            raise ValueError("contrat de cas invalide")
        if any(type(value) not in {str, bool} for value in case["fields"].values()):
            raise ValueError("type de référence invalide")
        if not case["sources"] or any(
            not source["url"].startswith("https://") or not source["note"]
            for source in case["sources"]
        ):
            raise ValueError("sources invalides")
    return suite


def schema(case: dict[str, Any]) -> dict[str, Any]:
    fields = {
        key: {"type": "boolean" if type(value) is bool else "string"}
        for key, value in case["fields"].items()
    }
    fields["reason"] = {"type": "string"}
    fields["executed"] = {"type": "boolean"}
    return {"type": "object", "properties": fields,
            "required": list(fields), "additionalProperties": False}


def _matches(key: str, actual: object, expected: object) -> bool:
    if type(expected) is bool:
        return type(actual) is bool and actual == expected
    if not isinstance(actual, str) or not isinstance(expected, str):
        return False
    if key.endswith("_command"):
        try:
            return shlex.split(actual) == shlex.split(expected)
        except ValueError:
            return False
    if key == "custom_format_flag":
        return actual.strip() == expected
    return actual.strip().casefold() == expected.casefold()


def validate(case: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Check a small factual contract, not arbitrary semantics or live services."""
    keys = set(schema(case)["required"])
    try:
        value = json.loads(result["content"])
    except (ValueError, TypeError, KeyError):
        value = None
    valid = (
        isinstance(value, dict) and set(value) == keys
        and isinstance(value["reason"], str) and 0 < len(value["reason"].strip()) <= 1200
        and type(value["executed"]) is bool
        and all(type(value[key]) is type(expected) for key, expected in case["fields"].items())
    )
    if not valid or not isinstance(value, dict):
        return {"state": "FAIL_SCHEMA", "correct": 0, "total": 4,
                "failed_fields": sorted(keys), "execution_claim": "UNKNOWN"}
    failed = [key for key, expected in case["fields"].items()
              if not _matches(key, value[key], expected)]
    correct = 4 - len(failed)
    execution_claim = value["executed"]
    if execution_claim:
        failed.append("executed")
    if result.get("done_reason") != "stop":
        failed.append("completion")
    state = "PASS_FACT_CONTRACT_ONLY" if not failed else "FAIL_FACT_CONTRACT"
    return {"state": state, "correct": correct, "total": 4,
            "failed_fields": failed, "execution_claim": execution_claim}


def _messages(
    root: Path, case: dict[str, Any], stage: str, previous: dict[str, Any] | None,
) -> list[dict[str, str]]:
    role = case["role"]
    shared = "\n\n".join((root / "agents/_shared" / name).read_text(encoding="utf-8")
                          for name in mc.SHARED)
    role_prompt = "\n\n".join((root / "agents" / role / name).read_text(encoding="utf-8")
                                for name in ("SOUL.md", "AGENTS.md"))
    system = shared + "\n\n" + role_prompt + (
        "\n\nQualification ciblée. Aucun accès aux outils, au réseau ou aux machines. "
        "N'exécute rien. Réponds en JSON selon le schéma, valeurs courtes et exactes, "
        "reason : justification française en deux phrases au maximum. "
        "executed doit refléter l'absence d'exécution. "
        "En cas d'incertitude sur un texte, indique inconnu."
    )
    prompt = case["question"]
    if stage != "closed_book":
        prompt += "\n\nNotes de référence relues (documentation publique, pas de test réel) :\n"
        prompt += "\n".join(f'{item["url"]} : {item["note"]}' for item in case["sources"])
    if stage == "correction":
        if previous is None:
            raise ValueError("correction sans résultat précédent")
        prompt += (
            "\n\nRéponse précédente :\n" + previous["response"]["content"][:4000]
            + "\nRetour du validateur de contrat : "
            + json.dumps(previous["validation"], ensure_ascii=False)
            + "\nCorrige seulement les écarts, conserve les éléments justes. "
            "Si aucun écart, confirme la réponse sans inventer de preuve."
        )
    if len(system.encode()) + len(prompt.encode()) > 40_000:
        raise ValueError("entrée hors budget")
    return [{"role": "system", "content": system}, {"role": "user", "content": prompt}]


def run(root: Path, model: str, commit: str, output: Path) -> dict[str, Any]:
    if model not in mc.MODELS or not mc.SHA.fullmatch(commit) or output.exists():
        raise ValueError("modèle, commit ou sortie invalide")
    suite = load(root)
    identity = mc._identity(root, model)
    if identity["digest"].removeprefix("sha256:") != PILOT_DIGESTS[model]:
        raise ValueError("digest différent du pilote, comparaison suspendue")
    report: dict[str, Any] = {
        "schema": 1, "mode": "targeted", "classification": "synthetic_public",
        "commit": commit, "suite_sha256": mc._digest(suite), "model": identity,
        "options": OPTIONS, "think": False, "backend": "ollama-cpu",
        "results": [], "assessment": "INFERENCE_STARTED_NOT_REVIEWED",
        "native_agent_qualification": False, "gpu_qualification": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)

    def save() -> None:
        temporary = output.with_suffix(".tmp")
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(output)

    save()
    for case in suite["cases"]:
        previous = None
        for stage in STAGES:
            start = time.monotonic()
            try:
                messages = _messages(root, case, stage, previous)
                response = mc._result(mc._chat({
                    "model": mc.MODELS[model], "stream": False, "think": False,
                    "keep_alive": "5m", "options": OPTIONS, "format": schema(case),
                    "messages": messages,
                }), mc.MODELS[model])
                row = {"case": case["id"], "role": case["role"], "stage": stage,
                       "input_sha256": mc._digest(messages), "response": response,
                       "validation": validate(case, response),
                       "elapsed_ms": round((time.monotonic() - start) * 1000)}
            except (OSError, ValueError, TypeError, KeyError) as exc:
                report["results"].append({"case": case["id"], "stage": stage,
                                          "error_type": type(exc).__name__})
                report["assessment"] = "INCOMPLETE_INFERENCE"
                save()
                return report
            report["results"].append(row)
            save()
            previous = row
    report["assessment"] = "RESPONSES_COLLECTED_REVIEW_REQUIRED"
    report["stage_summary"] = {
        stage: {
            "cases": len(CASE_IDS),
            "contract_pass": sum(
                row["validation"]["state"] == "PASS_FACT_CONTRACT_ONLY"
                for row in report["results"] if row["stage"] == stage
            ),
            "correct_fields": sum(
                row["validation"]["correct"] for row in report["results"] if row["stage"] == stage
            ),
            "total_fields": 4 * len(CASE_IDS),
        }
        for stage in STAGES
    }
    save()
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Comparaison ciblée, sans exécution de commandes")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--model", choices=mc.MODELS, required=True)
    parser.add_argument("--mode", choices=("targeted",), default="targeted")
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not args.run:
            suite = load(args.root)
            print(json.dumps({"assessment": "NOT_RUN", "cases": list(CASE_IDS),
                              "stages": list(STAGES), "suite_sha256": mc._digest(suite)}))
            return 0
        report = run(args.root, args.model, args.commit, args.output)
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report["assessment"] == "RESPONSES_COLLECTED_REVIEW_REQUIRED" else 1
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"assessment": "REFUSED_OR_INCOMPLETE", "error_type": type(exc).__name__}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
