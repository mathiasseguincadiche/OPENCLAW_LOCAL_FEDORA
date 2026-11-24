"""Persistent, bounded edit → test → repair loop for the local DevOps agent.

Only task snapshots are read. Edits live in a private disposable worktree, not
in the source snapshot, host project, or a git checkout. Validators are fixed,
rootless Podman commands with networking disabled. A PASS generates immutable
artifacts that the trusted project worker may collect for human review.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from clawfedora.devops_lab import TOOLS, LabRefusal, command_for, run_lab, snapshot_manifest
from clawfedora.devops_sandbox import (
    _approved_image,
    _overlay,
    _policy_file,
    _reserve_attempt,
    _validated_scope,
)
from clawfedora.project_common import assert_no_symlinks
from clawfedora.specialist_tools import receipt


def _digest(folder: Path) -> str:
    """Hash exact bytes and filenames, not a model-reported result."""
    manifest = snapshot_manifest(folder)
    h = hashlib.sha256()
    for name in manifest:
        h.update(name.as_posix().encode("utf-8") + b"\x00")
        data = (folder / name).read_bytes()
        h.update(len(data).to_bytes(8, "big") + data)
    return h.hexdigest()


def _source_digest(source: Path) -> str:
    """The snapshot guard is mandatory and must still match the source files."""
    guard_file = source / ".openclaw-fedora-input-guard.json"
    if guard_file.is_symlink():
        raise LabRefusal("Garde du snapshot lié interdit")
    guard = json.loads(guard_file.read_text(encoding="utf-8")).get("files")
    if not isinstance(guard, dict):
        raise LabRefusal("Garde du snapshot manquant")
    actual: dict[str, str] = {}
    for path in source.rglob("*"):
        if path.is_symlink():
            raise LabRefusal("Lien symbolique interdit")
        if path.is_file() and path != guard_file:
            actual[path.relative_to(source).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    if guard != actual:
        raise LabRefusal("Snapshot modifié : intégrité des entrées invalide")
    return _digest(source)


def _copy_files(source: Path, destination: Path) -> None:
    for name in snapshot_manifest(source):
        path = source / name
        target = destination / name
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with path.open("rb") as reader, target.open("xb") as writer:
            shutil.copyfileobj(reader, writer)
        target.chmod(0o600)


def _state_root(runtime: Path, workspace: Path, scope: str) -> Path:
    _policy_file(runtime)
    state = runtime / "state"
    if state.is_symlink():
        raise LabRefusal("État runtime lié interdit")
    base = state / "sandbox-iterations"
    if base.is_symlink():
        raise LabRefusal("Répertoire de travaux lié interdit")
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Scope includes a task session; workspace identity prevents cross-role reuse.
    key = hashlib.sha256((str(workspace.resolve()) + "\x00" + scope).encode()).hexdigest()
    root = base / key
    if root.is_symlink():
        raise LabRefusal("Révision liée interdite")
    root.mkdir(mode=0o700, exist_ok=True)
    assert_no_symlinks(root, label="historique sandbox")
    return root


def iterate(
    runtime: Path,
    workspace: Path,
    scope: str,
    operation: str,
    expected_revision: str,
    validator: str | None = None,
    files: dict[str, str] | None = None,
    *, validators: list[str] | None = None,
) -> dict[str, Any]:
    """Inspect state or persist another candidate and run a real validator.

    Calling repeatedly with the previous revision implements the repair loop.
    Neither the model nor this tool can publish, merge or deploy changes.
    """
    source = _validated_scope(workspace, scope)
    initial_digest = _source_digest(source)
    root = _state_root(runtime, workspace, scope)
    lock = root / ".lock"
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "r+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        state_file = root / "state.json"
        state: dict[str, Any] = (
            json.loads(state_file.read_text("utf-8")) if state_file.exists() else {}
        )
        if state and state.get("source_digest") != initial_digest:
            raise LabRefusal("Snapshot initial différent : nouvelle tâche requise")
        revision = str(state.get("revision", "initial"))
        if operation == "inspect":
            if expected_revision != revision:
                raise LabRefusal("Révision périmée : inspecter avant de corriger")
            return {
                "status": state.get("status", "NOT_STARTED"),
                "revision": revision,
                "attempts": state.get("attempts", 0),
                "files_sha256": state.get("files_sha256", {}),
                "validator": state.get("validator"),
                "validators": state.get("validators", []),
                "validation_results": state.get("validation_results", []),
                "network": "none",
                "workspace_modified": False,
            }
        if operation != "edit_test":
            raise LabRefusal("Opération inconnue")
        if validators is None:
            if validator not in TOOLS:
                raise LabRefusal("Validateur non autorisé")
            selected = [validator]
        else:
            if (
                validator is not None or not isinstance(validators, list)
                or not 2 <= len(validators) <= 3
                or any(not isinstance(item, str) or item not in TOOLS for item in validators)
                or len(set(validators)) != len(validators)
            ):
                raise LabRefusal("Liste de validateurs invalide : deux à trois distincts")
            selected = list(validators)
        previous = state.get("validators", [])
        if len(previous) > 1 and previous != selected:
            raise LabRefusal("Suite de validateurs inchangée requise pour la correction")
        if expected_revision != revision:
            raise LabRefusal("Révision périmée : la correction doit partir de la dernière version")
        if not isinstance(files, dict) or not files:
            raise LabRefusal("Au moins un fichier de correction requis")
        image = _approved_image(runtime)
        parent = root / str(state.get("worktree", "")) if state else source
        if state and (parent.is_symlink() or not parent.is_dir() or _digest(parent) != revision):
            raise LabRefusal("Révision de travail altérée")
        with tempfile.TemporaryDirectory(prefix="candidate-", dir=root) as scratch:
            candidate = Path(scratch) / "source"
            candidate.mkdir(mode=0o700)
            _copy_files(parent, candidate)
            changed = _overlay(candidate, files)
            # Resolve every requested command before spending a bounded attempt.
            if len(selected) > 1:
                manifest = snapshot_manifest(candidate)
                for item in selected:
                    command_for(item, candidate, manifest)
            attempt = _reserve_attempt(runtime, scope)
            # run_lab invokes only known static validators; no agent-generated argv.
            # Validation failures remain revisions so Ornith can fix the reported issues.
            import io
            from contextlib import redirect_stdout
            output = io.StringIO()
            validation_results: list[dict[str, Any]] = []
            candidate_digest = _digest(candidate)
            with redirect_stdout(output):
                for item in selected:
                    print(f"VALIDATOR={item}")
                    if len(selected) == 1:
                        code = run_lab(candidate, item, image, apply=True)
                    else:
                        # Three fresh containers, <= 40s per validator + bounded cleanup.
                        code = run_lab(candidate, item, image, apply=True, timeout=40)
                    validation_results.append({
                        "validator": item, "exit_code": code,
                        "status": "PASS" if code == 0 else "FAIL",
                    })
                    if _digest(candidate) != candidate_digest:
                        raise LabRefusal("Révision modifiée pendant la validation")
            exit_code = next(
                (item["exit_code"] for item in validation_results if item["exit_code"]), 0,
            )
            name = f"rev-{attempt}"
            destination = root / name
            if destination.exists() or destination.is_symlink():
                raise LabRefusal("Révision existante : état de tentative incohérent")
            os.replace(candidate, destination)
        combined = dict(state.get("files_sha256", {}))
        combined.update(changed)
        verdict = "PASS" if exit_code == 0 else "FAIL"
        new_state = {
            "source_digest": initial_digest,
            "revision": candidate_digest,
            "worktree": name,
            "attempts": attempt,
            "status": verdict,
            "validator": validator,
            "validators": selected,
            "validation_results": validation_results,
            "files_sha256": combined,
        }
        temp_state = root / f".state-{attempt}.json"
        temp_state.write_text(json.dumps(new_state, sort_keys=True), encoding="utf-8")
        os.chmod(temp_state, 0o600)
        os.replace(temp_state, state_file)
        result: dict[str, Any] = {
            "status": verdict,
            "exit_code": exit_code,
            "revision": candidate_digest,
            "attempt": attempt,
            "validator": validator,
            "validators": selected,
            "validation_results": validation_results,
            "files_sha256": combined,
            "log": output.getvalue()[-6500:],
            "executed": True,
            "network": "none",
            "workspace_modified": False,
            "next_action": "corriger en utilisant revision puis retester" if exit_code else
                           "soumettre les références des fichiers attendus au worker",
        }
        proof = {k: v for k, v in result.items() if k != "log"}
        proof.update({"scope": scope, "role": "ingenieur-devops", "source_digest": initial_digest})
        ref_path = receipt(workspace, "clawfedora_sandbox_iterate", proof)
        result["receipt"] = ref_path
        if not exit_code:
            identifier = Path(ref_path).stem
            proofs_dir = workspace / ".clawfedora-tool-evidence"
            references = {}
            for relative, digest in combined.items():
                artifact = proofs_dir / f"{identifier}-{digest}.sandbox.data"
                if not artifact.exists():
                    # Immutable evidence copy, never a pointer to a mutable sandbox.
                    content = (destination / relative).read_bytes()
                    if hashlib.sha256(content).hexdigest() != digest:
                        raise LabRefusal("Artefact différent de la correction validée")
                    with artifact.open("xb") as stream:
                        stream.write(content)
                    artifact.chmod(0o440)
                references[relative] = f"@tool-sandbox:{identifier}:{digest}"
            result["references"] = references
        return result
