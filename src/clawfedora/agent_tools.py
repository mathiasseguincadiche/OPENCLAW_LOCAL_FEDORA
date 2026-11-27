"""Bounded, deterministic helpers for agent proposals; never execute proposed code."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import yaml

from clawfedora.ci_reports import summarize
from clawfedora.core_config import AGENT_IDS
from clawfedora.diagram_layouts import style_and_arrange
from clawfedora.diagram_review import inspect_page
from clawfedora.document_impact import inspect as inspect_impact
from clawfedora.document_review import inspect_document
from clawfedora.drawio import decorate_page, export_page_svg, inspect_diagram, multi_view_diagram
from clawfedora.file_artifacts import formats, produce
from clawfedora.project_common import assert_no_symlinks, read_json
from clawfedora.specialist_tools import FORMATS, available, lint, receipt

TOOL_ROLES = {
    "clawfedora_artifact": set(AGENT_IDS),
    "clawfedora_notion_inventory": set(AGENT_IDS),
    "clawfedora_notion_studio_check": {
        "architecte-solutions", "redacteur-pedagogique", "auditeur-qualite",
    },
    "clawfedora_search": set(AGENT_IDS),
    "clawfedora_outline": set(AGENT_IDS),
    "clawfedora_diagram": {"architecte-solutions"},
    "clawfedora_lab_request": {"ingenieur-devops"},
    "clawfedora_sandbox_validate": {"ingenieur-devops"},
    "clawfedora_sandbox_iterate": {"ingenieur-devops"},
    "clawfedora_doc_links": {"redacteur-pedagogique", "auditeur-qualite"},
    "clawfedora_impact": {"chef-operations", "architecte-solutions", "ingenieur-devops",
                         "redacteur-pedagogique", "auditeur-qualite"},
    "clawfedora_doc_review": {"redacteur-pedagogique", "auditeur-qualite"},
    "clawfedora_check": {"ingenieur-devops", "ingenieur-securite", "auditeur-qualite"},
    "clawfedora_lint": set(FORMATS),
    "clawfedora_tool_status": set(AGENT_IDS),
    "clawfedora_ci_report": set(AGENT_IDS),
}
OUTLINES = {
    "chef-operations": {
        "brief": [
            "Besoin OPS",
            "Acquis et difficulté",
            "Décision attendue du spécialiste",
            "Livrable et preuve",
            "Décision de l’opérateur et prochaine pratique",
        ],
        "handover": [
            "Service reçu et fonction métier",
            "Sources, version, artefact immuable et empreintes",
            "Topologie, dépendances, ports, identités et stockage",
            "Démarrage, surveillance, sauvegarde et restauration",
            "Conditions d'échec, diagnostic et retour arrière",
            "Réception sur cible, preuves et validation humaine",
        ]
    },
    "expert-recherche": {
        "sources": [
            "Question et version installée",
            "Source, version, section lue et date",
            "Fichier, ligne et révision",
            "Conséquence et incertitude",
        ]
    },
    "architecte-solutions": {
        "adr": [
            "Contexte",
            "Options",
            "Décision et compromis",
            "Flux nommés et frontières",
            "Conséquences",
            "Réversibilité",
        ],
        "service_contract": [
            "Fonction applicative et responsabilités d'exploitation",
            "Architecture actuelle et cible : ne pas les confondre",
            "Flux, ports, frontières, secrets et états",
            "Observabilité, dépendances et persistance",
            "Alternatives, limites, pannes et récupération",
            "Critères de réception à faire vérifier par le DevOps",
        ],
    },
    "ingenieur-devops": {
        "runbook": [
            "But",
            "Machine cible, répertoire, prérequis et droits",
            "Procédure",
            "Résultat attendu",
            "Contrôle et preuve",
            "Premier écart et condition d’arrêt",
            "Reprise après échec partiel et retour arrière",
        ],
        "incident": ["Symptômes", "Impact", "Diagnostic", "Correction", "Validation", "Prévention"],
        "operations_acceptance": [
            "Cible isolée et accord de l'opérateur",
            "État initial, version et configuration",
            "Scénario de panne, répétition ou restauration",
            "Observation attendue, journaux et métriques",
            "Seuil d'arrêt, rollback et reprise",
            "Preuves datées, limites et réception humaine",
        ],
    },
    "ingenieur-securite": {
        "threats": [
            "Actif et version",
            "Constat et preuve expurgée",
            "Correction minimale",
            "Test après correction",
            "Risque résiduel",
        ]
    },
    "auditeur-qualite": {
        "audit": [
            "Critère",
            "Référence contrôlée, cible et révision",
            "Portée",
            "Verdict",
            "Contrôle manquant",
        ],
        "reader_review": [
            "Source, SHA et périmètre réellement consulté",
            "Découverte : trouver le but et commencer",
            "Apprentissage : suivre les prérequis et contrôles",
            "Recherche : retrouver une information ciblée",
            "Analyse experte : choix, limites et preuves",
            "Défauts prouvés, risques et améliorations proportionnées",
            "Verdict par critère, limites et droit de s'arrêter",
        ],
    },
    "redacteur-pedagogique": {
        "guide": [
            "Le problème",
            "Le mécanisme",
            "Un petit exemple expliqué",
            "Où commencer et action à essayer",
            "Signe de réussite et premier écart",
            "Diagnostic et retour arrière",
            "Rendu du document et des illustrations si exportés",
        ],
        "github_readme": [
            "Pitch et état réel", "Démarrage et installation conditionnelle",
            "Architecture, source et visuel", "Réalisations, limites et preuves",
            "Navigation et contribution",
        ],
        "notion_wiki": [
            "Accueil, objectif et état réel", "Comprendre et préparer les outils",
            "Pratiquer, suivre, ressources", "Navigation native et conservation",
            "Preuves et réception visuelle",
        ],
        "explanation": [
            "Idée principale",
            "Lien avec les acquis et vocabulaire utile",
            "Pourquoi ce choix",
            "Limites",
            "Exemple et prochaine action utile",
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
    revision = None
    for ancestor in (root, *root.parents):
        if ancestor == workspace:
            break
        stamp = ancestor / "context/source-revision.json"
        if stamp.is_file() and not stamp.is_symlink():
            revision = read_json(stamp)
            break
    extensions = {".md", ".txt", ".json", ".yaml", ".yml", ".tf", ".hcl", ".sh",
                  ".bash", ".py", ".ini", ".toml", ".conf", ".j2", ".service", ".sql"}
    paths = root.iterdir() if root == workspace else root.rglob("*")
    for path in sorted(paths):
        if scanned >= 200 or budget <= 0:
            break
        if not path.is_file() or (path.suffix.lower() not in extensions
                                  and path.name not in {"Dockerfile", "Containerfile"}):
            continue
        scanned += 1
        if path.stat().st_size > min(128_000, budget):
            continue
        budget -= path.stat().st_size
        raw = path.read_bytes()
        content = raw.decode("utf-8", errors="replace")
        for number, line in enumerate(content.splitlines(), 1):
            if any(word in line.lower() for word in words):
                hits.append(
                    {
                        "path": path.relative_to(workspace).as_posix(),
                        "line": number,
                        "snapshot_revision": revision,
                        "file_sha256": hashlib.sha256(raw).hexdigest(),
                        "text": line[:800],
                    }
                )
                if len(hits) == 4:
                    return {"hits": hits, "scanned": scanned, "bounded": True}
    return {"hits": hits, "scanned": scanned, "bounded": True}


def diagram(data: dict[str, Any]) -> dict[str, Any]:
    """Render native editable Draw.io cells and an inert preview from the same graph."""
    nodes, edges = data.get("nodes"), data.get("edges", [])
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= 8:
        raise ValueError("1 à 8 nœuds requis")
    if not isinstance(edges, list) or len(edges) > 12:
        raise ValueError("12 liens maximum")
    labels = nodes
    if any(not isinstance(label, str) or not label.strip() or len(label) > 60 for label in labels):
        raise ValueError("libellés courts requis")
    for edge in edges:
        if (not isinstance(edge, list) or len(edge) != 2
                or any(type(i) is not int or not 0 <= i < len(labels) for i in edge)):
            raise ValueError("liens [index source, index destination] requis")
    views = data.get("views", [])
    if not isinstance(views, list) or len(views) > 7 or any(
        not isinstance(view, dict) for view in views
    ):
        raise ValueError("jusqu'à 7 vues additionnelles Draw.io requises")
    document = ET.fromstring(multi_view_diagram(labels, edges, views))
    pages = document.findall("diagram")
    if "title" in data:
        title = data["title"]
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 60 or not title.isprintable():
            raise ValueError("titre de vue invalide")
        pages[0].set("name", title)
    layouts = []
    for page, view in zip(pages, [data, *views], strict=True):
        decorate_page(page, view)
        layouts.append(style_and_arrange(page, view))
    drawio = ET.tostring(document, encoding="unicode")
    inspect_diagram(drawio)
    exports = [(page.attrib["name"], export_page_svg(page))
               for page in ET.fromstring(drawio).findall("diagram")]
    return {
        "drawio": drawio, "views_generated": len(exports), "svg_views": exports,
        "compositions": layouts,
        "geometry_review": [inspect_page(page) for page in pages],
        "svg_view": "svg: vue principale uniquement; svg_views couvre toutes les vues",
        "svg": exports[0][1], "renderer": "drawio-xml", "svg_renderer": "clawfedora-svg/1",
        "scope": "export des formes du générateur; rendu dans Draw.io et support final à vérifier",
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


def _require_active_sandbox_scope(runtime: Path, scope: str) -> None:
    """Only the current worker task may authorize executable laboratory tools."""
    from clawfedora.project_control import progress

    state = progress(runtime)
    expected = "/".join([
        "projects", str(state.get("project_id", "")),
        str(state.get("task_id", "")), str(state.get("session_id", "")),
    ])
    if (
        state.get("active") is not True or state.get("phase") != "running"
        or state.get("role") != "ingenieur-devops"
        or not all(state.get(key) for key in ("project_id", "task_id", "session_id"))
        or scope != expected
    ):
        raise ValueError("Laboratoire réservé au snapshot de la tâche DevOps active")


def invoke(
    runtime: Path, role: str, workspace: Path, tool: str, data: dict[str, Any]
) -> dict[str, Any]:
    root = _workspace(runtime, role, workspace)
    if tool not in TOOL_ROLES or role not in TOOL_ROLES[tool]:
        raise ValueError("outil interdit pour ce rôle")
    if len(json.dumps(data).encode()) > 24000:
        raise ValueError("paramètres trop volumineux")
    if tool == "clawfedora_notion_inventory":
        from clawfedora.notion_premium_tools import inventory

        return inventory(root, data.get("scope"))
    if tool == "clawfedora_notion_studio_check":
        from clawfedora.notion_premium_tools import studio_check

        return studio_check(data.get("content"))
    if tool == "clawfedora_artifact":
        return produce(root, role, data)
    if tool == "clawfedora_search":
        return _search(root, data)
    if tool == "clawfedora_diagram":
        result = diagram(data)
        svg = result.pop("svg")
        drawio = result.pop("drawio")
        exports = result.pop("svg_views")
        result["receipt"] = receipt(root, tool, result, svg=svg, drawio=drawio)
        references = [{"title": exports[0][0], "reference": result["svg_reference"]}]
        for index, (title, content) in enumerate(exports[1:], 2):
            meta = {"drawio_sha256": result["drawio_sha256"], "page": index, "title": title}
            receipt(root, tool, meta, svg=content)
            references.append({"title": title, "reference": meta["svg_reference"]})
        result["views"] = references
        result["instruction"] = (
            "Sortie .drawio: drawio_reference; aperçu .svg: svg_reference, comme contenus JSON "
            "des chemins attendus. Utiliser views pour les SVG suivants."
        )
        return result
    if tool == "clawfedora_check":
        return check(data)
    if tool == "clawfedora_ci_report":
        if (data.get("format") == "trivy-image"
                and role not in {"ingenieur-securite", "auditeur-qualite"}):
            raise ValueError("rapport Trivy réservé à la sécurité et à l’audit")
        return summarize(data)
    if tool == "clawfedora_sandbox_validate":
        from clawfedora.devops_sandbox import validate_proposal

        scope, validator, files = data.get("scope"), data.get("validator"), data.get("files")
        if (
            not isinstance(scope, str) or not isinstance(validator, str)
            or not isinstance(files, dict)
            or any(not isinstance(k, str) or not isinstance(v, str) for k, v in files.items())
        ):
            raise ValueError("scope, validator et fichiers texte requis")
        _require_active_sandbox_scope(runtime, scope)
        return validate_proposal(runtime, root, scope, validator, files)
    if tool == "clawfedora_sandbox_iterate":
        from clawfedora.devops_iteration import iterate

        scope = data.get("scope")
        operation = data.get("operation")
        revision = data.get("expected_revision")
        validator = data.get("validator")
        validators = data.get("validators")
        files = data.get("files")
        if (not isinstance(scope, str) or not isinstance(operation, str)
                or not isinstance(revision, str) or
                (validator is not None and not isinstance(validator, str)) or
                (validators is not None and not isinstance(validators, list)) or
                (files is not None and
                 (not isinstance(files, dict) or
                  any(not isinstance(k, str) or not isinstance(v, str)
                      for k, v in files.items())))):
            raise ValueError("scope, opération, révision et fichiers texte requis")
        _require_active_sandbox_scope(runtime, scope)
        if validators is None:
            return iterate(runtime, root, scope, operation, revision, validator, files)
        return iterate(
            runtime, root, scope, operation, revision, validator, files, validators=validators,
        )
    if tool == "clawfedora_lab_request":
        from clawfedora.project_proofs import lab_request

        request = lab_request(data)
        request["receipt"] = receipt(root, tool, request)
        return request
    if tool == "clawfedora_doc_links":
        from clawfedora.document_links import check_links

        return check_links(root, data)
    if tool == "clawfedora_doc_review":
        content, kind = data.get("content"), data.get("kind")
        if not isinstance(content, str) or not isinstance(kind, str):
            raise ValueError("contenu et type documentaire texte requis")
        return inspect_document(content, kind, data.get("support", "markdown"))
    if tool == "clawfedora_impact":
        scope = data.get("scope")
        changed = data.get("changed_paths")
        if (not isinstance(scope, str) or not scope or Path(scope).is_absolute()
                or ".." in Path(scope).parts or not isinstance(changed, list)):
            raise ValueError("snapshot relatif et chemins modifiés requis")
        target = root / scope
        if not target.is_dir() or not target.resolve().is_relative_to(root.resolve()):
            raise ValueError("snapshot hors workspace")
        assert_no_symlinks(target, label="snapshot documentaire")
        return inspect_impact(target, changed)
    if tool == "clawfedora_tool_status":
        return {
            "available": available(),
            "role_tools": sorted(name for name, roles in TOOL_ROLES.items() if role in roles),
            "lint_formats": sorted(FORMATS.get(role, set())),
            "file_formats": formats(role),
            "document_exports": ["pdf", "docx", "odt", "txt"],
        }
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
        "instruction": "Adapter les rubriques au besoin; exemple expliqué avant une amorce. "
        "Ce plan n’est pas obligatoire pour une réponse courte.",
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
