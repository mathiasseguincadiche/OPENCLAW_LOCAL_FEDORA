"""Bind approved audit criteria to current task outputs and operator-owned receipts."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any

from clawfedora import devops_lab
from clawfedora.ci_evidence import verify_public_run
from clawfedora.ci_private_evidence import verify_private_run
from clawfedora.project_common import (
    assert_no_symlinks,
    now,
    read_json,
    safe_output,
    sha256_file,
    validate_task_id,
    write_json,
)


def requirement(criterion: str, outputs: list[str]) -> list[str]:
    if not criterion.startswith("[preuve"):
        return []
    header, end, description = criterion.partition("]")
    parts = header.split()[1:]
    if header.startswith("[preuve ") and end and description.strip():
        match parts:
            case ["ci", ("github" | "gitlab"), repo, commit] if re.fullmatch(
                r"[\w.-]+(?:/[\w.-]+)+", repo
            ) and re.fullmatch("[0-9a-f]{40}", commit):
                return parts
            case ["lab", tool, *paths] if (
                tool in devops_lab.TOOLS
                and paths
                and len(paths) == len(set(paths))
                and all(p in outputs for p in paths)
            ):
                return parts
            case ["lint", tool, target] if (
                tool in {"yamllint", "shellcheck", "pymarkdownlnt", "gitleaks"} and target in outputs
            ):
                return parts
            case ["observation", environment, target] if (
                re.fullmatch(r"[\w.-]{1,80}", environment) and target in outputs
            ):
                return parts
    raise ValueError("contrat [preuve] invalide: vérifier contrôle, cible et critère")


def lab_request(data: dict[str, Any]) -> dict[str, Any]:
    paths, tool, expected = data.get("files"), data.get("validator"), data.get("expected")
    if (
        not isinstance(paths, list)
        or not 1 <= len(paths) <= 20
        or not isinstance(expected, str)
        or not 1 <= len(expected.strip()) <= 500
        or any(
            not isinstance(p, str)
            or not re.fullmatch(r"[\w./-]+", p)
            or Path(p).is_absolute()
            or ".." in Path(p).parts
            or len(Path(p).parts) < 3
            for p in paths
        )
    ):
        raise ValueError("fichiers de tâche et résultat attendu requis")
    criterion = f"[preuve lab {tool} {' '.join(paths)}] {expected.strip()}"
    requirement(criterion, paths)
    return {"criterion": criterion, "files": paths, "status": "PROPOSED", "executed": False}


def _epoch(project: Path, task_id: str) -> int:
    ledger = project / "context/revisions.json"
    if not ledger.exists():
        return 0
    return max(
        (
            int(r["revision"])
            for r in read_json(ledger)["revisions"]
            if task_id in r["affected_tasks"]
        ),
        default=0,
    )


def _binding(project: Path, task: dict[str, Any], number: int) -> dict[str, Any]:
    task_id = validate_task_id(task["id"])
    if not 1 <= number <= len(task["acceptance_criteria"]):
        raise ValueError("numéro de critère hors du plan")
    text = task["acceptance_criteria"][number - 1]
    spec = requirement(text, task["expected_outputs"])
    targets = [] if not spec or spec[0] == "ci" else spec[2:]
    return {
        "project": project.name,
        "task": task_id,
        "criterion": number,
        "requirement": spec,
        "revision": _epoch(project, task_id),
        "plan_sha256": sha256_file(project / "context/project_plan.json"),
        "targets": {path: sha256_file(safe_output(project, path)) for path in targets},
    }


def receipt_path(task: str, number: int) -> str:
    return f"context/operator-proofs/{validate_task_id(task)}/{number}.json"


def collect_operator_proof(
    project: Path,
    task_id: str,
    number: int,
    *,
    apply: bool,
    image: str | None = None,
    run_id: int | None = None,
    token_file: Path | None = None,
    observation: str | None = None,
    outcome: str | None = None,
) -> dict[str, Any]:
    assert_no_symlinks(project, label="projet")
    plan = read_json(project / "context/project_plan.json")
    task = next((t for t in plan["tasks"] if t["id"] == task_id), None)
    if task is None:
        raise ValueError("tâche inconnue")
    binding = _binding(project, task, number)
    spec = binding["requirement"]
    if not spec or spec[0] not in {"lab", "ci", "observation"}:
        raise ValueError("ce critère ne demande pas de reçu opérateur")
    if not apply:
        return {"request": binding, "applied": False}
    details: dict[str, Any]
    if spec[0] == "lab":
        filenames = [Path(*Path(p).parts[2:]) for p in binding["targets"]]
        applicable = {
            "terraform-validate": any(p.suffix == ".tf" and len(p.parts) == 1 for p in filenames),
            "terraform-fmt": any(p.suffix == ".tf" for p in filenames),
            "ansible-lint": any(p.suffix in {".yml", ".yaml"} for p in filenames),
            "shellcheck": all(p.suffix == ".sh" for p in filenames),
            "hadolint": all(p.name == "Dockerfile" for p in filenames),
            "actionlint": any(p.parts[:2] == (".github", "workflows")
                              and p.suffix in {".yaml", ".yml"} for p in filenames),
        }
        if not applicable[spec[1]]:
            raise ValueError("les fichiers choisis ne conviennent pas au validateur")
        with tempfile.TemporaryDirectory(prefix="clawfedora-request-") as directory:
            root = Path(directory)
            # Drop the approved scope/task prefix, retaining .github/workflows etc.
            for relative, digest in binding["targets"].items():
                dest = root.joinpath(*Path(relative).parts[2:])
                dest.parent.mkdir(parents=True, exist_ok=True)
                with dest.open("xb") as handle:
                    handle.write((project / relative).read_bytes())
                if sha256_file(dest) != digest:
                    raise ValueError("source modifiée avant le contrôle")
            if len(devops_lab.snapshot_manifest(root)) != len(binding["targets"]):
                raise ValueError("fichier absent de la sélection du laboratoire")
            code = devops_lab.run_lab(root, spec[1], image, True)
        details = {"image": image, "exit_code": code, "scope": "static-lab"}
        passed = code == 0
    elif spec[0] == "ci":
        if run_id is None:
            raise ValueError("--run-id requis")
        _, provider, repository, commit = spec
        details = (
            verify_private_run(provider, repository, run_id, commit, token_file=token_file)
            if token_file
            else verify_public_run(provider, repository, run_id, commit)
        )
        passed = details["verdict"] == "VERIFIED_RUN_SUCCESS"
    else:
        if outcome not in {"PASS", "FAIL"}:
            raise ValueError("--result PASS ou FAIL requis pour une observation humaine")
        if not observation or not 1 <= len(observation.strip()) <= 1500:
            raise ValueError("--observation requise: cible, attendu et résultat réellement observé")
        details = {"scope": "operator-observation", "observed": observation.strip()}
        passed = outcome == "PASS"
    if _binding(project, task, number) != binding:
        raise ValueError("cible modifiée pendant le contrôle")
    record = {"binding": binding, "details": details, "at": now(), "passed": passed}
    write_json(project / receipt_path(task_id, number), record)
    return record


def resolve_reference(
    project: Path,
    task: dict[str, Any],
    number: int,
    reference: str,
) -> dict[str, str]:
    """Resolve exact relative names selected from the plan/current task under worker lock."""
    binding = _binding(project, task, number)
    spec = binding["requirement"]
    allowed = task["expected_outputs"]
    if not spec:
        if not isinstance(reference, str) or reference not in allowed:
            raise ValueError("preuve de contenu hors des sorties approuvées de la tâche")
    elif spec[0] == "lint":
        # Only worker-copied receipts are admissible; agent outputs cannot impersonate them.
        if (
            not re.fullmatch(
                rf"evidence/{re.escape(task['id'])}/tool-[0-9a-f]{{32}}\.json", reference
            )
            or reference in allowed
        ):
            raise ValueError("reçu de lint de la tâche requis")
        proof = read_json(project / reference)
        if not (
            proof.get("origin") == "managed-tool-runner"
            and proof.get("tool") == spec[1]
            and proof.get("status") == "PASS"
            and proof.get("input_sha256") == binding["targets"][spec[2]]
        ):
            raise ValueError("lint ou fichier contrôlé différent du critère")
    else:
        if reference != receipt_path(task["id"], number):
            raise ValueError("reçu opérateur du critère requis")
        proof = read_json(project / reference)
        if proof.get("passed") is not True or proof.get("binding") != binding:
            raise ValueError("preuve absente, en échec ou périmée")
    if not spec:
        safe_output(project, reference)
    return {p: sha256_file(project / p) for p in {reference, *binding["targets"]}}


def proof_catalog(project: Path) -> dict[str, Any]:
    """A bounded, read-only index for the reviewer. It contains no raw lint logs."""
    tasks = read_json(project / "context/project_plan.json")["tasks"]
    rows = {}
    for task in tasks:
        role_task = validate_task_id(task["id"])
        items = []
        for number, criterion in enumerate(task["acceptance_criteria"], 1):
            spec = requirement(criterion, task["expected_outputs"])
            if not spec:
                candidates = task["expected_outputs"]
            elif spec[0] == "lint":
                paths = (project / "evidence" / role_task).glob("tool-*.json")
                candidates = [p.relative_to(project).as_posix() for p in sorted(paths)]
            else:
                candidates = [receipt_path(role_task, number)]
            valid = []
            for reference in candidates:
                try:
                    hashes = resolve_reference(project, task, number, reference)
                except (ValueError, OSError):
                    continue
                valid.append({"path": reference, "sha256": hashes[reference]})
            items.append({"criterion": number, "scope": spec or ["content"], "references": valid})
        rows[role_task] = items
    return {"tasks": rows, "scope": "pièces disponibles; pertinence à justifier par critère"}
