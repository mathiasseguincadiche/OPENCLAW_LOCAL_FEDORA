"""Bounded real Ollama inference on public synthetic prompts; no agent execution."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

import yaml

from clawfedora import agent_eval, ollama_api

MODELS = {"qwen": "qwen3.5:9b-q4_K_M", "ornith": "ornith-1.5:9b"}
ROLES = (
    "chef-operations", "expert-recherche", "architecte-solutions", "ingenieur-devops",
    "ingenieur-securite", "auditeur-qualite", "redacteur-pedagogique",
)
OPTIONS = {"num_ctx": 8192, "num_predict": 1200, "num_gpu": 0,
           "num_thread": 4, "temperature": 0, "seed": 42}
SHA = re.compile(r"[0-9a-f]{40}\Z")
DIGEST = re.compile(r"(?:sha256:)?[0-9a-f]{64}\Z")
MAX_REPLY = 2_000_000
SHARED = ("CONTRACT.md", "PEDAGOGY.md", "TOOLS.md")
FIXTURE = {"service": "atlas-api", "port": 8443, "status": "inactive"}


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def _inputs(root: Path, mode: str) -> list[dict[str, Any]]:
    if mode not in {"smoke", "pilot", "extended"}:
        raise ValueError("mode de comparaison inconnu")
    suites = ("devops", "infraops") if mode == "extended" else ("infraops",)
    rows: list[dict[str, Any]] = []
    shared = "\n\n".join((root / "agents/_shared" / name).read_text(encoding="utf-8")
                          for name in SHARED)
    for suite_name in suites:
        suite = agent_eval.load_suite(root, suite_name)
        for case in suite["scenarios"]:
            role = case["role"]
            if role not in ROLES:
                raise ValueError("rôle inconnu")
            if mode == "smoke" and role not in {"ingenieur-devops", "auditeur-qualite"}:
                continue
            prompt = shared + "\n\n" + "\n\n".join(
                (root / "agents" / role / name).read_text(encoding="utf-8")
                for name in ("SOUL.md", "AGENTS.md")
            )
            prompt += (
                "\n\nQualification CPU : aucun outil OpenClaw, réseau, fichier projet "
                "ou exécution n'est disponible. Répondre en français, sans inventer de preuve. "
                "Privilégier une réponse concise et exploitable."
            )
            if len(prompt.encode()) > 36_000:
                raise ValueError("prompt de rôle hors budget")
            rows.append({"id": case["id"], "role": role, "system": prompt,
                         "prompt": case["prompt"], "expected": case["expected"]})
    return rows


def _chat(payload: dict[str, Any]) -> dict[str, Any]:
    # Fixed loopback only; no proxy, redirects, tools executed by the model or secrets.
    conn = HTTPConnection("127.0.0.1", 11434, timeout=600)
    try:
        conn.request("POST", "/api/chat", body=json.dumps(payload).encode(),
                     headers={"Content-Type": "application/json"})
        response = conn.getresponse()
        if response.status != 200:
            raise ValueError("chat Ollama HTTP non 200")
        raw = response.read(MAX_REPLY + 1)
        if len(raw) > MAX_REPLY:
            raise ValueError("réponse trop volumineuse")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("réponse chat non objet")
        return value
    finally:
        conn.close()


def _identity(root: Path, model: str) -> dict[str, Any]:
    version = yaml.safe_load(
        (root / "config/runtime_versions.yaml").read_text(encoding="utf-8")
    )["ollama"]["version"]
    actual = ollama_api.request_json(ollama_api.ENDPOINT + "/api/version")
    if actual.get("version") != version:
        raise ValueError("version Ollama différente du contrat")
    inventory = ollama_api.model_inventory(
        ollama_api.request_json(ollama_api.ENDPOINT + "/api/tags"),
        [{"alias": model, "runtime_id": MODELS[model], "quantization": "Q4_K_M"}],
    )
    identity = inventory[0]
    if not DIGEST.fullmatch(identity["digest"]):
        raise ValueError("empreinte de modèle absente")
    if not 0 < identity["size"] <= 8_000_000_000:
        raise ValueError("poids modèle hors budget")
    return {"ollama_version": version, **identity}


def _result(reply: dict[str, Any], expected_model: str) -> dict[str, Any]:
    message = reply.get("message")
    if (
        reply.get("model") != expected_model or reply.get("done") is not True
        or not isinstance(message, dict) or not isinstance(message.get("content"), str)
    ):
        raise ValueError("réponse modèle incomplète ou identité différente")
    metrics = {}
    for field in ("total_duration", "load_duration", "prompt_eval_count",
                  "prompt_eval_duration", "eval_count", "eval_duration"):
        value = reply.get(field)
        if type(value) is not int or value < 0:
            raise ValueError("mesures Ollama absentes")
        metrics[field] = value
    return {"content": message["content"], "done_reason": reply.get("done_reason"),
            "metrics": metrics, "tool_calls": message.get("tool_calls", [])}


def _tool_probe(model: str) -> dict[str, Any]:
    tool = {"type": "function", "function": {
        "name": "read_atlas_fixture", "description": "Lire le statut synthétique Atlas",
        "parameters": {"type": "object", "required": ["service"],
                       "properties": {"service": {"type": "string", "enum": ["atlas-api"]}},
                       "additionalProperties": False},
    }}
    messages = [{"role": "user", "content": (
        "Utilise exclusivement read_atlas_fixture pour atlas-api. Après réception du résultat, "
        "réponds exactement service=<nom>;port=<port>;status=<état> avec les valeurs "
        "réellement retournées. N'invente rien."
    )}]
    payload = {"model": model, "stream": False, "think": False,
               "options": OPTIONS, "keep_alive": "5m", "tools": [tool], "messages": messages}
    first = _result(_chat(payload), model)
    calls = first["tool_calls"]
    expected = {"name": "read_atlas_fixture", "arguments": {"service": "atlas-api"}}
    valid = (
        isinstance(calls, list) and len(calls) == 1 and isinstance(calls[0], dict)
        and isinstance(calls[0].get("function"), dict)
        and all(calls[0]["function"].get(key) == val for key, val in expected.items())
    )
    if not valid:
        return {"state": "FAIL_TOOL_CALL", "first": first}
    followup = [*messages, {"role": "assistant", "content": first["content"],
                            "tool_calls": calls},
                {"role": "tool", "tool_name": "read_atlas_fixture",
                 "content": json.dumps(FIXTURE)}]
    second = _result(_chat({**payload, "messages": followup}), model)
    passed = (second["content"].strip() == "service=atlas-api;port=8443;status=inactive"
              and not second["tool_calls"])
    return {"state": "PASS_FIXTURE_ONLY" if passed else "FAIL_TOOL_RESULT",
            "first": first, "second": second}


def run(root: Path, model: str, mode: str, commit: str, output: Path) -> dict[str, Any]:
    if model not in MODELS or not SHA.fullmatch(commit) or output.exists():
        raise ValueError("modèle, commit ou sortie invalide")
    cases = _inputs(root, mode)
    identity = _identity(root, model)
    report: dict[str, Any] = {
        "schema": 1, "classification": "synthetic_public", "commit": commit,
        "mode": mode, "suite_sha256": _digest(cases), "model": identity,
        "options": OPTIONS, "think": False, "backend": "ollama-cpu",
        "results": [], "tool_probe": {"state": "NOT_RUN"},
        "assessment": "INFERENCE_STARTED_NOT_REVIEWED",
        "native_agent_qualification": False, "gpu_qualification": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)

    def save() -> None:
        temporary = output.with_suffix(".tmp")
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(output)

    save()
    for case in cases:
        start = time.monotonic()
        try:
            reply = _result(_chat({
                "model": MODELS[model], "stream": False, "think": False,
                "keep_alive": "5m", "options": OPTIONS,
                "messages": [{"role": "system", "content": case["system"]},
                             {"role": "user", "content": case["prompt"]}],
            }), MODELS[model])
            row = {"state": "RESPONSE_COLLECTED" if reply["content"].strip()
                   else "EMPTY_RESPONSE", **reply}
        except (OSError, ValueError, TypeError, KeyError) as exc:
            row = {"state": "INFERENCE_ERROR", "error_type": type(exc).__name__}
        report["results"].append({
            "id": case["id"], "role": case["role"], "elapsed_ms": round(
                (time.monotonic() - start) * 1000),
            **row, "quality_review": "NOT_REVIEWED",
        })
        save()
        if row["state"] == "INFERENCE_ERROR":
            break
    if len(report["results"]) == len(cases) and all(
        row["state"] == "RESPONSE_COLLECTED" for row in report["results"]
    ):
        try:
            report["tool_probe"] = _tool_probe(MODELS[model])
        except (OSError, ValueError, TypeError, KeyError) as exc:
            report["tool_probe"] = {"state": "INFERENCE_ERROR", "error_type": type(exc).__name__}
        report["assessment"] = "RESPONSES_COLLECTED_REVIEW_REQUIRED"
    else:
        report["assessment"] = "INCOMPLETE_INFERENCE"
    save()
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Comparer deux modèles sur CPU sans publication")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--model", choices=MODELS, required=True)
    parser.add_argument("--mode", choices=("smoke", "pilot", "extended"), default="smoke")
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not args.run:
            cases = _inputs(args.root, args.mode)
            print(json.dumps({"assessment": "NOT_RUN", "case_ids": [c["id"] for c in cases],
                              "suite_sha256": _digest(cases)}))
            return 0
        report = run(args.root, args.model, args.mode, args.commit, args.output)
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report["assessment"] == "RESPONSES_COLLECTED_REVIEW_REQUIRED" else 1
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"assessment": "REFUSED_OR_INCOMPLETE",
                          "error_type": type(exc).__name__}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
