"""Plan construction reuses scoped evidence and stays review-only."""
from __future__ import annotations

import json
import os
from collections import Counter
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from clawfedora import notion_native_inventory as ni
from clawfedora import notion_rationalization as rational
from clawfedora import notion_references as refs
from clawfedora import notion_write as nw

ROOT = "a" * 32
CANONICAL = "b" * 32
COPY = "c" * 32
ARCHIVE = "d" * 32
SOURCE = "e" * 32
FILE = "f" * 32
MISSING = "1" * 32
BASELINE_TEXT = "Préparer le serveur et relever la version privée 6.2"
COPY_TEXT = "Préparer le serveur et relever la version privée 6.1"


def _block(ident: str, kind: str, **payload: Any) -> dict[str, Any]:
    return {"object": "block", "id": ident, "type": kind, kind: payload,
            "parent": {"type": "page_id", "page_id": ROOT}, "has_children": False}


@pytest.fixture
def capture(monkeypatch: pytest.MonkeyPatch) -> tuple[dict[str, Any], datetime]:
    now = datetime.now(UTC)
    blocks = [
        _block(CANONICAL, "paragraph", rich_text=[{"plain_text": BASELINE_TEXT}]),
        _block(COPY, "paragraph", rich_text=[{"plain_text": COPY_TEXT}]),
        _block(ARCHIVE, "paragraph", rich_text=[{"plain_text": BASELINE_TEXT}]),
        _block(SOURCE, "paragraph", rich_text=[
            {"href": "https://github.com/example/private"},
            {"mention": {"type": "page", "page": {"id": MISSING}}},
            {"href": "https://example.invalid?signature=NON-DIFFUSABLE"},
        ]),
        _block(FILE, "file", type="file", file={
            "url": "https://example.invalid/signed", "expiry_time": (now - timedelta(1)).isoformat(),
        }),
    ]

    def get(path: str, params: dict[str, str]) -> dict[str, Any]:
        if path == f"/v1/pages/{ROOT}":
            return {"object": "page", "id": ROOT}
        assert path == f"/v1/blocks/{ROOT}/children"
        return {"results": blocks, "has_more": False, "next_cursor": None}

    monkeypatch.setattr(ni, "_get", get)
    monkeypatch.setattr(ni.time, "sleep", lambda _: None)
    evidence = refs.capture_references(ROOT)

    def refuse_network(*args: Any) -> None:
        raise AssertionError("planning must be offline")

    monkeypatch.setattr(ni, "_get", refuse_network)
    return evidence, now + timedelta(minutes=1)


def _member(ident: str) -> dict[str, str]:
    return {"category": "block", "id": ident}


def _manifest(snapshot: dict[str, Any], **data: Any) -> dict[str, Any]:
    return {"schema": 1, "root_page": ROOT, "structure_sha256": snapshot["structure_sha256"], **data}


def test_plan_consolidates_real_reports_and_preserves_protected_content(
    capture: tuple[dict[str, Any], datetime],
) -> None:
    bundle, as_of = capture
    snapshot = bundle["inventory"]
    registry = _manifest(snapshot, topics=[
        {"key": "version", "comparison": "normalized_text",
         "canonical": [_member(CANONICAL)], "copies": [_member(COPY), _member(ARCHIVE)]},
    ])
    annotations = _manifest(snapshot, entries=[
        {**_member(CANONICAL), "text": BASELINE_TEXT, "semantic_key": "version"},
        {**_member(COPY), "text": COPY_TEXT, "semantic_key": "version", "truth_key": "version"},
        {**_member(ARCHIVE), "context": ["archive", "installation"]},
    ])
    github = next(x for x in bundle["references"] if x["kind"] == "github")
    observations = {"schema": 1, "capture_sha256": bundle["capture_sha256"], "entries": [{
        "reference_id": github["reference_id"], "observed_at": as_of.isoformat(),
        "result": "http", "visibility": "unknown", "status_code": 403,
    }]}
    arguments = {"annotations": annotations, "registry": registry, "reference_capture": bundle,
                 "observations": observations, "as_of": as_of, "before": snapshot}
    report = rational.plan(snapshot, root_page=ROOT, **arguments)
    issues = {row["signal"]: row for row in report["issues"]}
    assert set(issues) == {
        "duplicate_exact", "duplicate_semantic", "access_restricted", "outside_observed_inventory",
        "temporary_url_expired", "divergent_observable_evidence",
    }
    assert len([row for row in report["issues"] if row["signal"] == "duplicate_semantic"]) == 2
    assert len({row["issue_id"] for row in report["issues"]}) == len(report["issues"])
    assert {"duplicates", "references", "sources"} == report["evidence_reports"].keys()
    assert report["baseline_comparison"]["counts"] == {
        "added": 0, "absent": 0, "modified": 0, "reordered": 0,
    }
    archive = next(row for row in issues["duplicate_exact"]["content_to_preserve"]
                   if row["id"] == ARCHIVE)
    assert archive["context"] == ["archive", "installation"]
    assert {row["id"] for row in issues["divergent_observable_evidence"]["content_to_preserve"]} == {
        CANONICAL, COPY,
    }
    assert not report["remote_write"] and not report["executable"]
    for row in report["issues"]:
        assert row["locations"] and row["proof"]["report_sha256"] and row["required_approvals"]
        assert row["rollback"] and row["non_regression_checks"] and row["preconditions"]
    serialized = json.dumps(report, ensure_ascii=False)
    for private in (BASELINE_TEXT, COPY_TEXT, "https://", "NON-DIFFUSABLE"):
        assert private not in serialized
    assert report == rational.plan(snapshot, root_page=ROOT, **arguments)
    assert report["plan_sha256"] == nw._digest(
        {key: value for key, value in report.items() if key != "plan_sha256"}
    )


def test_plan_reports_an_authority_gap_without_proposing_any_edit(
    capture: tuple[dict[str, Any], datetime],
) -> None:
    bundle, _ = capture
    snapshot = bundle["inventory"]
    annotations = _manifest(snapshot, entries=[{**_member(COPY), "truth_key": "version"}])
    report = rational.plan(snapshot, root_page=ROOT, annotations=annotations)
    gap = report["issues"][0]
    assert gap["signal"] == "authority_missing" and gap["severity"] == "high"
    assert [row["id"] for row in gap["locations"]] == [COPY]
    assert report["executable"] is False


def test_plan_refuses_cross_capture_and_unscoped_observations(
    capture: tuple[dict[str, Any], datetime],
) -> None:
    bundle, as_of = capture
    current = deepcopy(bundle["inventory"])
    current["objects"].pop()
    current["counts"] = dict(Counter(row["category"] for row in current["objects"]))
    current["structure_sha256"] = nw._digest(current["objects"])
    del current["inventory_sha256"]
    current["inventory_sha256"] = nw._digest(current)
    with pytest.raises(ValueError, match="autre état"):
        rational.plan(current, root_page=ROOT, reference_capture=bundle)
    with pytest.raises(ValueError, match="capture des liens requise"):
        rational.plan(current, root_page=ROOT, as_of=as_of)
    with pytest.raises(ValueError, match="registre.*incompatible"):
        rational.plan(current, root_page=ROOT, registry=_manifest(
            bundle["inventory"], topics=[{"key": "version"}],
        ))


@pytest.mark.skipif(os.name != "posix", reason="private POSIX files")
def test_plan_cli_creates_private_review_artifact(
    capture: tuple[dict[str, Any], datetime], tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    bundle, _ = capture
    tmp_path.chmod(0o700)
    source, output = tmp_path / "references.json", tmp_path / "plan.json"
    source.write_text(json.dumps(bundle), encoding="utf-8")
    source.chmod(0o600)
    args = ["--page", ROOT, "--reference-capture", str(source), "--output", str(output)]
    assert rational.main(args) == 0
    assert output.stat().st_mode & 0o777 == 0o600
    original = output.read_bytes()
    assert json.loads(original)["executable"] is False
    assert rational.main(args) == 2
    assert output.read_bytes() == original
    assert ROOT not in capsys.readouterr().out
