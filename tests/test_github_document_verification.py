"""Recheck approved documentary changes against the correct new Git snapshot."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

from clawfedora import github_document_boundaries as boundaries
from clawfedora import github_document_corrections as corrections
from clawfedora import github_document_inventory as inv
from clawfedora import github_document_links as links
from clawfedora import github_document_verification as verification
from clawfedora.notion_write import _digest

REPO = "example/atlas"
BASE = "a" * 40
TIP = "b" * 40
BROKEN = b"# Accueil\n\n[Guide](absent.md)\n"
FIXED = b"# Accueil\n\n[Guide](guide.md)\n"


def _blob(raw: bytes) -> str:
    return hashlib.sha1(f"blob {len(raw)}\0".encode() + raw, usedforsecurity=False).hexdigest()


def _inventory(commit: str, raw: bytes | None) -> tuple[dict[str, Any], dict[str, Any] | None]:
    documents = {"guide.md": b"# Guide\n"}
    if raw is not None:
        documents["README.md"] = raw
    entries = [
        {"path": path, "mode": "100644", "type": "blob", "sha": _blob(data)}
        for path, data in documents.items()
    ]
    tree = ("c" if commit == BASE else "d") * 40
    inventory = inv._inventory(commit, tree, entries, REPO)
    blobs = {_blob(data): data for data in documents.values()}
    report = (
        links.LinkAudit(inventory, entries, blobs.get, REPO).report(["README.md"])
        if raw is not None else None
    )
    return inventory, report


@pytest.fixture
def inputs(tmp_path: Path) -> dict[str, Any]:
    before, original = _inventory(BASE, BROKEN)
    after, observed = _inventory(TIP, FIXED)
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "README.md").write_bytes(FIXED)
    review = _prepare(stage, before, original, "links")
    return dict(repo=REPO, commit=TIP, expected_review=review["report_sha256"], review=review,
                before_inventory=before, after_inventory=after, before_reports=[original],
                after_reports=[observed])


def _prepare(
    stage: Path, inventory: dict[str, Any], report: object, family: str,
) -> dict[str, Any]:
    return corrections.prepare(
        repo=REPO, base="main", base_sha=BASE, branch="atelier/documentation", changes=stage,
        inventory=inventory, reports=[report], selections=[f"{family}:1"],
    )


def _report(
    family: str, inventory: dict[str, Any], rows: list[dict[str, Any]], **details: Any,
) -> dict[str, Any]:
    assessment, key = corrections.REPORTS[family]
    body = {"schema": 1, "assessment": assessment, "classification": inv.CLASSIFICATION,
            **{name: inventory[name] for name in corrections.BINDING}, key: rows, **details}
    return {**body, "report_sha256": _digest(body)}


def _change_family(
    tmp_path: Path, inputs: dict[str, Any], family: str,
    original: dict[str, Any], observed: dict[str, Any] | None,
) -> None:
    review = _prepare(tmp_path / "stage", inputs["before_inventory"], original, family)
    inputs.update(review=review, expected_review=review["report_sha256"],
                  before_reports=[original], after_reports=[observed] if observed else [])


def test_link_case_roundtrip(inputs: dict[str, Any]) -> None:
    result = verification.verify(**inputs)
    assert result["status"] == "verified"
    assert result["files"] == [{"path": "README.md", "status": "exact_blob_present"}]
    assert result["findings"][0]["status"] == "confirmed"
    assert result["verified_commit"] == TIP
    assert "absent.md" not in json.dumps(result)


@pytest.mark.parametrize(("content", "status"), [
    (BROKEN, "different_blob"),
    (None, "document_absent_or_ineligible"),
])
def test_wrong_or_missing_blob_is_not_attested(
    inputs: dict[str, Any], content: bytes | None, status: str,
) -> None:
    after, report = _inventory(TIP, content)
    result = verification.verify(**(inputs | {
        "after_inventory": after, "after_reports": [report] if report else [],
    }))
    assert result["status"] == "review_required"
    assert result["files"][0]["status"] == status
    assert result["findings"][0]["status"] == "not_verified"


@pytest.mark.parametrize(("details", "rows", "status"), [
    ({"scopes": ["guide.md"], "markdown_inspected": ["guide.md"]}, [], "not_verified"),
    ({"scopes": ["README.md"], "markdown_inspected": []}, [], "not_verified"),
    ({"scopes": ["README.md"], "markdown_inspected": ["README.md"]},
     [{"path": "README.md", "status": "missing_anchor"}], "still_open"),
    ({"scopes": ["README.md"], "markdown_inspected": ["README.md"]},
     [{"path": "README.md", "status": "target_excluded"}], "not_verified"),
])
def test_link_evidence_requires_comparable_coverage(
    inputs: dict[str, Any], details: dict[str, Any], rows: list[dict[str, Any]], status: str,
) -> None:
    report = _report("links", inputs["after_inventory"], rows, **details)
    result = verification.verify(**(inputs | {"after_reports": [report]}))
    assert result["files"][0]["status"] == "exact_blob_present"
    assert result["status"] == "review_required"
    assert result["findings"][0]["status"] == status


def test_refuses_wrong_approval_old_audit_and_another_revision(inputs: dict[str, Any]) -> None:
    with pytest.raises(inv.InventoryError, match="revue approuvée"):
        verification.verify(**(inputs | {"expected_review": "0" * 64}))
    with pytest.raises(inv.InventoryError, match="autre révision"):
        verification.verify(**(inputs | {"after_reports": inputs["before_reports"]}))
    with pytest.raises(inv.InventoryError, match="SHA de vérification"):
        verification.verify(**(inputs | {"commit": BASE}))


def test_same_coherence_rule_and_contract_required(
    inputs: dict[str, Any], tmp_path: Path,
) -> None:
    original_row = {"id": "version", "kind": "version", "status": "version_drift",
                    "declarations": [{"path": "README.md", "comparison": "version_drift"}]}
    contract = {"contract_path": ".github/doc.json", "contract_blob": "c" * 40}
    original = _report("coherence", inputs["before_inventory"], [original_row], **contract)
    observed_row = {"id": "version", "kind": "version", "status": "match"}
    observed = _report("coherence", inputs["after_inventory"], [observed_row], **contract)
    _change_family(tmp_path, inputs, "coherence", original, observed)
    assert verification.verify(**inputs)["status"] == "verified"
    different_contract = contract | {"contract_blob": "d" * 40}
    other = _report("coherence", inputs["after_inventory"], [observed_row], **different_contract)
    result = verification.verify(**(inputs | {"after_reports": [other]}))
    assert result["findings"][0]["status"] == "not_verified"


@pytest.mark.parametrize(("state", "expected"), [
    (None, "confirmed"), ("observed_success", "confirmed"),
    ("different_revision", "still_open"), ("observed_pending", "not_verified"),
])
def test_ci_references_on_new_snapshot(
    inputs: dict[str, Any], tmp_path: Path, state: str | None, expected: str,
) -> None:
    before_row = {"path": "README.md", "status": "different_revision"}
    original = _report("ci", inputs["before_inventory"], [before_row])
    rows = [{"path": "README.md", "status": state}] if state else []
    observed = _report("ci", inputs["after_inventory"], rows, documents_inspected=["README.md"])
    _change_family(tmp_path, inputs, "ci", original, observed)
    assert verification.verify(**inputs)["findings"][0]["status"] == expected


def test_boundary_replayed_before_and_after(
    inputs: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = {"code": "private_literal_in_public_document", "locations": [{"path": "README.md"}]}
    original = _report("boundaries", inputs["before_inventory"], [row])
    observed = _report("boundaries", inputs["after_inventory"], [],
                       coverage={"documents_checked": ["README.md"]})
    _change_family(tmp_path, inputs, "boundaries", original, None)
    policy = {"schema": 1, "private_paths": [], "literals": ["marqueur de test privé"]}
    calls: list[str] = []
    reproduce = True

    def audit(
        repo: str, commit: str, scopes: list[str], *, policy: object, expected_inventory: str,
    ) -> dict[str, Any]:
        assert repo == REPO and scopes == ["README.md"] and isinstance(policy, dict)
        report = original if commit == BASE else observed
        assert expected_inventory == report["inventory_sha256"]
        calls.append(commit)
        return report if reproduce else {**report, "report_sha256": "0" * 64}

    monkeypatch.setattr(boundaries, "audit_github", audit)
    assert verification.verify(**inputs)["status"] == "review_required"
    assert calls == []
    result = verification.verify(
        **inputs, boundary_scopes=["README.md"], boundary_policy=policy,
    )
    assert calls == [BASE, TIP]
    assert result["status"] == "verified"
    assert "marqueur" not in json.dumps(result)
    reproduce = False
    with pytest.raises(inv.InventoryError, match="référence d'origine"):
        verification.verify(**inputs, boundary_scopes=["README.md"], boundary_policy=policy)
    assert calls == [BASE, TIP, BASE]


@pytest.mark.skipif(os.name != "posix", reason="permissions POSIX")
def test_cli_writes_private_report_on_verification(
    inputs: dict[str, Any], tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    args = ["--repo", REPO, "--commit", TIP, "--review-sha256", inputs["expected_review"]]
    for flag, data in [
        ("review", inputs["review"]), ("before-inventory", inputs["before_inventory"]),
        ("after-inventory", inputs["after_inventory"]),
        ("before-report", inputs["before_reports"][0]),
        ("after-report", inputs["after_reports"][0]),
    ]:
        path = private / f"{flag}.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        path.chmod(0o600)
        args.extend((f"--{flag}", str(path)))
    output = private / "verification.json"
    assert verification.main([*args, "--output", str(output)]) == 0
    assert output.stat().st_mode & 0o777 == 0o600
    assert json.loads(capsys.readouterr().out)["status"] == "verified"
    assert verification.main([*args, "--output", str(output)]) == 2
