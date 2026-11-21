"""Append-only operator evidence for long-running InfraOps milestones.

This is *not* the audited multi-agent task receipt mechanism in project_proofs.
No model can certify human work or execute commands. CI metadata is checked
through the official public API; an authenticated CI result proves only its run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
import uuid
from pathlib import Path
from typing import Any

from clawfedora import github_refresh, github_pr, project_roadmap, source_connectors
from clawfedora.ci_evidence import verify_public_run
from clawfedora.core_config import resolve_runtime_root
from clawfedora.project_common import (
    assert_no_symlinks,
    now,
    project_path,
    read_json,
    sha256_file,
    validate_task_id,
    write_json,
)
from clawfedora.project_intake import _SECRET_PATTERNS, validate_input_integrity
from clawfedora.project_worker import worker_lock

FOLDER = "context/milestone-evidence"
MAX_ENTRIES = 400
MAX_LOG = 32_768
KINDS = {"operator", "simulation", "public-ci"}
OUTCOMES = {"PASS", "FAIL", "UNKNOWN"}
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
TARGET = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}\Z")


def _hash(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _safe_text(value: str, *, label: str, limit: int, optional: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label}: texte requis")
    result = value.strip()
    if ((not optional and not result) or len(result) > limit
            or any(ord(char) < 32 and char not in "\n\t" for char in result)):
        raise ValueError(f"{label}: texte invalide ou trop long")
    if any(rule.search(result) for rule in (*_SECRET_PATTERNS, *github_pr.SUSPECT_CONTENT)):
        raise ValueError(f"{label}: secret potentiel détecté")
    return result


def _artifact(path: Path | None) -> tuple[bytes, str]:
    if path is None:
        return b"", ""
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_LOG:
        raise ValueError("sortie technique absente, liée ou supérieure à 32 Kio")
    content = path.read_bytes()
    if b"\x00" in content:
        raise ValueError("sortie binaire interdite")
    try:
        output = content.decode("utf-8")
    except UnicodeError as exc:
        raise ValueError("sortie non UTF-8") from exc
    _safe_text(output, label="sortie technique", limit=MAX_LOG)
    return content, hashlib.sha256(content).hexdigest()


def _current(project: Path, repository: str) -> str:
    initial, baseline = github_refresh._initial(project, repository)
    registry = github_refresh._read_registry(project, repository, baseline)
    revisions = registry["revisions"]
    if not revisions:
        if not initial.is_dir():
            raise ValueError("snapshot GitHub initial absent")
        return baseline
    commit = str(revisions[-1]["commit"])
    github_refresh._snapshot(project, repository, commit)
    return commit


def _criterion(project: Path, task_id: str | None, number: int | None) -> dict[str, Any] | None:
    if (task_id is None) != (number is None):
        raise ValueError("--task-id et --criterion doivent être fournis ensemble")
    if task_id is None:
        return None
    task_id = validate_task_id(task_id)
    path = project / "context/project_plan.json"
    if not path.is_file():
        raise ValueError("plan des tâches absent")
    plan = read_json(path)
    task = next((t for t in plan.get("tasks", []) if t.get("id") == task_id), None)
    if not isinstance(task, dict):
        raise ValueError("tâche de rattachement inconnue")
    criteria = task.get("acceptance_criteria")
    if (not isinstance(criteria, list) or type(number) is not int
            or not 1 <= number <= len(criteria) or not isinstance(criteria[number - 1], str)):
        raise ValueError("critère de rattachement inconnu")
    return {
        "task_id": task_id,
        "number": number,
        "criterion_sha256": hashlib.sha256(criteria[number - 1].encode()).hexdigest(),
        "plan_sha256": sha256_file(path),
        "binding": "REFERENCE_ONLY_NOT_AUDITED",
    }


def _milestone(project: Path, milestone_id: str) -> None:
    milestones = project_roadmap.load(project)["milestones"]
    if milestone_id not in {entry["id"] for entry in milestones}:
        raise ValueError("jalon absent de la feuille de route")


def _root(project: Path) -> Path:
    root = project / FOLDER
    assert_no_symlinks(root, label="registre des preuves de jalons")
    return root


def _count(root: Path) -> int:
    if not root.exists():
        return 0
    result = 0
    for milestone in root.iterdir():
        if not milestone.is_dir():
            raise ValueError("registre des preuves non régulier")
        result += sum(1 for item in milestone.iterdir() if item.is_dir()
                      and re.fullmatch(r"[0-9a-f]{32}", item.name))
    return result


def _prepare(
    project: Path, *, milestone_id: str, repository: str, commit: str,
    environment: str, environment_sha256: str | None, kind: str,
    procedure: str, expected: str, observed: str, outcome: str,
    output_file: Path | None, run_id: int | None,
    task_id: str | None, criterion: int | None,
) -> tuple[dict[str, Any], bytes]:
    milestone_id = validate_task_id(milestone_id)
    _milestone(project, milestone_id)
    repository = source_connectors._safe_repo(repository)
    commit = source_connectors._safe_sha(commit)
    if _current(project, repository) != commit:
        raise ValueError("SHA GitHub périmé : actualiser le snapshot avant la preuve")
    if not isinstance(environment, str) or not TARGET.fullmatch(environment):
        raise ValueError("identifiant d'environnement invalide")
    if environment_sha256 is not None and not HEX64.fullmatch(environment_sha256):
        raise ValueError("empreinte d'environnement SHA-256 invalide")
    if kind not in KINDS or outcome not in OUTCOMES:
        raise ValueError("type ou résultat de preuve inconnu")
    if kind == "public-ci":
        if environment != "ci-github" or type(run_id) is not int or run_id < 1:
            raise ValueError("CI publique : cible ci-github et run-id positif requis")
        if outcome != "UNKNOWN" or output_file is not None:
            raise ValueError("résultat CI uniquement fourni par l'API officielle")
    elif run_id is not None:
        raise ValueError("run-id réservé à la preuve CI publique")

    proc = _safe_text(procedure, label="procédure", limit=600)
    wanted = _safe_text(expected, label="résultat attendu", limit=900)
    observed_text = _safe_text(
        observed, label="observation", limit=1800, optional=(kind == "public-ci"),
    )
    artifact, artifact_hash = _artifact(output_file)
    linked_criterion = _criterion(project, task_id, criterion)
    external: dict[str, Any] | None = None
    verification = "NOT_VERIFIED"
    if kind == "public-ci":
        external = verify_public_run("github", repository, run_id, commit)
        if (external.get("repository") != repository or external.get("commit") != commit
                or external.get("run_id") != run_id):
            raise ValueError("réponse CI divergente")
        if external["verdict"] == "VERIFIED_RUN_SUCCESS":
            verification = "CI_RUN_SUCCESS_ONLY"
    payload = {
        "schema_version": 1, "project_id": project.name,
        "milestone_id": milestone_id, "repository": repository,
        "commit": commit, "environment": environment,
        "environment_sha256": environment_sha256,
        "kind": kind, "procedure": proc, "expected": wanted,
        "observed": observed_text, "operator_outcome": outcome,
        "output_sha256": artifact_hash, "criterion": linked_criterion,
        "ci_report": external, "verification": verification,
        "milestone_verification": "NOT_VERIFIED",
    }
    return payload, artifact


def capture(
    runtime: Path, project_id: str, *, milestone_id: str,
    repository: str, commit: str, environment: str,
    environment_sha256: str | None = None, kind: str = "operator",
    procedure: str, expected: str, observed: str = "",
    outcome: str = "UNKNOWN", output_file: Path | None = None,
    run_id: int | None = None, task_id: str | None = None,
    criterion: int | None = None, apply: bool = False,
    approve: str = "",
) -> dict[str, Any]:
    """Explicit human capture with SHA-bound preview; no remote writes."""
    if apply and not HEX64.fullmatch(approve):
        raise ValueError("empreinte de prévisualisation SHA-256 requise")
    project = project_path(runtime, project_id)
    # Read before the lock for preview. Apply rechecks all sources under the lock.
    if not apply:
        assert_no_symlinks(project, label="projet")
        failures = validate_input_integrity(project)
        if failures:
            raise ValueError("sources initiales altérées: " + "; ".join(failures))
        record, artifact = _prepare(
            project, milestone_id=milestone_id, repository=repository, commit=commit,
            environment=environment, environment_sha256=environment_sha256,
            kind=kind, procedure=procedure, expected=expected, observed=observed,
            outcome=outcome, output_file=output_file, run_id=run_id,
            task_id=task_id, criterion=criterion,
        )
        return _preview(record, artifact)
    with worker_lock(runtime, allow_gaming=True):
        assert_no_symlinks(project, label="projet")
        failures = validate_input_integrity(project)
        if failures:
            raise ValueError("sources initiales altérées: " + "; ".join(failures))
        record, artifact = _prepare(
            project, milestone_id=milestone_id, repository=repository, commit=commit,
            environment=environment, environment_sha256=environment_sha256,
            kind=kind, procedure=procedure, expected=expected, observed=observed,
            outcome=outcome, output_file=output_file, run_id=run_id,
            task_id=task_id, criterion=criterion,
        )
        proposed = _preview(record, artifact)
        if proposed["approval_sha256"] != approve:
            raise ValueError("prévisualisation périmée : relire et approuver de nouveau")
        root = _root(project)
        if _count(root) >= MAX_ENTRIES:
            raise ValueError("limite des preuves atteinte : archiver sous contrôle humain")
        milestone_root = root / record["milestone_id"]
        milestone_root.mkdir(parents=True, exist_ok=True)
        identifier = uuid.uuid4().hex
        destination = milestone_root / identifier
        with tempfile.TemporaryDirectory(prefix=".staging-", dir=milestone_root) as tmp:
            stage = Path(tmp)
            receipt = {
                **record, "id": identifier, "captured_at": now(),
                "approval_sha256": proposed["approval_sha256"],
                "origin": "HUMAN_EXPLICIT_CLI_OR_APPROVED_LOCAL_COMMAND",
                "integrity_notice": "empreinte détecte altération locale, sans signature externe",
            }
            receipt["record_sha256"] = _hash(receipt)
            write_json(stage / "record.json", receipt)
            if artifact:
                (stage / "output.txt").write_bytes(artifact)
            stage.rename(destination)
        return {
            "status": "RECORDED", "id": identifier,
            "milestone_id": record["milestone_id"],
            "verification": record["verification"],
            "milestone_verification": "NOT_VERIFIED",
            "record_path": (destination / "record.json").relative_to(project).as_posix(),
        }


def _preview(record: dict[str, Any], artifact: bytes) -> dict[str, Any]:
    return {
        "status": "PREVIEW", "project_id": record["project_id"],
        "milestone_id": record["milestone_id"],
        "repository": record["repository"], "commit": record["commit"],
        "environment": record["environment"], "kind": record["kind"],
        "operator_outcome": record["operator_outcome"],
        "ci_verdict": (record["ci_report"] or {}).get("verdict"),
        "output_bytes": len(artifact), "output_sha256": record["output_sha256"],
        "criterion": record["criterion"],
        "verification": record["verification"],
        "milestone_verification": "NOT_VERIFIED",
        "approval_sha256": _hash(record),
        "remote_writes": False,
        "warning": "enregistrer une preuve ne valide ni le jalon ni une compétence",
    }


def _checked(project: Path, directory: Path) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{32}", directory.name):
        raise ValueError("identifiant de preuve invalide")
    contents = {p.name for p in directory.iterdir()}
    if contents not in ({"record.json"}, {"record.json", "output.txt"}):
        raise ValueError("fichiers de preuve inattendus")
    record = read_json(directory / "record.json")
    digest = record.pop("record_sha256", None)
    if digest != _hash(record):
        raise ValueError("preuve modifiée ou corrompue")
    if record.get("id") != directory.name or record.get("project_id") != project.name:
        raise ValueError("preuve liée à une autre identité")
    if record.get("milestone_id") != directory.parent.name:
        raise ValueError("preuve liée à un autre jalon")
    artifact = directory / "output.txt"
    actual = sha256_file(artifact) if artifact.is_file() else ""
    if actual != record.get("output_sha256"):
        raise ValueError("sortie de preuve modifiée ou absente")
    record["record_sha256"] = digest
    return record


def report(
    project: Path, *,
    environment: str | None = None, environment_sha256: str | None = None,
) -> dict[str, Any]:
    """Bounded, read-only metadata. Never expose commands or raw logs to the UI."""
    if environment is not None and not TARGET.fullmatch(environment):
        raise ValueError("environnement consulté invalide")
    if environment_sha256 is not None and not HEX64.fullmatch(environment_sha256):
        raise ValueError("SHA-256 environnement consulté invalide")
    assert_no_symlinks(project, label="projet")
    roadmap = project_roadmap.load(project)
    root = _root(project)
    milestones: list[dict[str, Any]] = []
    count = 0
    known: dict[str, str] = {}
    if root.exists():
        for milestone in root.iterdir():
            if not milestone.is_dir() or milestone.name not in {
                entry["id"] for entry in roadmap["milestones"]
            }:
                raise ValueError("preuves rattachées à un jalon inconnu")
            for directory in milestone.iterdir():
                if directory.name.startswith(".staging-"):
                    continue
                if not directory.is_dir():
                    raise ValueError("preuve non régulière")
                count += 1
                if count > MAX_ENTRIES:
                    raise ValueError("registre de preuves au-delà de la limite")
                record = _checked(project, directory)
                repo, commit = record["repository"], record["commit"]
                if repo not in known:
                    known[repo] = _current(project, repo)
                reasons = []
                if commit != known[repo]:
                    reasons.append("GIT_REVISION_CHANGED")
                if environment is not None and record["environment"] != environment:
                    reasons.append("TARGET_DIFFERENT")
                if (environment_sha256 is not None
                        and record["environment_sha256"] != environment_sha256):
                    reasons.append("ENVIRONMENT_REVISION_CHANGED")
                linked = record.get("criterion")
                if isinstance(linked, dict):
                    path = project / "context/project_plan.json"
                    if not path.is_file() or linked.get("plan_sha256") != sha256_file(path):
                        reasons.append("TASK_PLAN_CHANGED")
                milestones.append({
                    "id": record["id"], "milestone_id": record["milestone_id"],
                    "environment": record["environment"],
                    "environment_sha256": record["environment_sha256"],
                    "repository": repo, "commit": commit,
                    "kind": record["kind"], "operator_outcome": record["operator_outcome"],
                    "verification": record["verification"] if not reasons else "REQUALIFY",
                    "milestone_verification": "NOT_VERIFIED",
                    "captured_at": record["captured_at"],
                    "requalify_reasons": reasons,
                    "environment_check": (
                        "UNPINNED" if record["environment_sha256"] is None else
                        "NOT_COMPARED" if environment_sha256 is None else
                        "MATCH" if record["environment_sha256"] == environment_sha256
                        else "DIFFERENT"
                    ),
                    "criterion": linked,
                    "record_sha256": record["record_sha256"],
                })
    milestones.sort(key=lambda row: (row["captured_at"], row["id"]), reverse=True)
    by_milestone: list[dict[str, Any]] = []
    for row in roadmap["milestones"]:
        linked = [p for p in milestones if p["milestone_id"] == row["id"]]
        by_milestone.append({
            "milestone_id": row["id"], "title": row["title"],
            "declared_state": row["state"], "verification": "NOT_VERIFIED",
            "count": len(linked), "to_requalify": sum(bool(p["requalify_reasons"]) for p in linked),
            "recorded": linked[:20],
        })
    return {
        "schema_version": 1, "project_id": project.name, "total": count,
        "milestones": by_milestone,
        "scope": "historique de preuves non équivalent à certification ou compétence",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clawfedora-milestone-evidence",
        description="Journal append-only des preuves de jalons, sans validation automatique",
    )
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--project-id", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    capture_cmd = commands.add_parser("capture")
    for flag in ("milestone-id", "repo", "commit", "environment", "procedure", "expected"):
        capture_cmd.add_argument("--" + flag, required=True)
    capture_cmd.add_argument("--environment-sha256")
    capture_cmd.add_argument("--kind", choices=sorted(KINDS), default="operator")
    capture_cmd.add_argument("--observed", default="")
    capture_cmd.add_argument("--result", choices=sorted(OUTCOMES), default="UNKNOWN")
    capture_cmd.add_argument("--output-file", type=Path)
    capture_cmd.add_argument("--run-id", type=int)
    capture_cmd.add_argument("--task-id")
    capture_cmd.add_argument("--criterion", type=int)
    capture_cmd.add_argument("--approve", default="")
    capture_cmd.add_argument("--apply", action="store_true")
    view = commands.add_parser("report")
    view.add_argument("--environment")
    view.add_argument("--environment-sha256")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        runtime = resolve_runtime_root(str(args.runtime_root) if args.runtime_root else None)
        project = project_path(runtime, args.project_id)
        if args.command == "report":
            result = report(
                project, environment=args.environment,
                environment_sha256=args.environment_sha256,
            )
        else:
            result = capture(
                runtime, args.project_id,
                milestone_id=args.milestone_id, repository=args.repo,
                commit=args.commit, environment=args.environment,
                environment_sha256=args.environment_sha256,
                kind=args.kind, procedure=args.procedure,
                expected=args.expected, observed=args.observed,
                outcome=args.result, output_file=args.output_file,
                run_id=args.run_id, task_id=args.task_id,
                criterion=args.criterion, approve=args.approve,
                apply=args.apply,
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, RuntimeError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
