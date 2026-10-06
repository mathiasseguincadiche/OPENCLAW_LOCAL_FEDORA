"""Sequential response comparison; human judgement, no downloads or promotion."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from clawfedora.core_config import load_yaml, resolve_runtime_root, root_contract
from clawfedora.gpu_telemetry import PeakSampler, b580_slot, xe_vram_mib
from clawfedora.hardware_gate import collect_hardware_gate
from clawfedora.project_common import assert_no_symlinks, now, write_json
from clawfedora.project_worker import worker_lock
from clawfedora.qualification import _request_json

SYSTEM_PROMPT = (
    "Mentor infrastructure/OPS. Explique en français simple; une action utile, "
    "pas tout l’exercice. Aucun outil disponible: ne simule aucun test."
)
VRAM_SCOPE = (
    "VRAM totale des clients xe observables; sondes périodiques, "
    "pic réel potentiellement manqué; allocation GPU ≠ offload complet."
)


def messages(case: dict[str, Any]) -> list[dict[str, str]]:
    history = case.get("history", [])
    if (
        not isinstance(history, list)
        or len(history) > 10
        or any(
            not isinstance(item, dict)
            or item.get("role") not in {"user", "assistant"}
            or not isinstance(item.get("content"), str)
            for item in history
        )
    ):
        raise ValueError("historique de comparaison texte requis")
    result = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": case["prompt"]},
    ]
    if len(json.dumps(result, ensure_ascii=False).encode()) > 6000:
        raise ValueError("contexte de comparaison limité à 6000 octets")
    return result


def comparison_plan(repo: Path, tokens: int = 1024, repeats: int = 1) -> dict[str, Any]:
    if tokens not in {1024, 1536, 2048} or not 1 <= repeats <= 3:
        raise ValueError("sortie 1024/1536/2048 et 1 à 3 répétitions requises")
    catalog = root_contract(repo, "model_catalog.yaml")
    models = catalog["models"]
    suite = load_yaml(repo / "benchmarks/suites/mentor_ops_fr.yaml")
    for case in suite["cases"]:
        messages(case)
    return {
        "created_at": now(),
        "status": "PLANNED",
        "runtime_tested": False,
        "automatic_promotion": False,
        "context": 8192,
        "max_output_tokens": tokens,
        "repeats": repeats,
        "temperature": 0.2,
        "top_p": 0.8,
        "top_k": 20,
        "presence_penalty": 0.0,
        "think": False,
        "keep_alive": "15m",
        "seed_base": 42,
        "models": [
            models["qwen-max"]["runtime_id"],
            models["gemma-deep"]["runtime_id"],
            catalog["challengers"]["devstral-devops"]["granite-devops"]["runtime_id"],
        ],
        "cases": suite["cases"],
        "results": [],
        "scope": "Réponses seules, sans outils OpenClaw; ni test de charge 8K rempli, "
        "ni qualification native. Notes humaines requises, jamais déduites des mots-clés.",
    }


def run_comparison(repo: Path, runtime: Path, output: Path, plan: dict[str, Any]) -> dict[str, Any]:
    assert_no_symlinks(output, label="rapport de comparaison")
    if output.exists():
        raise ValueError("choisir un nouveau rapport, sans écraser une mesure existante")
    api = "http://127.0.0.1:11434/api"
    with worker_lock(runtime):
        hardware = {gate: collect_hardware_gate(repo, gate).payload() for gate in ("l2", "l3")}
        if any(value["verdict"] != "PASS" for value in hardware.values()):
            raise ValueError("Fedora/B580 non qualifiés par les précontrôles L2/L3")
        version = _request_json(f"{api}/version")["version"]
        if version != root_contract(repo, "runtime_versions.yaml")["ollama"]["version"]:
            raise ValueError("version Ollama différente du contrat")
        inventory = _request_json(f"{api}/tags")["models"]
        identities = {item["name"]: item.get("digest") for item in inventory}
        if any(not identities.get(model) for model in plan["models"]):
            raise ValueError("installer explicitement les trois candidats avant la comparaison")
        if _request_json(f"{api}/ps").get("models"):
            raise ValueError("libérer les modèles résidents avant la comparaison")
        for model in plan["models"]:
            details = _request_json(f"{api}/show", payload={"model": model}).get("details", {})
            if details.get("quantization_level") != "Q4_K_M":
                raise ValueError(f"quantification Q4_K_M non confirmée: {model}")
        report = {
            **plan,
            "status": "RUNNING",
            "hardware": hardware,
            "ollama_version": version,
            "identities": identities,
            "results": [],
        }
        slot = b580_slot()
        try:
            for model in plan["models"]:
                try:
                    for repeat in range(plan["repeats"]):
                        for case in plan["cases"]:
                            started = time.monotonic()
                            with PeakSampler(lambda: xe_vram_mib(slot)) as sampler:
                                value = _request_json(
                                    f"{api}/chat",
                                    timeout=300,
                                    payload={
                                        "model": model,
                                        "stream": False,
                                        "think": False,
                                        "keep_alive": "15m",
                                        "options": {
                                            "num_ctx": 8192,
                                            "num_predict": plan["max_output_tokens"],
                                            "temperature": plan["temperature"],
                                            "top_p": plan["top_p"],
                                            "top_k": plan["top_k"],
                                            "presence_penalty": plan["presence_penalty"],
                                            "seed": plan["seed_base"] + repeat,
                                        },
                                        "messages": messages(case),
                                    },
                                )
                            if value.get("done") is not True:
                                raise ValueError("réponse Ollama incomplète")
                            resident = _request_json(f"{api}/ps").get("models", [])
                            if len(resident) != 1 or resident[0].get("digest") != identities[model]:
                                raise ValueError("identité ou résidence concurrente divergente")
                            if resident[0].get("size_vram", 0) <= 0:
                                raise ValueError("aucune allocation GPU observée")
                            duration = value.get("eval_duration", 0)
                            report["results"].append(
                                {
                                    "model": model,
                                    "case": case["id"],
                                    "repeat": repeat + 1,
                                    "wall_seconds": time.monotonic() - started,
                                    "output": value.get("message", {}).get("content", ""),
                                    "done_reason": value.get("done_reason"),
                                    "eval_count": value.get("eval_count"),
                                    "prompt_eval_count": value.get("prompt_eval_count"),
                                    "load_duration_ns": value.get("load_duration"),
                                    "tokens_per_second": value.get("eval_count", 0) / (duration / 1e9)
                                    if duration
                                    else None,
                                    "resident": resident[0],
                                    "xe_total_peak_mib": sampler.peak,
                                    "vram_samples": sampler.samples,
                                    "human_review": {
                                        criterion: None for criterion in case["criteria"]
                                    },
                                    "scope": VRAM_SCOPE,
                                }
                            )
                            write_json(output, report)
                finally:
                    _request_json(f"{api}/generate", payload={"model": model, "keep_alive": 0})
            after = _request_json(f"{api}/tags")["models"]
            after_ids = {item["name"]: item.get("digest") for item in after}
            if any(after_ids.get(model) != identities[model] for model in plan["models"]):
                raise ValueError("identités modèles modifiées pendant la comparaison")
            report.update(status="AWAITING_HUMAN_REVIEW", runtime_tested=True)
        except Exception as exc:
            report.update(status="INCOMPLETE", runtime_tested=False, error=str(exc))
            raise
        finally:
            write_json(output, report)
        return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tokens", type=int, default=1024)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    try:
        plan = comparison_plan(args.root, args.tokens, args.repeats)
        if args.live:
            run_comparison(args.root, resolve_runtime_root(args.runtime_root), args.output, plan)
        else:
            assert_no_symlinks(args.output, label="plan de comparaison")
            if args.output.exists():
                raise ValueError("choisir un nouveau fichier de plan")
            write_json(args.output, plan)
        print(json.dumps({"report": str(args.output), "live": args.live}))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(2, f"Comparaison interrompue: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
