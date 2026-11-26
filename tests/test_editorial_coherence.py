"""Cross-support checks are local and never return private reference values."""
from __future__ import annotations

import hashlib
import json

import pytest

from clawfedora import editorial_coherence as ec

COMMIT = "a" * 40
PAGE = "b" * 32
STAMP = "2026-11-25T20:00:00Z"
PRIVATE = "internal-example-7c41"
PUBLIC = "Architecture V3"


@pytest.fixture
def snapshots(tmp_path):
    github = tmp_path / "github"
    notion = tmp_path / "notion"
    github.mkdir()
    notion.mkdir()
    (github / ".source-provenance.json").write_text(json.dumps({
        "provider": "github", "commit": COMMIT, "read_only": True,
        "repository": "example/atlas",
    }))
    (notion / ".source-provenance.json").write_text(json.dumps({
        "provider": "notion", "captured_at": STAMP, "read_only": True,
        "classification": "private_local_only", "pages": [{"id": PAGE}],
    }))

    def build(public=None, private=None):
        if public is None:
            public = f"Référence éditoriale [architecture] : {PUBLIC}\n"
        if private is None:
            private = (f"Référence éditoriale [architecture] : {PUBLIC}\n"
                       f"Référence éditoriale [lab.identity] : {PRIVATE}\n")
        sources = []
        for ident, support, visibility, filename, revision, body in (
            ("readme", "github", "public", "README.md", COMMIT, public),
            ("wiki", "notion", "private", f"page-{PAGE}.md", STAMP, private),
        ):
            raw = body.encode()
            (tmp_path / support / filename).write_bytes(raw)
            sources.append({
                "id": ident, "support": support, "visibility": visibility,
                "snapshot": support, "path": filename, "revision": revision,
                "sha256": hashlib.sha256(raw).hexdigest(),
            })
        spec = {"schema": 1, "sources": sources,
                "facts": {"architecture": "shared", "lab.identity": "private"}}
        (tmp_path / "manifest.json").write_text(json.dumps(spec))
        return spec

    build()
    return tmp_path, build


def test_matching_references_are_not_certification(snapshots):
    root, _ = snapshots
    result = ec.inspect(root, "manifest.json")
    assert result["assessment"] == "DECLARED_REFERENCES_ALIGNED"
    assert result["findings"] == []
    assert result["facts_checked"] == 2
    assert PRIVATE not in json.dumps(result)
    assert PUBLIC not in json.dumps(result)


def test_divergence_and_private_literal_outside_markers(snapshots):
    root, build = snapshots
    build(public=f"Référence éditoriale [architecture] : Architecture V2\nHost {PRIVATE}\n")
    result = ec.inspect(root, "manifest.json")
    assert result["assessment"] == "REVIEW_REQUIRED"
    assert {item["code"] for item in result["findings"]} == {
        "REFERENCE_DIVERGENCE", "PRIVATE_FACT_EXPOSURE",
    }
    assert PRIVATE not in json.dumps(result)
    assert result["findings"][0]["locations"]


def test_unclassified_missing_and_repeated(snapshots):
    root, build = snapshots
    build(public="Référence éditoriale [other] : Value\n",
          private="Référence éditoriale [architecture] : V3\n"
                  "Référence éditoriale [architecture] : V3\n")
    assert {item["code"] for item in ec.inspect(root, "manifest.json")["findings"]} == {
        "UNCLASSIFIED_FACT", "SHARED_REFERENCE_MISSING", "PRIVATE_REFERENCE_MISSING",
        "REPEATED_REFERENCE",
    }


def test_markers_in_code_are_examples(snapshots):
    root, build = snapshots
    build(public=f"Référence éditoriale [architecture] : {PUBLIC}\n"
                 "~~~text\nRéférence éditoriale [other] : example\n~~~\n")
    assert ec.inspect(root, "manifest.json")["findings"] == []


@pytest.mark.parametrize("fault", ["hash", "commit", "notion_public", "traversal", "symlink"])
def test_refuse_unapproved_or_unconfined_sources(snapshots, fault):
    root, build = snapshots
    spec = build()
    if fault == "hash":
        (root / "github/README.md").write_text("changed")
    elif fault == "commit":
        spec["sources"][0]["revision"] = "c" * 40
    elif fault == "notion_public":
        spec["sources"][1]["visibility"] = "public"
    elif fault == "traversal":
        spec["sources"][0]["path"] = "../manifest.json"
    else:
        path = root / "github/README.md"
        target = root / "external.md"
        path.rename(target)
        path.symlink_to(target)
    (root / "manifest.json").write_text(json.dumps(spec))
    with pytest.raises(ValueError):
        ec.inspect(root, "manifest.json")


def test_cli_has_review_exit_code_and_no_value_disclosure(snapshots, capsys):
    root, build = snapshots
    args = ["--root", str(root), "--manifest", "manifest.json"]
    assert ec.main(args) == 0
    build(public=f"Référence éditoriale [architecture] : V2\n{PRIVATE}\n")
    assert ec.main(args) == 1
    (root / "manifest.json").write_text("{}")
    assert ec.main(args) == 2
    assert PRIVATE not in capsys.readouterr().out
