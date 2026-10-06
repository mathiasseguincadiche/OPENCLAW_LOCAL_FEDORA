"""Optional native response capture and blinded human comparison; never a skill score."""

from __future__ import annotations

import argparse
import hashlib
import html
import time
import uuid
from pathlib import Path
from subprocess import TimeoutExpired
from typing import Any

from clawfedora.core_config import AGENT_IDS, resolve_runtime_root, root_contract
from clawfedora.mentor import context as mentor_context
from clawfedora.project_common import assert_no_symlinks, read_json, sha256_file, write_json
from clawfedora.project_worker import AgentRunner, openclaw_runner, worker_lock
from clawfedora.webui_bridge import chat_prompt

SUITE = "benchmarks/suites/mentor_ops_fr.yaml"
MODEL = "qwen3.5:9b-q4_K_M"


def cases(repo: Path, selected: list[str] | None = None) -> list[dict[str, Any]]:
    import re

    import yaml

    suite = yaml.safe_load((repo / SUITE).read_text())
    if not isinstance(suite, dict):
        raise ValueError("suite YAML objet requise")
    rows = suite.get("cases", [])
    if not isinstance(rows, list) or not 1 <= len(rows) <= 20:
        raise ValueError("suite: 1 à 20 cas requis")
    ids: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("cas objet requis")
        identifier = row.get("id", "")
        if (
            not isinstance(identifier, str)
            or not re.fullmatch(r"[a-z0-9-]{1,64}", identifier)
            or identifier == "manifest"
        ):
            raise ValueError("identifiant de cas invalide")
        if identifier in ids or row.get("role") not in AGENT_IDS:
            raise ValueError("rôle ou identifiant de cas invalide")
        ids.add(identifier)
        criteria = row.get("criteria")
        if (
            not isinstance(criteria, list)
            or not 1 <= len(criteria) <= 6
            or any(not isinstance(c, str) or not 0 < len(c) <= 500 for c in criteria)
        ):
            raise ValueError("critères humains courts requis")
        chat_prompt(
            {
                "model": "openclaw/" + row["role"],
                "messages": row.get("history", []) + [{"role": "user", "content": row["prompt"]}],
            }
        )
    if selected and (len(set(selected)) != len(selected) or set(selected) - ids):
        raise ValueError("sélection de cas inconnue ou répétée")
    return [row for row in rows if not selected or row["id"] in selected]


def metadata(repo: Path, runtime: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    assert_no_symlinks(runtime / "workspaces", label="profils d’évaluation")
    prompts = {}
    for role in sorted({row["role"] for row in rows}):
        workspace = runtime / "workspaces" / role
        if read_json(workspace / ".openclaw-fedora-managed").get("agent_id") != role:
            raise ValueError("profil d’évaluation non géré")
        prompts[role] = {
            name: sha256_file(workspace / name)
            for name in ("AGENTS.md", "IDENTITY.md", "SOUL.md", "TOOLS.md")
        }
    pins = root_contract(repo, "runtime_versions.yaml")
    model = read_json(runtime / "state/model-identities.json").get("models", {}).get(MODEL)
    if not isinstance(model, dict) or not model.get("digest"):
        raise ValueError("identité Qwen adoptée requise")
    return {
        "suite_sha256": sha256_file(repo / SUITE),
        "cases": [row["id"] for row in rows],
        "deployed_prompts": prompts,
        "model": {key: model.get(key) for key in ("digest", "quantization_level")},
        "runtime_model": MODEL,
        "pins": {name: pins[name]["version"] for name in ("openclaw", "ollama")},
        "mentor_notes_sha256": sha256_file(runtime / "state/mentor.json")
        if (runtime / "state/mentor.json").exists()
        else None,
        "mentor_context_sha256": hashlib.sha256(mentor_context(runtime).encode()).hexdigest(),
    }


def capture(
    repo: Path,
    runtime: Path,
    output: Path,
    selected: list[str] | None = None,
    *,
    runner: AgentRunner | None = None,
) -> Path:
    rows = cases(repo, selected)
    assert_no_symlinks(output.parent, label="sortie d’évaluation")
    output.mkdir(exist_ok=False)
    with worker_lock(runtime):
        manifest: dict[str, Any] = {
            "schema_version": "1.0.0",
            "origin": "native-openclaw" if runner is None else "simulated",
            "status": "INCOMPLETE",
            "pedagogical_verdict": "NOT_REVIEWED",
            "skill_acquired": False,
            "records": [],
        }
        write_json(output / "manifest.json", manifest)
        try:
            baseline = metadata(repo, runtime, rows)
            manifest["conditions"] = baseline
            invoke = runner or openclaw_runner(runtime, repo, plain_text=True)
            for row in rows:
                # Fresh native session for each fixed history. No project transitions or note writes.
                _, prompt = chat_prompt(
                    {
                        "model": "openclaw/" + row["role"],
                        "messages": row.get("history", [])
                        + [{"role": "user", "content": row["prompt"]}],
                    }
                )
                started = time.monotonic()
                result = invoke(
                    row["role"], mentor_context(runtime) + "\n" + prompt, str(uuid.uuid4())
                )
                response = result.get("text")
                if not isinstance(response, str) or not 0 < len(response.encode()) <= 64000:
                    raise ValueError("réponse texte bornée requise")
                if metadata(repo, runtime, rows) != baseline:
                    raise ValueError("conditions modifiées pendant la capture")
                path = output / (row["id"] + ".json")
                write_json(
                    path,
                    {"case": row, "response": response, "seconds": time.monotonic() - started},
                )
                manifest["records"].append({"file": path.name, "sha256": sha256_file(path)})
                write_json(output / "manifest.json", manifest)
            manifest["status"] = "CAPTURED"
        finally:
            write_json(output / "manifest.json", manifest)
    return output / "manifest.json"


def _load_capture(directory: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    assert_no_symlinks(directory, label="capture")
    manifest = read_json(directory / "manifest.json")
    rows = []
    expected = manifest.get("conditions", {}).get("cases", [])
    if (
        manifest.get("status") != "CAPTURED"
        or manifest.get("origin") not in {"native-openclaw", "simulated"}
        or not expected
    ):
        raise ValueError("capture incomplète")
    for identifier, record in zip(expected, manifest["records"], strict=True):
        # Select only files in the supplied capture, with exact identity and hash.
        target = next((p for p in directory.iterdir() if p.name == record["file"]), None)
        if (
            target is None
            or target.name != identifier + ".json"
            or sha256_file(target) != record["sha256"]
        ):
            raise ValueError("capture modifiée")
        row = read_json(target)
        if row["case"]["id"] != identifier:
            raise ValueError("identité de cas modifiée")
        rows.append(row)
    return manifest, rows


def compare(before: Path, after: Path, output: Path) -> Path:
    left, old = _load_capture(before)
    right, new = _load_capture(after)
    a, b = left["conditions"], right["conditions"]
    for name in (
        "suite_sha256",
        "cases",
        "model",
        "runtime_model",
        "pins",
        "mentor_notes_sha256",
        "mentor_context_sha256",
    ):
        if a[name] != b[name]:
            raise ValueError(f"comparaison non comparable: {name}")
    if a["deployed_prompts"] == b["deployed_prompts"]:
        raise ValueError("profils déployés identiques: aucun avant/après pédagogique")
    if left["origin"] != right["origin"]:
        raise ValueError("origines différentes: simulation et modèle réel non comparables")
    assert_no_symlinks(output.parent, label="rapport")
    output.mkdir(exist_ok=False)
    sections, mapping = [], {}
    for prior, current in zip(old, new, strict=True):
        if prior["case"] != current["case"]:
            raise ValueError("cas modifié entre captures")
        swap = bool(uuid.uuid4().int % 2)
        choices = (current, prior) if swap else (prior, current)
        row = prior["case"]
        mapping[row["id"]] = {"A": "after" if swap else "before", "B": "before" if swap else "after"}
        sections.append(
            "<section><h2>"
            + html.escape(row["id"])
            + "</h2><p>"
            + html.escape(row["prompt"])
            + "</p><pre>Historique fixé : "
            + html.escape(str(row.get("history", [])))
            + "</pre><ul>"
            + "".join("<li>" + html.escape(c) + "</li>" for c in row["criteria"])
            + "</ul>"
            + "".join(
                "<h3>Réponse " + label + "</h3><pre>" + html.escape(value["response"]) + "</pre>"
                for label, value in zip(("A", "B"), choices, strict=True)
            )
            + "<p>Exactitude · clarté · adaptation aux acquis · prochaine action utile : "
            "à relire humainement. Préférence A/B/équivalentes et motif : __________</p></section>"
        )
    warning = (
        "SIMULATION — aucun modèle ni apprentissage évalué."
        if left["origin"] == "simulated"
        else (
            "Captures natives — jugement humain requis; aucune compétence certifiée. "
            "Une paire de réponses ne prouve pas un gain durable."
        )
    )
    report = output / "comparaison.html"
    report.write_text(
        '<!doctype html><html lang="fr"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        "style-src 'unsafe-inline'\">"
        "<title>Comparaison pédagogique OPS</title><style>"
        "body{max-width:960px;margin:auto;padding:24px;font:16px/1.5 sans-serif;color:#183344}"
        "h1,h2{color:#126b74}pre{white-space:pre-wrap;overflow-wrap:anywhere;"
        "background:#f0f5f6;padding:16px}section{border-top:1px solid #aaa;margin-top:32px}"
        "</style><h1>Comparer les réponses OPS</h1><p>"
        + warning
        + "</p>"
        + "".join(sections)
        + "</html>",
        encoding="utf-8",
    )
    write_json(output / "correspondance.json", mapping)
    write_json(
        output / "provenance.json", {"before": left, "after": right, "verdict": "NOT_REVIEWED"}
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("capture", help="appeler le Qwen natif, une session par cas")
    run.add_argument("--repo-root", type=Path, default=Path.cwd())
    run.add_argument("--runtime-root", type=Path)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--case", action="append", dest="selected")
    review = sub.add_parser("compare", help="préparer une comparaison A/B sans score automatique")
    review.add_argument("--before", type=Path, required=True)
    review.add_argument("--after", type=Path, required=True)
    review.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = (
            capture(
                args.repo_root, resolve_runtime_root(args.runtime_root), args.output, args.selected
            )
            if args.command == "capture"
            else compare(args.before, args.after, args.output)
        )
        print(result)
        return 0
    except (OSError, ValueError, KeyError, TypeError, TimeoutExpired) as exc:
        print("Évaluation non terminée: " + str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
