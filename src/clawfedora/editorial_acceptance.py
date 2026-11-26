"""Operator-led editorial qualification ledger; no agents or remote actions launched."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from clawfedora import notion_write as nw
from clawfedora.structured_response import parse_response

COMMIT = re.compile(r"[0-9a-f]{40}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")
NAME = re.compile(r"[a-zA-Z0-9_-][a-zA-Z0-9_.-]{0,95}\Z")
MAX_PROOF = 20_000_000
CASES = (
    ("roles", "Vérifier les sept rôles, modèles locaux, outils et refus hors périmètre."),
    ("markdown", "Produire un README et une fiche pédagogique ; auditer et corriger."),
    ("diagrams", "Créer deux vues distinctes Draw.io/SVG, vérifier la paire et la géométrie."),
    ("identity", "Créer deux identités distinctes et contrôler les sources JSON/SVG."),
    ("notion-spec", "Réviser la spécification du wiki, préserver installation et parcours."),
    ("notion-native", "Créer un wiki privé de test, médias, galeries, relations et rollup."),
    ("navigation", "Vérifier les copies synchronisées et la propagation manuelle."),
    ("enrichment", "Ajouter une section approuvée ; préserver blocs et progression."),
    ("coherence", "Détecter divergence et exposition fictive ; ne pas révéler la valeur."),
    ("github-native", "Publier uniquement dans un dépôt de test après approbation."),
    ("visual", "Examiner les six vues réelles de GitHub et Notion, clair et sombre."),
    ("negative", "Refuser sortie divergente, source altérée, doublon, rejeu et faux succès."),
    ("learning", "Pratiquer un exercice, distinguer aide, résultat, diagnostic et autonomie."),
)


def _commit(value: str) -> str:
    if not isinstance(value, str) or COMMIT.fullmatch(value) is None:
        raise ValueError("commit déployé exact requis (40 caractères hexadécimaux)")
    return value


def plan() -> dict[str, Any]:
    return {
        "schema": 1, "scenario": "atelier-atlas",
        "assessment": "NOT_RUN",
        "cases": [{"id": ident, "objective": objective, "state": "NOT_RUN"}
                  for ident, objective in CASES],
        "native_qualification": False,
        "remote_actions_executed": False,
    }


def _private(path: Path, *, directory: bool = False) -> None:
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("chemin de réception lié interdit")
    if not (path.is_dir() if directory else path.is_file()):
        raise ValueError("élément de réception absent")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError("réception privée requise")


def template(commit: str, output: Path) -> dict[str, Any]:
    _private(output.parent, directory=True)
    if any((p / ".git").exists() for p in (output.parent, *output.parent.parents)):
        raise ValueError("preuves interdites dans un dépôt Git")
    value = {
        "schema": 1, "scenario": "atelier-atlas", "deployed_commit": _commit(commit),
        "operator_attests_native_run": False,
        "cases": {ident: {"state": "NOT_RUN", "evidence": []} for ident, _ in CASES},
    }
    nw._private_new(output, value)
    return {"assessment": "TEMPLATE_CREATED_NOT_RUN", "case_count": len(CASES)}


def _read(path: Path, maximum: int) -> bytes:
    _private(path)
    if path.stat().st_size > maximum:
        raise ValueError("preuve trop volumineuse")
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    if not 0 < len(raw) <= maximum:
        raise ValueError("preuve vide ou trop volumineuse")
    return raw


def _proof(root: Path, entry: object, used: set[str]) -> str:
    if not isinstance(entry, dict) or set(entry) != {"file", "sha256"}:
        raise ValueError("référence de preuve invalide")
    name, digest = entry["file"], entry["sha256"]
    if (
        not isinstance(name, str) or not NAME.fullmatch(name) or ".." in name
        or name in used or not isinstance(digest, str) or not SHA.fullmatch(digest)
    ):
        raise ValueError("preuve hors périmètre, répétée ou empreinte invalide")
    actual = hashlib.sha256(_read(root / name, MAX_PROOF)).hexdigest()
    if actual != digest:
        raise ValueError("preuve modifiée depuis la déclaration")
    used.add(name)
    return actual


def evaluate(form: Path, commit: str) -> dict[str, Any]:
    _private(form.parent, directory=True)
    if any((p / ".git").exists() for p in (form.parent, *form.parent.parents)):
        raise ValueError("preuves interdites dans un dépôt Git")
    raw = _read(form, 30_000)
    data = parse_response(raw.decode("utf-8"), {"type": "object"})
    if (
        set(data) != {"schema", "scenario", "deployed_commit", "operator_attests_native_run",
                      "cases"}
        or data["schema"] != 1 or data["scenario"] != "atelier-atlas"
        or data["deployed_commit"] != _commit(commit)
        or type(data["operator_attests_native_run"]) is not bool
        or not isinstance(data["cases"], dict)
        or set(data["cases"]) != {ident for ident, _ in CASES}
    ):
        raise ValueError("formulaire, campagne ou commit incohérent")
    used = {form.name}
    seen_hashes: set[str] = set()
    results: list[dict[str, Any]] = []
    for ident, _ in CASES:
        row = data["cases"][ident]
        if (
            not isinstance(row, dict) or set(row) != {"state", "evidence"}
            or row["state"] not in {"NOT_RUN", "PASS", "FAIL", "BLOCKED"}
            or not isinstance(row["evidence"], list) or len(row["evidence"]) > 4
        ):
            raise ValueError("cas de réception invalide")
        state = row["state"]
        if state in {"PASS", "FAIL"} and (
            not data["operator_attests_native_run"] or not row["evidence"]
        ):
            raise ValueError("essai déclaré sans attestation native et preuve")
        if state == "NOT_RUN" and row["evidence"]:
            raise ValueError("cas non exécuté avec preuves")
        hashes = [_proof(form.parent, item, used) for item in row["evidence"]]
        if len(set(hashes)) != len(hashes) or seen_hashes.intersection(hashes):
            raise ValueError("contenu de preuve réutilisé")
        seen_hashes.update(hashes)
        results.append({"id": ident, "state": state, "evidence_sha256": hashes})
    states = {row["state"] for row in results}
    assessment = (
        "OPERATOR_REPORTED_FAILURE" if "FAIL" in states else
        "OPERATOR_REPORTED_COMPLETE" if states == {"PASS"} else
        "OPERATOR_REVIEW_INCOMPLETE"
    )
    return {
        "schema": 1, "scenario": "atelier-atlas", "assessment": assessment,
        "deployed_commit": commit, "reviewed_at": datetime.now(UTC).isoformat(),
        "form_sha256": hashlib.sha256(raw).hexdigest(), "cases": results,
        "operator_attests_native_run": data["operator_attests_native_run"],
        "native_qualification": False, "remote_actions_executed": False,
        "limitations": "Empreintes et déclarations vérifiées, contenu des preuves non certifié.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Réception éditoriale Atlas, sans exécution")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("plan")
    create = sub.add_parser("template")
    create.add_argument("--commit", required=True)
    create.add_argument("--output", type=Path, required=True)
    check = sub.add_parser("review")
    check.add_argument("--commit", required=True)
    check.add_argument("--form", type=Path, required=True)
    check.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.action == "plan":
            result = plan()
        elif args.action == "template":
            result = template(args.commit, args.output)
        else:
            result = evaluate(args.form, args.commit)
            if args.output is not None:
                if args.output.parent != args.form.parent:
                    raise ValueError("reçu dans le dossier privé de réception requis")
                nw._private_new(args.output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if args.action == "review" and result["assessment"] != (
            "OPERATOR_REPORTED_COMPLETE"
        ) else 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"assessment": "REFUSED", "reason": type(exc).__name__}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
