"""Read-only CI provenance from official public forge APIs, never from model output.

No tokens, headers from chat, redirects, arbitrary hosts, source code execution,
secret-bearing log downloads or repository writes are accepted. Private repos
need a separate least-privilege connector and are deliberately unsupported here.
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.request
from datetime import UTC, datetime
from typing import Any, cast
from urllib.parse import quote

OWNER = re.compile(r"^[A-Za-z0-9_.-]+$")
SHA = re.compile(r"^[0-9a-f]{40}$")
MAX_BODY = 256 * 1024


class ProofRefused(ValueError):
    """The remote proof is missing, inconsistent or cannot be trusted."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: urllib.request.Request, fp: Any, code: int, msg: str,
        headers: Any, newurl: str
    ) -> None:
        return None


def _repo_parts(provider: str, repository: str) -> tuple[str, ...]:
    pieces = tuple(repository.split("/"))
    if (
        provider not in {"github", "gitlab"}
        or len(pieces) < 2
        or (provider == "github" and len(pieces) != 2)
        or any(not OWNER.fullmatch(part) or part in {".", ".."} for part in pieces)
    ):
        raise ProofRefused("Dépôt public GitHub owner/name ou GitLab group/project requis")
    return pieces


def _json_get(url: str) -> Any:
    """Hardcoded API host only, bounded JSON response; redirect refused."""
    if not url.startswith((
        "https://api.github.com/repos/", "https://gitlab.com/api/v4/projects/"
    )):
        raise ProofRefused("Destination externe non autorisée")
    request = urllib.request.Request(
        url, headers={
            "Accept": "application/vnd.github+json, application/json",
            "User-Agent": "clawfedora-ci-evidence/1",
        },
        method="GET",
    )
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=12) as response:
            if response.status != 200:
                raise ProofRefused("API officielle indisponible")
            content = response.read(MAX_BODY + 1)
    except (OSError, urllib.error.URLError) as exc:
        raise ProofRefused(
            "Preuve inaccessible via l'API publique ; aucune authentification envoyée"
        ) from exc
    if len(content) > MAX_BODY:
        raise ProofRefused("Réponse officielle dépassant la limite de taille")
    try:
        return json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProofRefused("JSON fournisseur invalide") from exc


def _matching(payload: object, run_id: int, commit: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ProofRefused("Réponse fournisseur non structurée")
    data = cast(dict[str, Any], payload)
    if type(data.get("id")) is not int or data["id"] != run_id:
        raise ProofRefused("Identifiant de pipeline différent de celui demandé")
    sha = data.get("head_sha") if "head_sha" in data else data.get("sha")
    if not isinstance(sha, str) or sha.lower() != commit:
        raise ProofRefused("SHA distant différent de celui attendu")
    return data


def verify_public_run(
    provider: str, repository: str, run_id: int, commit: str
) -> dict[str, Any]:
    """One remote observation. A successful run is not proof of service deployment."""
    parts = _repo_parts(provider, repository)
    if type(run_id) is not int or run_id < 1 or not SHA.fullmatch(commit):
        raise ProofRefused("ID positif et commit SHA-1 complet (40 hex) obligatoires")

    if provider == "github":
        api = "https://api.github.com/repos/" + "/".join(quote(p) for p in parts)
        payload = _matching(_json_get(f"{api}/actions/runs/{run_id}"), run_id, commit)
        status, conclusion = payload.get("status"), payload.get("conclusion")
        if status not in {"queued", "in_progress", "completed", "waiting", "pending"}:
            raise ProofRefused("Statut GitHub Actions inconnu")
        if status != "completed":
            verdict = "PENDING"
        elif conclusion == "success":
            verdict = "VERIFIED_RUN_SUCCESS"
        elif conclusion in {"failure", "cancelled", "timed_out", "action_required", "neutral",
                            "skipped", "startup_failure"}:
            verdict = "RUN_NOT_SUCCESSFUL"
        else:
            raise ProofRefused("Conclusion GitHub Actions non reconnue")
        url = "https://github.com/" + "/".join(quote(p) for p in parts)
        url += f"/actions/runs/{run_id}"
    else:
        api = (
            "https://gitlab.com/api/v4/projects/"
            + quote("/".join(parts), safe="")
            + f"/pipelines/{run_id}"
        )
        payload = _matching(_json_get(api), run_id, commit)
        status = payload.get("status")
        if status in {"created", "waiting_for_resource", "preparing", "pending", "running",
                      "scheduled", "manual"}:
            verdict = "PENDING"
        elif status == "success":
            verdict = "VERIFIED_RUN_SUCCESS"
        elif status in {"failed", "canceled", "skipped"}:
            verdict = "RUN_NOT_SUCCESSFUL"
        else:
            raise ProofRefused("Statut GitLab CI inconnu")
        url = "https://gitlab.com/" + "/".join(quote(p) for p in parts)
        url += f"/-/pipelines/{run_id}"

    return {
        "provider": provider,
        "repository": repository,
        "run_id": run_id,
        "commit": commit,
        "verdict": verdict,
        "observed_at_utc": datetime.now(UTC).isoformat(),
        "official_url": url,
        "remote_status": status,
        "provenance": "OFFICIAL_PUBLIC_FORGE_API",
        "scope": "pipeline_result_only",
        "warning": (
            "Résultat du pipeline officiel associé au SHA ; aucune preuve directe de "
            "fonctionnement du service, d'authenticité des artefacts, de déploiement, "
            "de rollback ni de compétence métier."
        ),
    }


def _public_jobs(
    provider: str, repository: str, run_id: int, commit: str,
) -> dict[str, Any]:
    """Bounded, public job metadata, never logs/artifacts or credentials.

    Verify the parent pipeline identity *first*. If pagination may truncate a
    report, refuse the detail instead of implying every job was inspected.
    """
    parts = _repo_parts(provider, repository)
    if provider == "github":
        api = "https://api.github.com/repos/" + "/".join(quote(p) for p in parts)
        data = _json_get(f"{api}/actions/runs/{run_id}/jobs?per_page=100")
        if not isinstance(data, dict):
            raise ProofRefused("Liste des jobs GitHub mal formée")
        raw, count = data.get("jobs"), data.get("total_count")
        if (
            not isinstance(raw, list) or type(count) is not int
            or not 0 <= count < 100 or len(raw) != count
        ):
            raise ProofRefused("Liste de jobs GitHub incomplète ou paginée")
    else:
        api = "https://gitlab.com/api/v4/projects/" + quote("/".join(parts), safe="")
        raw = _json_get(f"{api}/pipelines/{run_id}/jobs?per_page=100")
        if not isinstance(raw, list) or len(raw) >= 100:
            raise ProofRefused("Liste de jobs GitLab incomplète ou paginée")
    rows: list[dict[str, Any]] = []
    known = {
        "queued", "in_progress", "completed", "waiting", "pending",
        "success", "failed", "canceled", "cancelled", "skipped",
        "running", "created", "manual", "scheduled", "preparing",
        "waiting_for_resource",
    }
    for item in raw:
        if not isinstance(item, dict):
            raise ProofRefused("Job fournisseur non structuré")
        identifier, name, status = item.get("id"), item.get("name"), item.get("status")
        if (
            type(identifier) is not int or identifier < 1
            or not isinstance(name, str) or not 0 < len(name) <= 160
            or not isinstance(status, str) or status not in known
        ):
            raise ProofRefused("Identité ou statut de job non vérifiables")
        if provider == "github":
            if item.get("run_id") != run_id:
                raise ProofRefused("Job GitHub lié à un autre run")
            conclusion = item.get("conclusion")
            if conclusion is not None and conclusion not in {
                "success", "failure", "cancelled", "timed_out", "action_required",
                "neutral", "skipped", "startup_failure",
            }:
                raise ProofRefused("Conclusion de job GitHub inconnue")
        else:
            parent = item.get("pipeline")
            if not isinstance(parent, dict) or parent.get("id") != run_id:
                raise ProofRefused("Job GitLab lié à un autre pipeline")
            conclusion = None
        rows.append({
            "id": identifier, "name": name, "status": status, "conclusion": conclusion,
        })
    rows.sort(key=lambda item: item["id"])
    if len({row["id"] for row in rows}) != len(rows):
        raise ProofRefused("Identifiants de jobs dupliqués")
    return {
        "jobs_scope": "public_job_metadata_only",
        "jobs_count": len(rows),
        "jobs": rows,
        "jobs_warning": (
            "Métadonnées des jobs liées au pipeline et à son SHA, sans "
            "inspection des journaux, étapes, fichiers ou déploiements."
        ),
    }


def verify_public_run_with_jobs(
    provider: str, repository: str, run_id: int, commit: str,
) -> dict[str, Any]:
    """Optional detailed metadata; never weaken the default run-only proof."""
    report = verify_public_run(provider, repository, run_id, commit)
    report.update(_public_jobs(provider, repository, run_id, commit))
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Vérifier une CI publique sur son commit")
    parser.add_argument("--provider", choices=("github", "gitlab"), required=True)
    parser.add_argument("--repo", required=True, help="owner/name ou group/subgroup/name")
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--commit", required=True, help="SHA complet à 40 caractères")
    parser.add_argument("--jobs", action="store_true", help="Inclure les jobs publics (sans logs)")
    args = parser.parse_args(argv)
    try:
        proof = verify_public_run_with_jobs if args.jobs else verify_public_run
        report = proof(args.provider, args.repo, args.run_id, args.commit)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["verdict"] == "VERIFIED_RUN_SUCCESS" else 1
    except ProofRefused as exc:
        print(json.dumps({"verdict": "REFUSED", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
