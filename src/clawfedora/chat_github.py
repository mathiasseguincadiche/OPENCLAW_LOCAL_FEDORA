"""Only explicit user-typed GitHub chat commands can reach GitHub.

The model never approves a remote write. A project's approved deliverables
can be proposed as a draft PR using a single-use exact manifest confirmation.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Any

from clawfedora.github_pr import make_plan, publish_draft
from clawfedora.github_quality import audit_repository
from clawfedora.github_remote import create_plan, create_repository
from clawfedora.project_common import read_json, write_json
from clawfedora.project_worker import worker_lock

SHA256 = re.compile(r"[0-9a-f]{64}\Z")
STAGING = re.compile(r"deliverables/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*\Z")

HELP = """GitHub : commandes locales du pont (jamais interprétées par le modèle).

!github aide : afficher les commandes.
!github audit [livrables|GitHub-identifiant] : audit documentaire local sans réseau.
!github depot MonProjet : préparer un dépôt privé, sans réseau.
!github creer MonProjet EMPREINTE : créer le dépôt privé approuvé.
!github pr owner/repo SHA40 atelier/branche deliverables/tache : préparer une PR.
!github publier owner/repo EMPREINTE : autoriser la PR brouillon préparée.

Les écritures exigent GITHUB_TOKEN dans l'environnement local du pont
et un projet sélectionné. Elles ne fusionnent aucune PR. La publication
des livrables exige un projet marqué COMPLETE et une revue humaine.
Les règles de protection se gèrent séparément via clawfedora-github-remote.
"""


def _project(runtime: Path, current: str | None) -> Path:
    from clawfedora.chat_projects import open_project

    project = open_project(runtime, current) if current else None
    if project is None:
        raise ValueError("sélectionner un projet : !projets, puis !projet identifiant")
    return project


def _stage(project: Path, label: str) -> Path:
    if STAGING.fullmatch(label) is None or ".." in label or label.endswith("."):
        raise ValueError("dossier deliverables/tache attendu")
    folder = project / label
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError("dossier de livrables absent ou lié")
    if not folder.resolve().is_relative_to((project / "deliverables").resolve()):
        raise ValueError("dossier hors du projet")
    return folder


def _snapshot(project: Path, name: str) -> Path:
    root = project / "intake"
    if root.is_symlink():
        raise ValueError("racine des sources liée interdite")
    found = sorted(
        path for path in root.glob("GitHub-*")
        if path.is_dir() and not path.is_symlink()
        and (path / ".source-provenance.json").is_file()
    )
    if name:
        found = [path for path in found if path.name == name]
    if len(found) != 1:
        raise ValueError("indiquer un snapshot GitHub unique : " +
                         ", ".join(path.name for path in found[:8]))
    return found[0]


def _record(project: Path, kind: str, payload: dict[str, Any], state: str) -> None:
    target = project / "context" / f"github-{kind}-pending.json"
    if target.is_symlink():
        raise ValueError("plan GitHub lié interdit")
    write_json(target, {**payload, "state": state})
    target.chmod(0o600)


def _pending(project: Path, kind: str) -> dict[str, Any]:
    target = project / "context" / f"github-{kind}-pending.json"
    if target.is_symlink() or not target.is_file():
        raise ValueError("aucun plan GitHub préparé")
    record = read_json(target)
    if record.get("state") != "PREVIEWED":
        raise ValueError("plan déjà tenté : vérifier GitHub avant toute relance")
    return record


def run(runtime: Path, current: str | None, arguments: str, *, local: bool) -> str:
    try:
        words = shlex.split(arguments)
    except ValueError:
        return "GitHub : syntaxe invalide. Utiliser !github aide."
    if not words or words[0] == "aide":
        return HELP
    if len(words) > 9:
        return "GitHub : trop d'arguments."
    try:
        project = _project(runtime, current)
        action = words[0]
        if action == "audit" and len(words) <= 2:
            label = words[1] if len(words) == 2 else ""
            folder = (project / "deliverables") if label == "livrables" else _snapshot(
                project, label,
            )
            report = audit_repository(folder)
            links = report["links"]
            graphics = report["graphics"]
            documents = [
                item["id"] for item in report["structure"] if item["state"] == "FOUND"
            ]
            return (
                "**Audit local : aucune publication.**\n\n"
                f"- Dossier : {folder.relative_to(project)}\n"
                f"- Documents présents : {', '.join(documents) or 'aucun'}\n"
                f"- Liens manquants : {links['missing_total']} ; "
                f"non vérifiables : {links['not_checked_total']}\n"
                f"- SVG contrôlés statiquement : {graphics['svg_checked']}\n"
                "- La CI, Fedora et le rendu GitHub ne sont pas vérifiés."
            )
        if action == "depot" and len(words) == 2:
            plan = create_plan(words[1])
            with worker_lock(runtime):
                _record(project, "repo", plan, "PREVIEWED")
            return (
                f"**Dépôt privé prévu : {plan['name']}** ; aucun accès réseau.\n"
                f"Empreinte : {plan['manifest_sha256']}\n"
                f"Pour approuver : !github creer {plan['name']} "
                f"{plan['manifest_sha256']}"
            )
        if action == "creer" and len(words) == 3:
            if not local:
                raise ValueError("choisir un rôle local pour publier sur GitHub")
            name, digest = words[1:]
            if SHA256.fullmatch(digest) is None:
                raise ValueError("empreinte SHA-256 requise")
            with worker_lock(runtime):
                plan = _pending(project, "repo")
                if plan["name"] != name or plan["manifest_sha256"] != digest:
                    raise ValueError("approbation différente du plan")
                _record(project, "repo", plan, "ATTEMPTED")
                result = create_repository(
                    name, approve_name=name, approve_manifest=digest,
                )
                _record(project, "repo", {**plan, "url": result["url"]}, "CREATED")
            return f"Dépôt privé créé : {result['url']}. Contrôler ses protections."
        if action == "pr" and len(words) == 5:
            repo, sha, branch, label = words[1:]
            if read_json(project / "project.json").get("status") != "COMPLETE":
                raise ValueError("projet non terminé : terminer d'abord l'audit et la livraison")
            stage = _stage(project, label)
            with worker_lock(runtime):
                plan = make_plan(
                    repo=repo, base="main", base_sha=sha, branch=branch,
                    changes=stage, allow_workflows=False,
                )
                _record(project, "pr", {
                    "repository": repo, "base_sha": sha, "branch": branch,
                    "stage": label, "manifest_sha256": plan["manifest_sha256"],
                }, "PREVIEWED")
            return (
                f"**PR brouillon prévue :** {len(plan['files'])} fichiers vers {repo}.\n"
                f"Empreinte : {plan['manifest_sha256']}\n"
                "Relire les fichiers et leurs preuves. Pour approuver : "
                f"!github publier {repo} {plan['manifest_sha256']}"
            )
        if action == "publier" and len(words) == 3:
            if not local:
                raise ValueError("choisir un rôle local pour publier sur GitHub")
            repo, digest = words[1:]
            if SHA256.fullmatch(digest) is None:
                raise ValueError("empreinte SHA-256 requise")
            with worker_lock(runtime):
                plan = _pending(project, "pr")
                if plan["repository"] != repo or plan["manifest_sha256"] != digest:
                    raise ValueError("approbation différente du plan")
                if read_json(project / "project.json").get("status") != "COMPLETE":
                    raise ValueError("projet non terminé")
                stage = _stage(project, plan["stage"])
                _record(project, "pr", plan, "ATTEMPTED")
                result = publish_draft(
                    repo=repo, base="main", base_sha=plan["base_sha"],
                    branch=plan["branch"], changes=stage,
                    title="Livrables relus de l'atelier OpenClaw",
                    body=(
                        "Proposition relue localement, à vérifier dans GitHub. "
                        "Aucune réussite Fedora, sécurité ou CI n'est présumée. "
                        "Examiner le diff, les preuves et les risques avant toute fusion."
                    ),
                    approve_repo=repo, approve_manifest=digest,
                )
                _record(project, "pr", {**plan, "url": result["url"]}, "CREATED")
            return f"PR brouillon créée : {result['url']}. Aucune fusion automatique."
        return HELP
    except (OSError, ValueError, KeyError) as exc:
        return (
            f"GitHub : opération refusée ou incomplète ({exc}). "
            "En cas de tentative de publication, vérifier GitHub avant de recommencer."
        )
