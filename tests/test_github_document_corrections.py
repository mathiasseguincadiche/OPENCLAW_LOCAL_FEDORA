"""Attach reviewed Markdown bytes to actionable findings on an exact Git snapshot."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

from clawfedora import github_document_corrections as corrections
from clawfedora import github_document_inventory as inv
from clawfedora import github_document_links as links
from clawfedora import github_pr as pr
from clawfedora.notion_write import _digest

COMMIT = "a" * 40
TREE = "b" * 40
REPO = "example/atlas"
BRANCH = "atelier/corriger-liens"
BEFORE = b"[Guide](absent.md)\n"
AFTER = b"[Guide](guide.md)\n"


def _blob(raw: bytes) -> str:
    return hashlib.sha1(f"blob {len(raw)}\0".encode() + raw, usedforsecurity=False).hexdigest()


@pytest.fixture
def inputs(tmp_path: Path) -> dict[str, Any]:
    contents = {"README.md": BEFORE, "guide.md": b"# Guide\n", "config.yml": b"version: 1\n"}
    entries = [
        {"path": path, "type": "blob", "mode": "100644", "sha": _blob(raw)}
        for path, raw in contents.items()
    ]
    inventory = inv._inventory(COMMIT, TREE, entries, REPO)
    blobs = {_blob(raw): raw for raw in contents.values()}
    audit = links.LinkAudit(inventory, entries, blobs.get, REPO).report(["README.md"])
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "README.md").write_bytes(AFTER)
    return dict(repo=REPO, base="main", base_sha=COMMIT, branch=BRANCH, changes=stage,
                inventory=inventory, reports=[audit], selections=["links:1"])


def test_exact_draft_preview_and_only_review_metadata(inputs: dict[str, Any]) -> None:
    result = corrections.prepare(**inputs)
    preview = pr.make_plan(
        repo=REPO, base="main", base_sha=COMMIT, branch=BRANCH,
        changes=inputs["changes"], allow_workflows=False,
    )
    assert result["publication_preview"] == preview
    assert result["edits"] == [{"path": "README.md", "base_git_blob": _blob(BEFORE),
                                "proposed_git_blob": _blob(AFTER)}]
    assert result["findings"] == [{"reference": "links:1", "edited_paths": ["README.md"],
                                   "report_sha256": inputs["reports"][0]["report_sha256"]}]
    assert "absent.md" not in json.dumps(result)
    assert result["report_sha256"] == _digest(
        {k: v for k, v in result.items() if k != "report_sha256"}
    )
    (inputs["changes"] / "README.md").write_bytes(AFTER + b"\n")
    assert corrections.prepare(**inputs)["publication_preview"] != preview


def _outcome(inputs: dict[str, Any], family: str, row: dict[str, Any]) -> dict[str, Any]:
    assessment, key = corrections.REPORTS[family]
    body = {"schema": 1, "assessment": assessment, "classification": inv.CLASSIFICATION,
            **{name: inputs["inventory"][name] for name in corrections.BINDING}, key: [row]}
    return {**body, "report_sha256": _digest(body)}


@pytest.mark.parametrize(("family", "row"), [
    ("coherence", {"status": "missing_technical_path", "document": "README.md",
                   "target": "config.yml"}),
    ("coherence", {"status": "version_drift",
                   "authority": {"path": "config.yml"},
                   "declarations": [{"comparison": "version_drift", "path": "README.md"}]}),
    ("ci", {"status": "different_revision", "path": "README.md"}),
    ("boundaries", {"code": "identical_documents",
                    "locations": [{"path": "README.md"}, {"path": "guide.md"}]}),
    ("boundaries", {"code": "private_literal_in_public_document",
                    "locations": [{"path": "README.md", "line": 2}], "operator_rule_positions": [1]}),
])
def test_report_family_review(inputs: dict[str, Any], family: str, row: dict[str, Any]) -> None:
    inputs["reports"] = [_outcome(inputs, family, row)]
    inputs["selections"] = [f"{family}:1"]
    result = corrections.prepare(**inputs)
    assert result["findings"][0]["edited_paths"] == ["README.md"]
    assert "operator_rule_positions" not in json.dumps(result)
    assert "config.yml" not in json.dumps(result)


def test_tampered_and_unrelated_audits_refused(inputs: dict[str, Any]) -> None:
    audit = inputs["reports"][0]
    audit["commit"] = "c" * 40
    with pytest.raises(inv.InventoryError, match="empreinte"):
        corrections.prepare(**inputs)
    audit["report_sha256"] = _digest({k: v for k, v in audit.items() if k != "report_sha256"})
    with pytest.raises(inv.InventoryError, match="autre révision"):
        corrections.prepare(**inputs)
    inputs["base_sha"] = "d" * 40
    with pytest.raises(inv.InventoryError, match="SHA de base exacts"):
        corrections.prepare(**inputs)


@pytest.mark.parametrize(("path", "content", "failure"), [
    ("guide.md", b"# Another guide\n", "chaque fichier"),
    ("README.md", BEFORE, "déjà ce contenu"),
    ("nouveau.md", b"# Nouveau\n", "documents Markdown existants"),
    ("config.yml", b"version: 2\n", "documents Markdown existants"),
])
def test_staging_scope(inputs: dict[str, Any], path: str, content: bytes, failure: str) -> None:
    (inputs["changes"] / path).write_bytes(content)
    with pytest.raises(inv.InventoryError, match=failure):
        corrections.prepare(**inputs)


def test_selection_rejects_unchecked_errors_and_unknown_rows(inputs: dict[str, Any]) -> None:
    for selections, message in [
        (["links:2"], "constat absent"), (["links:1", "links:1"], "sélection"),
        (["ci:1"], "rapport manquant"), (["links:01"], "référence"),
    ]:
        with pytest.raises(inv.InventoryError, match=message):
            corrections.prepare(**(inputs | {"selections": selections}))
    report = _outcome(inputs, "ci", {"status": "run_not_verified", "path": "README.md"})
    with pytest.raises(inv.InventoryError, match="constat non exploitable"):
        corrections.prepare(**(inputs | {"reports": [report], "selections": ["ci:1"]}))


def test_staging_drift_refused(inputs: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    original = pr.make_plan

    def plan_then_edit(**kwargs: Any) -> dict[str, Any]:
        preview = original(**kwargs)
        (inputs["changes"] / "README.md").write_bytes(b"# Nouveau\n")
        return preview

    monkeypatch.setattr(pr, "make_plan", plan_then_edit)
    with pytest.raises(inv.InventoryError, match="modifié pendant"):
        corrections.prepare(**inputs)


@pytest.mark.skipif(os.name != "posix", reason="permissions POSIX")
def test_cli_private_report(
    inputs: dict[str, Any], tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    inputs["changes"].chmod(0o700)
    inventory_path, report_path, output = [
        private / name for name in ("inventory.json", "audit.json", "review.json")
    ]
    for path, value in ((inventory_path, inputs["inventory"]), (report_path, inputs["reports"][0])):
        path.write_text(json.dumps(value), encoding="utf-8")
        path.chmod(0o600)
    args = [
        "--repo", REPO, "--base-sha", COMMIT, "--branch", BRANCH,
        "--changes", str(inputs["changes"]), "--inventory", str(inventory_path),
        "--report", str(report_path), "--finding", "links:1", "--output",
    ]
    assert corrections.main([*args, str(inputs["changes"] / "review.json")]) == 2
    assert corrections.main([*args, str(output)]) == 0
    assert output.stat().st_mode & 0o777 == 0o600
    before = output.read_bytes()
    assert corrections.main([*args, str(output)]) == 2
    assert output.read_bytes() == before
    assert "absent.md" not in capsys.readouterr().out
