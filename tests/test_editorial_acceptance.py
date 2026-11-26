"""Qualification records never attest native work automatically."""
from __future__ import annotations

import hashlib
import json

import pytest

from clawfedora import editorial_acceptance as ea

COMMIT = "a" * 40


@pytest.fixture
def dossier(tmp_path):
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    form = root / "observations.json"
    ea.template(COMMIT, form)
    data = json.loads(form.read_text())

    def save():
        form.write_text(json.dumps(data))

    def proof(name, value):
        path = root / name
        path.write_text(value)
        path.chmod(0o600)
        return {"file": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    return root, form, data, save, proof


def test_plan_and_template_are_not_executed(dossier):
    _, form, data, _, _ = dossier
    assert ea.plan()["assessment"] == "NOT_RUN"
    assert len(ea.plan()["cases"]) == 13
    assert not data["operator_attests_native_run"]
    assert all(row["state"] == "NOT_RUN" for row in data["cases"].values())
    result = ea.evaluate(form, COMMIT)
    assert result["assessment"] == "OPERATOR_REVIEW_INCOMPLETE"
    assert result["native_qualification"] is False
    assert result["remote_actions_executed"] is False
    assert form.stat().st_mode & 0o077 == 0


def test_complete_is_operator_claim_not_certification(dossier):
    _, form, data, save, proof = dossier
    data["operator_attests_native_run"] = True
    for ident, row in data["cases"].items():
        row["state"] = "PASS"
        row["evidence"] = [proof(f"{ident}.json", f"synthetic-test-only-{ident}")]
    save()
    result = ea.evaluate(form, COMMIT)
    assert result["assessment"] == "OPERATOR_REPORTED_COMPLETE"
    assert result["native_qualification"] is False
    assert "synthetic-test-only" not in json.dumps(result)
    assert ".json" not in json.dumps(result)
    assert result["form_sha256"] == hashlib.sha256(form.read_bytes()).hexdigest()


@pytest.mark.parametrize("problem", ["no_attestation", "no_proof", "hash", "path", "reuse",
                                     "same_bytes", "symlink", "permissions", "wrong_commit"])
def test_refuses_unbound_or_unsafe_claims(dossier, problem):
    root, form, data, save, proof = dossier
    data["operator_attests_native_run"] = True
    item = proof("roles.json", "example")
    data["cases"]["roles"] = {"state": "PASS", "evidence": [item]}
    commit = COMMIT
    if problem == "no_attestation":
        data["operator_attests_native_run"] = False
    elif problem == "no_proof":
        data["cases"]["roles"]["evidence"] = []
    elif problem == "hash":
        (root / "roles.json").write_text("changed")
    elif problem == "path":
        item["file"] = "../roles.json"
    elif problem == "reuse":
        data["cases"]["markdown"] = {"state": "PASS", "evidence": [item]}
    elif problem == "same_bytes":
        data["cases"]["markdown"] = {
            "state": "PASS", "evidence": [proof("copy.json", "example")],
        }
    elif problem == "symlink":
        path = root / "roles.json"
        path.rename(root / "other.json")
        path.symlink_to(root / "other.json")
    elif problem == "permissions":
        (root / "roles.json").chmod(0o644)
    else:
        commit = "b" * 40
    save()
    with pytest.raises(ValueError):
        ea.evaluate(form, commit)


def test_failed_case_and_private_receipt(dossier, capsys):
    root, form, data, save, proof = dossier
    data["operator_attests_native_run"] = True
    data["cases"]["roles"] = {"state": "FAIL", "evidence": [proof("roles.json", "failure")]}
    save()
    output = root / "receipt.json"
    args = ["review", "--commit", COMMIT, "--form", str(form), "--output", str(output)]
    assert ea.main(args) == 1
    assert json.loads(output.read_text())["assessment"] == "OPERATOR_REPORTED_FAILURE"
    assert output.stat().st_mode & 0o077 == 0
    assert ea.main(args) == 2
    assert "failure" not in capsys.readouterr().out


def test_git_checkout_refused(dossier):
    root, _, _, _, _ = dossier
    (root / ".git").mkdir()
    with pytest.raises(ValueError, match="dépôt Git"):
        ea.template(COMMIT, root / "new.json")
