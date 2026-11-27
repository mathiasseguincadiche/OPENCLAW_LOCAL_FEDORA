"""Canonical sources, copies and links are assessed within one Notion inventory."""
from __future__ import annotations

import json
import os
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from clawfedora import notion_native_inventory as ni
from clawfedora import notion_references as refs
from clawfedora import notion_source_truth as truth
from clawfedora import notion_write as nw

ROOT = "a" * 32
CANONICAL_PAGE = "b" * 32
COPY_PAGE = "c" * 32
CANONICAL = "d" * 32
DIVERGENT = "e" * 32
MATCHING = "f" * 32
POINTER = "1" * 32
CANONICAL_CHECK = "2" * 32
COPY_CHECK = "3" * 32


def _member(ident: str, category: str = "block") -> dict[str, str]:
    return {"category": category, "id": ident}


def _block(ident: str, kind: str, parent: str, **payload: Any) -> dict[str, Any]:
    return {"id": ident, "object": "block", "type": kind, kind: payload,
            "parent": {"type": "page_id", "page_id": parent}, "has_children": False}


def _paragraph(ident: str, parent: str, text: str) -> dict[str, Any]:
    return _block(ident, "paragraph", parent, rich_text=[{"plain_text": text}])


@pytest.fixture
def capture(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    lists = {
        ROOT: [_block(CANONICAL_PAGE, "child_page", ROOT), _block(COPY_PAGE, "child_page", ROOT),
               _paragraph(DIVERGENT, ROOT, "Version privée : 6.1"),
               _block(POINTER, "link_to_page", ROOT, type="page_id", page_id=CANONICAL_PAGE)],
        CANONICAL_PAGE: [_paragraph(CANONICAL, CANONICAL_PAGE, "Version privée : 6.2"),
                         _paragraph(CANONICAL_CHECK, CANONICAL_PAGE, "Vérification privée")],
        COPY_PAGE: [_paragraph(COPY_CHECK, COPY_PAGE, "Vérification privée"),
                    _paragraph(MATCHING, COPY_PAGE, "VERSION PRIVÉE : 6.2")],
    }

    def get(path: str, params: dict[str, str]) -> dict[str, Any]:
        _, _, kind, ident, *_ = path.split("/")
        if kind == "pages":
            return {"object": "page", "id": ident,
                    "parent": {"type": "page_id", "page_id": ROOT} if ident != ROOT else None}
        return {"results": lists[ident], "has_more": False, "next_cursor": None}

    monkeypatch.setattr(ni, "_get", get)
    monkeypatch.setattr(ni.time, "sleep", lambda _: None)
    recorded = refs.capture_references(ROOT)

    def reject_network(*args: Any) -> None:
        raise AssertionError("offline audit used Notion")

    monkeypatch.setattr(ni, "_get", reject_network)
    return recorded


def _manifest(snapshot: dict[str, Any], **payload: Any) -> dict[str, Any]:
    return {"schema": 1, "root_page": ROOT, "structure_sha256": snapshot["structure_sha256"],
            **payload}


def _topic(
    key: str, comparison: str, canonical: list[dict[str, str]], copies: list[dict[str, str]],
) -> dict[str, Any]:
    return {"key": key, "comparison": comparison, "canonical": canonical, "copies": copies}


def test_sources_compare_copies_preserve_context_and_distinguish_links(
    capture: dict[str, Any],
) -> None:
    snapshot = capture["inventory"]
    registry = _manifest(snapshot, topics=[
        _topic("version", "normalized_text", [_member(CANONICAL)],
               [_member(MATCHING), _member(DIVERGENT), _member(COPY_PAGE, "page")]),
        _topic("ordre", "ordered_direct_text", [_member(CANONICAL_PAGE, "page")],
               [_member(COPY_PAGE, "page"), _member(POINTER)]),
    ])
    annotations = _manifest(snapshot, entries=[
        {**_member(DIVERGENT), "context": ["archive"]},
        {**_member(CANONICAL_CHECK), "truth_key": "version"},
        {**_member(MATCHING), "truth_key": "inventaire"},
    ])
    report = truth.audit(snapshot, root_page=ROOT, registry=registry,
                         annotations=annotations, reference_capture=capture)
    topics = {item["key"]: item for item in report["subjects"]}
    assert topics["inventaire"]["authority"] == "missing"
    assert topics["inventaire"]["comparisons"][0]["status"] == "no_unique_authority"
    version = {item["id"]: item for item in topics["version"]["comparisons"]}
    assert version[MATCHING]["status"] == "matching_observable_evidence"
    assert version[DIVERGENT]["status"] == "divergent_observable_evidence"
    assert version[DIVERGENT]["protected_context"] == ["archive"]
    assert version[COPY_PAGE]["status"] == "insufficient_observable_evidence"
    assert version[CANONICAL_CHECK]["role"] == "candidate"
    assert topics["ordre"]["comparisons"][0]["status"] == "different_order"
    assert topics["ordre"]["pointers"] == [
        {"id": POINTER, "category": "block", "parent_id": ROOT, "position": 3,
         "declared_as_copy": True},
    ]
    assert report == truth.audit(snapshot, root_page=ROOT, registry=registry,
                                 annotations=annotations, reference_capture=capture)
    assert "Version privée" not in json.dumps(report, ensure_ascii=False)
    assert report["report_sha256"] == nw._digest(
        {k: v for k, v in report.items() if k != "report_sha256"}
    )


def test_conflicting_canonical_claims_do_not_pick_a_winner(capture: dict[str, Any]) -> None:
    snapshot = capture["inventory"]
    registry = _manifest(snapshot, topics=[
        _topic("version", "normalized_text", [_member(CANONICAL), _member(MATCHING)],
               [_member(DIVERGENT)]),
    ])
    topic = truth.audit(snapshot, root_page=ROOT, registry=registry)["subjects"][0]
    assert topic["authority"] == "conflicting"
    assert len(topic["canonical"]) == 2
    assert topic["comparisons"][0]["status"] == "no_unique_authority"


def test_property_profile_distinguishes_observed_type_counts() -> None:
    rows = {
        ("data_source", "x"): {"property_types": {"title": 1, "select": 1}},
        ("data_source", "y"): {"property_types": {"select": 1, "title": 1}},
        ("data_source", "z"): {"property_types": {"title": 1, "select": 2}},
    }
    canonical = truth._evidence(("data_source", "x"), "property_type_profile", rows, {})
    same = truth._evidence(("data_source", "y"), "property_type_profile", rows, {})
    different = truth._evidence(("data_source", "z"), "property_type_profile", rows, {})
    assert truth._comparison_status("declared", canonical, same) == "matching_observable_evidence"
    status = truth._comparison_status("declared", canonical, different)
    assert status == "divergent_observable_evidence"


@pytest.mark.parametrize("problem", ["wrong_hash", "foreign", "both_roles", "duplicate"])
def test_sources_refuse_wrong_capture_and_invalid_declarations(
    capture: dict[str, Any], problem: str,
) -> None:
    snapshot = capture["inventory"]
    topic = _topic("version", "normalized_text", [_member(CANONICAL)], [_member(MATCHING)])
    registry = _manifest(snapshot, topics=[topic])
    if problem == "wrong_hash":
        registry["structure_sha256"] = "0" * 64
    elif problem == "foreign":
        topic["copies"] = [_member("0" * 32)]
    elif problem == "both_roles":
        topic["copies"] = [_member(CANONICAL)]
    else:
        registry["topics"].append(topic)
    with pytest.raises(ValueError):
        truth.audit(snapshot, root_page=ROOT, registry=registry)


def test_sources_accept_legacy_inventory_without_new_fingerprints(capture: dict[str, Any]) -> None:
    legacy = deepcopy(capture["inventory"])
    legacy["schema"] = 1
    del legacy["inventory_sha256"]
    for row in legacy["objects"]:
        row.pop("observable_sha256", None)
        row.pop("properties_sha256", None)
    legacy["structure_sha256"] = nw._digest(legacy["objects"])
    registry = _manifest(legacy, topics=[
        _topic("version", "normalized_text", [_member(CANONICAL)], [_member(MATCHING)]),
    ])
    result = truth.audit(legacy, root_page=ROOT, registry=registry)
    assert result["counts_by_comparison"] == {"matching_observable_evidence": 1}


def test_sources_refuse_reference_capture_for_another_inventory_state(
    capture: dict[str, Any],
) -> None:
    snapshot = deepcopy(capture["inventory"])
    snapshot["objects"].pop()
    snapshot["counts"] = dict(Counter(row["category"] for row in snapshot["objects"]))
    snapshot["structure_sha256"] = nw._digest(snapshot["objects"])
    del snapshot["inventory_sha256"]
    snapshot["inventory_sha256"] = nw._digest(snapshot)
    registry = _manifest(snapshot, topics=[
        _topic("version", "normalized_text", [_member(CANONICAL)], [_member(MATCHING)]),
    ])
    with pytest.raises(ValueError, match="autre état"):
        truth.audit(snapshot, root_page=ROOT, registry=registry, reference_capture=capture)


@pytest.mark.skipif(os.name != "posix", reason="private POSIX files")
def test_sources_cli_private_output(
    capture: dict[str, Any], tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    tmp_path.chmod(0o700)
    snapshot = capture["inventory"]
    inventory, annotations, output = (tmp_path / name for name in ("inventory", "notes", "report"))
    inventory.write_text(json.dumps(snapshot), encoding="utf-8")
    inventory.chmod(0o600)
    annotations.write_text(json.dumps(_manifest(snapshot, entries=[
        {**_member(DIVERGENT), "truth_key": "version"},
    ])), encoding="utf-8")
    annotations.chmod(0o600)
    args = ["--page", ROOT, "--inventory", str(inventory), "--annotations", str(annotations),
            "--output", str(output)]
    assert truth.main(args) == 0
    assert output.stat().st_mode & 0o777 == 0o600
    assert json.loads(output.read_text())["counts_by_authority"] == {"missing": 1}
    assert truth.main(args) == 2
    assert ROOT not in capsys.readouterr().out
