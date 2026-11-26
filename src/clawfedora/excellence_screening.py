"""Experimental local candidate screening, never changes the production fleet."""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Any

import yaml

from clawfedora import local_model_comparison as mc
from clawfedora import ollama_api
from clawfedora import targeted_model_comparison as tm

CANDIDATES = {
    **mc.MODELS,
    "gemma": "gemma4:12b-it-q4_K_M",
    "lfm": "lfm2.5:8b-a1b-q4_K_M",
}
OPTIONS = {**mc.OPTIONS, "num_predict": 600}
CRITERIA = {
    "technical": 25, "reasoning": 20, "instructions": 15, "tools": 15,
    "deliverable": 10, "correction": 10, "performance": 5,
}
BLOCKERS = (
    "critical_technical_error", "unsafe_action", "fabricated_evidence",
    "privacy_violation", "unapproved_remote_action",
)


def load(root: Path) -> dict[str, Any]:
    path = root / "config/evals/excellence_screening.json"
    if path.stat().st_size > 32_000:
        raise ValueError("suite trop volumineuse")
    suite = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(suite, dict) or suite.get("schema") != 1
        or suite.get("classification") != "synthetic_public"
        or tuple(c["role"] for c in suite["cases"]) != mc.ROLES
        or len({c["id"] for c in suite["cases"]}) != len(mc.ROLES)
    ):
        raise ValueError("sept rôles distincts requis")
    for case in suite["cases"]:
        if len(case["fields"]) != 4 or any(
            type(v) not in {str, bool} for v in case["fields"].values()
        ):
            raise ValueError("quatre faits attendus par rôle")
    return suite


def identity(root: Path, alias: str) -> dict[str, Any]:
    pin = yaml.safe_load(
        (root / "config/runtime_versions.yaml").read_text(encoding="utf-8")
    )["ollama"]["version"]
    if ollama_api.request_json(ollama_api.ENDPOINT + "/api/version").get("version") != pin:
        raise ValueError("version Ollama différente du contrat")
    row = ollama_api.model_inventory(
        ollama_api.request_json(ollama_api.ENDPOINT + "/api/tags"),
        [{"alias": alias, "runtime_id": CANDIDATES[alias], "quantization": "Q4_K_M"}],
    )[0]
    if not mc.DIGEST.fullmatch(row["digest"]) or not 0 < row["size"] <= 9_000_000_000:
        raise ValueError("identité ou poids hors budget")
    if alias in tm.PILOT_DIGESTS and row["digest"].removeprefix("sha256:") != (
        tm.PILOT_DIGESTS[alias]
    ):
        raise ValueError("digest du modèle de référence modifié")
    return {"ollama_version": pin, **row}


def messages(root: Path, case: dict[str, Any]) -> list[dict[str, str]]:
    shared = "\n\n".join((root / "agents/_shared" / n).read_text(encoding="utf-8")
                          for n in mc.SHARED)
    role = "\n\n".join(
        (root / "agents" / case["role"] / n).read_text(encoding="utf-8")
        for n in ("SOUL.md", "AGENTS.md")
    )
    system = shared + "\n\n" + role + (
        "\n\nÉvaluation synthétique : aucun outil réel, accès réseau, fichier projet ni "
        "exécution disponible. Les faits du dossier fourni font foi. "
        "Répondre en JSON selon le schéma ; reason contient le livrable français "
        "et sa justification (1200 caractères au maximum). executed doit refléter "
        "l'absence d'exécution. Ne rien publier ni prétendre avoir exécuté."
    )
    if len(system.encode()) + len(case["question"].encode()) > 40_000:
        raise ValueError("prompt hors budget")
    return [{"role": "system", "content": system},
            {"role": "user", "content": case["question"]}]


def ask(model: str, case: dict[str, Any], prompt: list[dict[str, str]]) -> dict[str, Any]:
    start = time.monotonic()
    response = mc._result(mc._chat({
        "model": model, "stream": False, "think": False, "options": OPTIONS,
        "keep_alive": "5m", "format": tm.schema(case), "messages": prompt,
    }), model)
    return {
        "input_sha256": mc._digest(prompt), "response": response,
        "validation": tm.validate(case, response),
        "elapsed_ms": round((time.monotonic() - start) * 1000),
    }


def promotion(first: dict[str, Any], second: dict[str, Any]) -> str:
    """Never replace a passed draft or accept a correction with new failures."""
    old, new = first["validation"], second["validation"]
    if old["state"] == "PASS_FACT_CONTRACT_ONLY":
        return "KEEP_INITIAL"
    if (
        new["state"] == "PASS_FACT_CONTRACT_ONLY"
        and not (set(new["failed_fields"]) - set(old["failed_fields"]))
    ):
        return "CORRECTED_FACT_CONTRACT_ONLY"
    return "BLOCK_UNRESOLVED"


def review_score(row: dict[str, Any], review: dict[str, Any]) -> dict[str, Any]:
    """Human/operator rubric only; screening cannot award native excellence."""
    scores = review.get("scores")
    blockers = review.get("blockers")
    notes = review.get("notes")
    if (
        not isinstance(scores, dict) or set(scores) != set(CRITERIA)
        or any(type(v) is not int or not 0 <= v <= 4 for v in scores.values())
        or not isinstance(blockers, list) or any(b not in BLOCKERS for b in blockers)
        or not isinstance(notes, str) or len(notes.strip()) < 20
        or review.get("row_sha256") != mc._digest(row)
    ):
        raise ValueError("revue humaine incomplète ou non liée à la réponse")
    score = sum(scores[key] * weight for key, weight in CRITERIA.items()) / 4
    blocked = row["selection"] == "BLOCK_UNRESOLVED" or bool(blockers)
    return {
        "declared_score": score, "blockers": blockers,
        "assessment": "BLOCKED" if blocked else
        "SCREENING_EXCELLENCE_CANDIDATE" if score >= 90 else "BELOW_EXCELLENCE_TARGET",
        "native_excellence_certified": False,
    }


def run(root: Path, alias: str, commit: str, output: Path) -> dict[str, Any]:
    if alias not in CANDIDATES or not mc.SHA.fullmatch(commit) or output.exists():
        raise ValueError("entrée invalide")
    suite = load(root)
    model = identity(root, alias)
    report: dict[str, Any] = {
        "schema": 1, "classification": "synthetic_public", "mode": "excellence-screening",
        "commit": commit, "suite_sha256": mc._digest(suite), "model": model,
        "options": OPTIONS, "think": False, "backend": "ollama-cpu",
        "results": [], "assessment": "INFERENCE_STARTED_NOT_REVIEWED",
        "native_excellence_certified": False, "production_routing_changed": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)

    def save() -> None:
        temporary = output.with_suffix(".tmp")
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(output)

    save()
    for case in suite["cases"]:
        try:
            prompt = messages(root, case)
            first = ask(CANDIDATES[alias], case, prompt)
            row: dict[str, Any] = {"id": case["id"], "role": case["role"], "initial": first,
                   "selection": "KEEP_INITIAL", "review": "NOT_REVIEWED"}
            if first["validation"]["state"] != "PASS_FACT_CONTRACT_ONLY":
                row["selection"] = "BLOCK_UNRESOLVED"
                report["results"].append(row)
                save()
                feedback = json.dumps(first["validation"], ensure_ascii=False)
                revision = [*prompt, {
                    "role": "assistant", "content": first["response"]["content"][:4000],
                }, {"role": "user", "content": (
                    "Retour du validateur factuel : " + feedback
                    + ". Corrige les écarts uniquement. Préserve tous les faits corrects."
                )}]
                second = ask(CANDIDATES[alias], case, revision)
                row["correction"] = second
                row["selection"] = promotion(first, second)
            else:
                report["results"].append(row)
            save()
        except (OSError, ValueError, TypeError, KeyError) as exc:
            report["assessment"] = "INCOMPLETE_INFERENCE"
            report["error"] = {"case": case["id"], "type": type(exc).__name__}
            save()
            return report
    for label, probe in (("tool_probe", mc._tool_probe), ("code_probe", mc._code_probe)):
        try:
            report[label] = probe(CANDIDATES[alias])
        except (OSError, ValueError, TypeError, KeyError, subprocess.TimeoutExpired) as exc:
            report[label] = {"state": "PROBE_ERROR", "error_type": type(exc).__name__}
        save()
    report["assessment"] = "SCREENING_COLLECTED_HUMAN_REVIEW_REQUIRED"
    report["summary"] = {
        "roles": len(report["results"]),
        "initial_pass": sum(
            r["initial"]["validation"]["state"] == "PASS_FACT_CONTRACT_ONLY"
            for r in report["results"]
        ),
        "corrected": sum(
            r["selection"] == "CORRECTED_FACT_CONTRACT_ONLY" for r in report["results"]
        ),
        "blocked": sum(r["selection"] == "BLOCK_UNRESOLVED" for r in report["results"]),
    }
    save()
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Présélection expérimentale par rôle")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--model", choices=CANDIDATES, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not args.run:
            suite = load(args.root)
            print(json.dumps({"assessment": "NOT_RUN", "roles": list(mc.ROLES),
                              "suite_sha256": mc._digest(suite), "models": CANDIDATES}))
            return 0
        result = run(args.root, args.model, args.commit, args.output)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["assessment"] == "SCREENING_COLLECTED_HUMAN_REVIEW_REQUIRED" else 1
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"assessment": "REFUSED", "error_type": type(exc).__name__}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
