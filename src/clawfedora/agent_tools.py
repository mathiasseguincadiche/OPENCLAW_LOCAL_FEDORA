"""Bounded, deterministic helpers for agent proposals; never execute proposed code."""

from __future__ import annotations

import ast
import html
import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml

from clawfedora.core_config import AGENT_IDS
from clawfedora.project_common import assert_no_symlinks, read_json
from clawfedora.specialist_tools import FORMATS, available, lint, receipt, run_fixed

TOOL_ROLES = {
    "clawfedora_search": set(AGENT_IDS),
    "clawfedora_outline": set(AGENT_IDS),
    "clawfedora_diagram": {"architecte-solutions"},
    "clawfedora_check": {"ingenieur-devops", "ingenieur-securite", "auditeur-qualite"},
    "clawfedora_lint": set(FORMATS),
    "clawfedora_tool_status": set(AGENT_IDS),
}
OUTLINES = {
    "chef-operations": {"brief": ["Objectif", "Contraintes", "Livrables", "Critères de fin"]},
    "expert-recherche": {"sources": ["Question", "Source et date", "Preuve", "Limites"]},
    "architecte-solutions": {
        "adr": ["Contexte", "Options", "Décision et compromis", "Conséquences", "Réversibilité"],
    },
    "ingenieur-devops": {
        "runbook": [
            "But",
            "Prérequis et droits",
            "Procédure",
            "Résultat attendu",
            "Preuves",
            "Rollback",
        ],
        "incident": ["Symptômes", "Impact", "Diagnostic", "Correction", "Validation", "Prévention"],
    },
    "ingenieur-securite": {
        "threats": ["Actifs", "Scénario", "Contrôles", "Validation", "Risque résiduel"]
    },
    "auditeur-qualite": {"audit": ["Critère", "Preuve observée", "Limite", "Verdict", "Action"]},
    "redacteur-pedagogique": {
        "guide": [
            "Le problème",
            "Le mécanisme",
            "Un petit exemple",
            "À vous de pratiquer",
            "Vérifier",
            "Diagnostiquer",
        ],
        "explanation": [
            "Idée principale",
            "Vocabulaire utile",
            "Pourquoi ce choix",
            "Limites",
            "Prochaine étape",
        ],
    },
}


def _workspace(runtime: Path, role: str, workspace: Path) -> Path:
    if role not in AGENT_IDS:
        raise ValueError("rôle inconnu")
    expected = runtime / "workspaces" / role
    for parent in (runtime, runtime / "workspaces", expected, workspace):
        if parent.is_symlink():
            raise ValueError("workspace lié interdit")
    if workspace.resolve() != expected.resolve():
        raise ValueError("workspace hors rôle")
    marker = expected / ".openclaw-fedora-managed"
    if marker.is_symlink() or read_json(marker).get("agent_id") != role:
        raise ValueError("workspace non géré")
    return expected


def _search(workspace: Path, data: dict[str, Any]) -> dict[str, Any]:
    scope = str(data.get("scope", "."))
    if Path(scope).is_absolute() or ".." in Path(scope).parts:
        raise ValueError("scope relatif au snapshot requis")
    root = workspace / scope
    if not root.is_dir() or not root.resolve().is_relative_to(workspace.resolve()):
        raise ValueError("scope hors workspace")
    assert_no_symlinks(root, label="recherche")
    words = str(data.get("query", "")).lower().split()
    if not words or len(words) > 12:
        raise ValueError("requête courte requise")
    hits: list[dict[str, Any]] = []
    scanned = 0
    budget = 2_000_000
    for path in sorted(root.rglob("*")):
        if scanned >= 200 or budget <= 0:
            break
        if not path.is_file() or path.suffix.lower() not in {".md", ".txt", ".json", ".yaml", ".yml"}:
            continue
        scanned += 1
        if path.stat().st_size > min(128_000, budget):
            continue
        budget -= path.stat().st_size
        content = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(content.splitlines(), 1):
            if any(word in line.lower() for word in words):
                hits.append(
                    {
                        "path": path.relative_to(workspace).as_posix(),
                        "line": number,
                        "text": line[:800],
                    }
                )
                if len(hits) == 4:
                    return {"hits": hits, "scanned": scanned, "bounded": True}
    return {"hits": hits, "scanned": scanned, "bounded": True}


def diagram(data: dict[str, Any]) -> dict[str, Any]:
    """Render escaped labels as inert SVG and Mermaid; no HTML, URLs or scripts."""
    nodes, edges = data.get("nodes"), data.get("edges", [])
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= 8:
        raise ValueError("1 à 8 nœuds requis")
    if not isinstance(edges, list) or len(edges) > 12:
        raise ValueError("12 liens maximum")
    labels = [str(item) for item in nodes]
    if any(not label.strip() or len(label) > 60 for label in labels):
        raise ValueError("libellés courts requis")
    width, height = 620, len(labels) * 70 + 40
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f3f6fa"/>',
    ]
    mermaid = ["flowchart TD"]
    for index, label in enumerate(labels):
        y = index * 70 + 20
        svg += [
            f'<rect x="170" y="{y}" width="330" height="48" rx="8" fill="#173a56"/>',
            f'<text x="335" y="{y + 29}" text-anchor="middle" fill="white" '
            f'font-family="sans-serif" font-size="13">{html.escape(label)}</text>',
        ]
        safe = "".join(c if c.isalnum() or c in " -_.,/" else " " for c in label)
        mermaid.append(f'  n{index}["{safe}"]')
    for edge in edges:
        if (
            not isinstance(edge, list)
            or len(edge) != 2
            or any(type(i) is not int or not 0 <= i < len(labels) for i in edge)
        ):
            raise ValueError("liens [index source, index destination] requis")
        a, b = edge
        svg.append(
            f'<path d="M 170 {a * 70 + 44} H 80 V {b * 70 + 44} H 170" '
            'stroke="#367a93" stroke-width="2" fill="none"/>'
        )
        mermaid.append(f"  n{a} --> n{b}")
    rendered = "".join(svg) + "</svg>"
    renderer = "builtin"
    warning = "Graphviz absent: rendu simple embarqué utilisé."
    if Path("/usr/bin/dot").is_file():
        # Only structured labels/edges become DOT; arbitrary DOT attributes are never accepted.
        dot = ["digraph G { rankdir=TB; node [shape=box];"]
        dot.extend(
            f"n{i} [label={json.dumps(label, ensure_ascii=False)}];" for i, label in enumerate(labels)
        )
        dot.extend(f"n{a} -> n{b};" for a, b in edges)
        dot.append("}")
        result = run_fixed(["/usr/bin/dot", "-Tsvg"], "\n".join(dot))
        if result.returncode or len(result.stdout.encode()) > 16000:
            raise ValueError("rendu Graphviz échoué ou trop volumineux")
        rendered, renderer, warning = result.stdout, "graphviz", ""
    return {
        "svg": rendered,
        "mermaid": "\n".join(mermaid),
        "renderer": renderer,
        "warning": warning,
        "scope": "schéma proposé, aucune architecture déployée",
    }


def check(data: dict[str, Any]) -> dict[str, Any]:
    content, kind = data.get("content"), data.get("format")
    if not isinstance(content, str) or not 0 < len(content.encode()) <= 12000:
        raise ValueError("contenu limité à 12000 octets requis")
    findings: list[str] = []
    try:
        if kind == "json":
            json.loads(content)
        elif kind == "yaml":
            yaml.safe_load(content)
        elif kind == "python":
            ast.parse(content)
        elif kind != "text":
            raise ValueError("format json/yaml/python/text requis")
    except (json.JSONDecodeError, yaml.YAMLError, SyntaxError) as exc:
        findings.append(f"Syntaxe invalide: {str(exc)[:350]}")
    for pattern, warning in {
        "curl |": "vérifier le script téléchargé avant exécution",
        "chmod 777": "droits excessifs",
        "setenforce 0": "désactivation SELinux proposée",
        "0.0.0.0": "écoute réseau globale à justifier",
        "--privileged": "conteneur privilégié à justifier",
        "rm -rf": "suppression récursive à encadrer",
    }.items():
        if pattern in content:
            findings.append(warning)
    return {
        "scope": "statique seulement",
        "runtime_tested": False,
        "format": kind,
        "findings": findings,
        "note": "Aucun code exécuté; absence de finding != sécurité prouvée.",
    }


def invoke(
    runtime: Path, role: str, workspace: Path, tool: str, data: dict[str, Any]
) -> dict[str, Any]:
    root = _workspace(runtime, role, workspace)
    if tool not in TOOL_ROLES or role not in TOOL_ROLES[tool]:
        raise ValueError("outil interdit pour ce rôle")
    if len(json.dumps(data).encode()) > 24000:
        raise ValueError("paramètres trop volumineux")
    if tool == "clawfedora_search":
        return _search(root, data)
    if tool == "clawfedora_diagram":
        result = diagram(data)
        svg = result.pop("svg")
        result["receipt"] = receipt(root, tool, result, svg=svg)
        result["instruction"] = (
            "Sortie .svg: utiliser svg_reference comme contenu JSON; le worker collecte le rendu."
        )
        return result
    if tool == "clawfedora_check":
        return check(data)
    if tool == "clawfedora_tool_status":
        return {"available": available(), "lint_formats": sorted(FORMATS.get(role, set()))}
    if tool == "clawfedora_lint":
        result = lint(role, data)
        result["receipt"] = receipt(root, tool, result)
        return result
    kind = str(data.get("kind", ""))
    if kind not in OUTLINES[role]:
        raise ValueError("type de document interdit pour ce rôle")
    title = str(data.get("title", "Document"))[:120].replace("\n", " ")
    return {
        "kind": kind,
        "outline": "# "
        + title
        + "\n\n"
        + "\n\n".join(
            f"## {section}\n\nÀ compléter avec les sources et preuves observées."
            for section in OUTLINES[role][kind]
        ),
        "scope": "trame, aucune preuve inventée",
    }


def main() -> int:
    try:
        raw = sys.stdin.buffer.read(24001)
        if len(raw) > 24000:
            raise ValueError("requête trop volumineuse")
        data = json.loads(raw)
        runtime = Path(os.environ["OPENCLAW_LOCAL_FEDORA_ROOT"])
        value = invoke(runtime, sys.argv[1], Path(sys.argv[2]), sys.argv[3], data)
        print(json.dumps(value, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
        print(json.dumps({"error": str(exc)[:350]}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
