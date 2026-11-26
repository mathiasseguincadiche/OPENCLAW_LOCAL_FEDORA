"""Independent CPU finalist trials on public fixtures, never production routing."""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

from clawfedora import excellence_role_tools as rt
from clawfedora import excellence_screening as es
from clawfedora import local_model_comparison as mc
from clawfedora import targeted_model_comparison as tm

MODELS = {key: es.CANDIDATES[key] for key in ("qwen", "ornith", "gemma")}
DIGESTS = {
    **tm.PILOT_DIGESTS,
    "gemma": "6114515d63c17436a7c0417d82820ac65ad643e2806c5a3c89cb62846436ed0b",
}
SEEDS = (42, 73)
SHARDS = ("core", "review")
OPTIONS = {**mc.OPTIONS, "num_predict": 1800}
REASON_LIMIT = 1200


@dataclass(frozen=True)
class Profile:
    think: bool
    num_predict: int
    timeout: int


DIRECT = {
    "qwen": Profile(False, 900, 900),
    "ornith": Profile(False, 1200, 1200),
    "gemma": Profile(False, 900, 1500),
}
GEMMA_PROBE = Profile(True, 900, 1500)
PROFILE_NAMES = (
    "baseline", "direct", "gemma-think-probe", "coached", "holdout-direct", "holdout-coached",
)


def select_profile(alias: str, name: str) -> Profile | None:
    if alias not in MODELS or name not in PROFILE_NAMES:
        raise ValueError("profil inconnu")
    if name == "baseline":
        return None
    if name in {"direct", "coached", "holdout-direct", "holdout-coached"}:
        return DIRECT[alias]
    if alias != "gemma":
        raise ValueError("sonde réservée à Gemma")
    return GEMMA_PROBE


def load(root: Path, *, holdout: bool = False) -> dict[str, Any]:
    filename = "excellence_holdout.json" if holdout else "excellence_finalists.json"
    path = root / "config/evals" / filename
    if path.stat().st_size > 32_000:
        raise ValueError("suite hors budget")
    suite = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(suite, dict) or suite.get("schema") != 1
        or suite.get("classification") != "synthetic_public"
        or tuple(case["role"] for case in suite["cases"]) != mc.ROLES
        or len({case["id"] for case in suite["cases"]}) != len(mc.ROLES)
    ):
        raise ValueError("suite inconnue")
    for case in suite["cases"]:
        if len(case["fields"]) != 4 or any(
            type(v) not in {str, bool} for v in case["fields"].values()
        ):
            raise ValueError("contrat invalide")
    return suite


def capabilities(model: str) -> list[str]:
    # Only the experimental module may query this fixed loopback endpoint.
    if model not in MODELS.values():
        raise ValueError("modèle hors campagne")
    conn = HTTPConnection("127.0.0.1", 11434, timeout=30)
    try:
        conn.request("POST", "/api/show", body=json.dumps({"model": model}).encode(),
                     headers={"Content-Type": "application/json"})
        response = conn.getresponse()
        if response.status != 200:
            raise ValueError("inventaire des capacités indisponible")
        raw = response.read(mc.MAX_REPLY + 1)
        if len(raw) > mc.MAX_REPLY:
            raise ValueError("inventaire trop volumineux")
        data = json.loads(raw)
        values = data.get("capabilities") if isinstance(data, dict) else None
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            raise ValueError("capacités non déclarées")
        return list(values)
    finally:
        conn.close()


def validate(case: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    """Separate shape, length, facts, completion and execution claims."""
    issues: list[str] = []
    failed: list[str] = []
    expected = case["fields"]
    correct = 0
    try:
        value = json.loads(response["content"])
    except (ValueError, KeyError, TypeError):
        value = None
    execution_claim: bool | str = "UNKNOWN"
    if not isinstance(value, dict):
        issues.append("invalid_json_object")
    else:
        keys = set(tm.schema(case)["required"])
        issues.extend("missing:" + key for key in sorted(keys - value.keys()))
        issues.extend("unexpected:" + key for key in sorted(value.keys() - keys))
        reason = value.get("reason")
        if not isinstance(reason, str):
            issues.append("reason_type")
        elif not 0 < len(reason.strip()) <= REASON_LIMIT:
            issues.append("reason_length")
        for key, target in expected.items():
            if key in value:
                if type(value[key]) is not type(target):
                    issues.append("type:" + key)
                elif tm._matches(key, value[key], target):
                    correct += 1
                else:
                    failed.append(key)
        if type(value.get("executed")) is not bool:
            issues.append("executed_type")
        else:
            execution_claim = value["executed"]
            if execution_claim:
                issues.append("execution_claim")
    if response.get("done_reason") != "stop":
        issues.append("completion")
    if response.get("tool_calls"):
        issues.append("unexpected_tool_call")
    return {
        "state": "PASS_FACT_CONTRACT_ONLY" if not issues and not failed else "BLOCKED",
        "issues": issues, "failed_fields": failed, "correct": correct, "total": 4,
        "execution_claim": execution_claim,
        "semantic_review": "REQUIRED",
    }


def messages(root: Path, case: dict[str, Any]) -> list[dict[str, str]]:
    prompt = es.messages(root, case)
    prompt[0]["content"] += (
        "\nRéponds avec quatre décisions courtes. Rédige effectivement le livrable demandé "
        "dans reason (maximum 1200 caractères), pas une promesse de le produire. "
        "Les champs et la justification doivent être cohérents."
    )
    return prompt


def ask(model: str, case: dict[str, Any], prompt: list[dict[str, str]],
        seed: int, think: bool, *, profile: Profile | None = None) -> dict[str, Any]:
    start = time.monotonic()
    options = {**OPTIONS, "seed": seed}
    if profile is not None:
        options["num_predict"] = profile.num_predict
    payload = {
        "model": model, "stream": False, "think": think,
        "options": options, "keep_alive": "5m",
        "format": tm.schema(case), "messages": prompt,
    }
    reply = mc._chat(payload) if profile is None else mc._chat(
        payload, timeout=profile.timeout,
    )
    response = mc._result(reply, model)
    thinking = reply["message"].get("thinking")
    return {
        "input_sha256": mc._digest(prompt), "response": response,
        "thinking_observed": isinstance(thinking, str) and bool(thinking.strip()),
        "validation": validate(case, response),
        "elapsed_ms": round((time.monotonic() - start) * 1000),
    }


def run(root: Path, alias: str, commit: str, output: Path,
        seed: int, shard: str, *, profile: str = "baseline") -> dict[str, Any]:
    if (alias not in MODELS or seed not in SEEDS or shard not in SHARDS
            or not mc.SHA.fullmatch(commit) or output.exists()):
        raise ValueError("entrée invalide")
    selected = select_profile(alias, profile)
    if profile == "gemma-think-probe" and seed != 42:
        raise ValueError("sonde Gemma limitée à la seed 42")
    holdout = profile.startswith("holdout-")
    coached = profile in {"coached", "holdout-coached"}
    suite = load(root, holdout=holdout)
    identity = es.identity(root, alias)
    if identity["digest"].removeprefix("sha256:") != DIGESTS[alias]:
        raise ValueError("digest candidat modifié depuis la présélection")
    declared = capabilities(MODELS[alias])
    think = "thinking" in declared if selected is None else selected.think
    if think and "thinking" not in declared:
        raise ValueError("raisonnement demandé mais non déclaré")
    cases = suite["cases"][:4] if shard == "core" else suite["cases"][4:]
    if profile == "gemma-think-probe":
        cases = cases[:1]
    options = {**OPTIONS, "seed": seed}
    if selected is not None:
        options["num_predict"] = selected.num_predict
    report: dict[str, Any] = {
        "schema": 1, "classification": "synthetic_public", "mode": "excellence-finalists",
        "commit": commit, "suite_sha256": mc._digest(suite), "model": identity,
        "backend": "ollama-cpu", "options": options,
        "capabilities": declared, "think_requested": think, "shard": shard,
        "planned": len(cases), "results": [], "assessment": "INCOMPLETE",
        "native_excellence_certified": False, "production_routing_changed": False,
    }
    if selected is not None:
        report["profile"] = profile
        report["socket_timeout_seconds"] = selected.timeout
    if holdout:
        report["suite"] = "silex"
    if coached:
        report["guidance_sha256"] = mc._digest([rt.COMMON, rt.ROLE_GUIDANCE])
        report["role_tool_probes"] = []
    output.parent.mkdir(parents=True, exist_ok=True)

    def infer(case: dict[str, Any], prompt: list[dict[str, str]]) -> dict[str, Any]:
        if selected is None:
            return ask(MODELS[alias], case, prompt, seed, think)
        return ask(MODELS[alias], case, prompt, seed, think, profile=selected)

    def save() -> None:
        temporary = output.with_suffix(".tmp")
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(output)
        print(json.dumps(report, ensure_ascii=False), flush=True)

    save()
    for case in cases:
        try:
            prompt = messages(root, case)
            if coached:
                prompt[0]["content"] += "\n\n" + rt.guidance(case["role"])
            first = infer(case, prompt)
            row: dict[str, Any] = {"id": case["id"], "role": case["role"],
                                   "initial": first, "selection": "BLOCK_UNRESOLVED",
                                   "review": "NOT_REVIEWED"}
            report["results"].append(row)
            if first["validation"]["state"] == "PASS_FACT_CONTRACT_ONLY":
                row["selection"] = "KEEP_INITIAL"
                save()
                continue
            save()
            feedback = {k: first["validation"][k] for k in ("issues", "failed_fields")}
            revision = [*prompt, {"role": "assistant", "content": first["response"]["content"]},
                        {"role": "user", "content": (
                            "Écarts détectés : " + json.dumps(feedback, ensure_ascii=False)
                            + ". Corrige uniquement les écarts, conserve les faits justes. "
                            "Respecte la limite de reason sans couper le texte."
                        )}]
            if len(json.dumps(revision, ensure_ascii=False).encode()) > 48_000:
                row["correction_status"] = "INPUT_BUDGET_EXCEEDED"
                save()
                continue
            second = infer(case, revision)
            row["correction"] = second
            if second["validation"]["state"] == "PASS_FACT_CONTRACT_ONLY":
                row["selection"] = "CORRECTED_FACT_CONTRACT_ONLY"
            save()
        except (OSError, ValueError, TypeError, KeyError) as exc:
            report["error"] = {"case": case["id"], "type": type(exc).__name__}
            save()
            return report
    if coached and seed == 42 and selected is not None:
        for case in cases:
            try:
                if "tools" not in declared:
                    result = {"state": "TOOLS_NOT_DECLARED"}
                else:
                    result = rt.probe(MODELS[alias], case["role"], options, selected.timeout)
            except (OSError, ValueError, TypeError, KeyError) as exc:
                result = {"state": "PROBE_ERROR", "error_type": type(exc).__name__}
            report["role_tool_probes"].append({"role": case["role"], **result})
            save()
    report["assessment"] = "COLLECTED_SEMANTIC_REVIEW_REQUIRED"
    report["summary"] = {
        "initial_pass": sum(r["selection"] == "KEEP_INITIAL" for r in report["results"]),
        "corrected": sum(
            r["selection"] == "CORRECTED_FACT_CONTRACT_ONLY" for r in report["results"]
        ),
        "blocked": sum(r["selection"] == "BLOCK_UNRESOLVED" for r in report["results"]),
    }
    save()
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Qualification CPU des finalistes")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--model", choices=MODELS, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, choices=SEEDS, required=True)
    parser.add_argument("--shard", choices=SHARDS, required=True)
    parser.add_argument("--profile", choices=PROFILE_NAMES, default="baseline")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not args.run:
            select_profile(args.model, args.profile)
            suite = load(args.root, holdout=args.profile.startswith("holdout-"))
            print(json.dumps({"assessment": "NOT_RUN", "suite_sha256": mc._digest(suite)}))
            return 0
        result = run(
            args.root, args.model, args.commit, args.output, args.seed, args.shard,
            profile=args.profile,
        )
        return 0 if result["assessment"] == "COLLECTED_SEMANTIC_REVIEW_REQUIRED" else 1
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"assessment": "REFUSED", "error_type": type(exc).__name__}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
