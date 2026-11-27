"""Reference capture is bounded, redacted and scoped to the inventory."""
from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from clawfedora import notion_native_inventory as ni
from clawfedora import notion_references as refs
from clawfedora import notion_write as nw

ROOT = "a" * 32
PAGE = "b" * 32
SOURCE = "c" * 32
EXERCISE = "d" * 32
MISSING = "e" * 32
TABLE = "f" * 32
CELL = "1" * 32
IMAGE = "2" * 32
BOOKMARK = "3" * 32
PAGE_LINK = "4" * 32


def _block(
    ident: str, kind: str, parent: str, has_children: bool = False, **payload: Any,
) -> dict[str, Any]:
    parent_kind = "block_id" if parent == TABLE else "page_id"
    return {"id": ident, "object": "block", "type": kind, kind: payload,
            "parent": {"type": parent_kind, parent_kind: parent}, "has_children": has_children}


@pytest.fixture
def reference_capture(monkeypatch: pytest.MonkeyPatch) -> tuple[dict[str, Any], datetime]:
    now = datetime.now(UTC)
    items = {
        ROOT: [
            _block(PAGE, "child_page", ROOT),
            _block(
                SOURCE, "paragraph", ROOT, rich_text=[
                    {"mention": {"type": "page", "page": {"id": PAGE}}},
                    {"mention": {"type": "page", "page": {"id": MISSING}}},
                    {"href": f"https://app.notion.com/p/Exercice-{PAGE}#{EXERCISE}"},
                    {"href": f"https://app.notion.com/p/Mauvaise-page-{ROOT}#{EXERCISE}"},
                    {"text": {"link": {"url": "https://github.com/example/wiki/actions/runs/1"}}},
                    {"href": "https://github.com/example/wiki"},
                    {"mention": {"type": "link_preview", "link_preview": {
                        "url": "https://docs.github.com/en/actions",
                    }}},
                    {"href": "https://example.invalid/public"},
                    {"href": "https://example.invalid/private?token=NE-PAS-COPIER"},
                    {"href": "https://example.invalid/a#ancre-privee"},
                ],
            ),
            _block(IMAGE, "image", ROOT, type="file", file={
                "url": "https://signed.invalid/image?signature=SECRET",
                "expiry_time": (now - timedelta(minutes=3)).isoformat(),
            }),
            _block(BOOKMARK, "bookmark", ROOT, url="https://example.invalid/bookmark"),
            _block(PAGE_LINK, "link_to_page", ROOT, type="page_id", page_id=PAGE),
        ],
        PAGE: [
            _block(EXERCISE, "paragraph", PAGE, rich_text=[{"plain_text": "Texte privé"}]),
            _block(TABLE, "table", PAGE, has_children=True),
        ],
        TABLE: [_block(CELL, "table_row", TABLE, cells=[[{"href": f"#{EXERCISE}"}]])],
    }
    pages = {
        ROOT: {"id": ROOT, "object": "page"},
        PAGE: {"id": PAGE, "object": "page", "parent": {"type": "page_id", "page_id": ROOT},
               "cover": {"type": "file", "file": {
                   "url": "https://signed.invalid/cover",
                   "expiry_time": (now + timedelta(hours=1)).isoformat(),
               }}, "properties": {"documentation": {
                   "type": "url", "url": "https://developers.notion.com/reference/block",
               }}},
    }
    calls = []

    def get(path: str, params: dict[str, str]) -> dict[str, Any]:
        calls.append(path)
        _, _, kind, ident, *_ = path.split("/")
        if kind == "pages":
            return pages[ident]
        return {"results": items[ident], "has_more": False, "next_cursor": None}

    monkeypatch.setattr(ni, "_get", get)
    monkeypatch.setattr(ni.time, "sleep", lambda _: None)
    bundle = refs.capture_references(ROOT)
    assert set(calls) == {
        f"/v1/pages/{ROOT}", f"/v1/pages/{PAGE}", f"/v1/blocks/{ROOT}/children",
        f"/v1/blocks/{PAGE}/children", f"/v1/blocks/{TABLE}/children",
    }

    def reject_network(*args: Any) -> None:
        raise AssertionError("offline audit used Notion")

    monkeypatch.setattr(ni, "_get", reject_network)
    return bundle, now + timedelta(minutes=5)


def test_audit_resolves_notion_links_and_redacts_sensitive_urls(
    reference_capture: tuple[dict[str, Any], datetime],
) -> None:
    bundle, now = reference_capture
    report = refs.audit(bundle, root_page=ROOT, as_of=now)
    assert report["counts_by_status"] == {
        "block_anchor_page_mismatch": 1,
        "not_verified": 8,
        "outside_observed_inventory": 1,
        "present_in_inventory": 4,
        "temporary_url_expired": 1,
        "temporary_url_unexpired_unverified": 1,
    }
    rendered = json.dumps([bundle, report], ensure_ascii=False)
    for private in ("https://", "SECRET", "NE-PAS-COPIER", "Texte privé", "ancre-privee"):
        assert private not in rendered
    assert [row["slot"] for row in report["references"] if row["source_id"] == CELL] == ["cell"]
    classified = [row["kind"] for row in report["references"]]
    assert {"github", "github_ci", "documentation", "external", "redacted_url"} <= set(classified)
    assert report == refs.audit(bundle, root_page=ROOT, as_of=now)
    assert report["report_sha256"] == nw._digest(
        {k: v for k, v in report.items() if k != "report_sha256"}
    )


def test_audit_uses_scoped_operator_observations(
    reference_capture: tuple[dict[str, Any], datetime],
) -> None:
    bundle, now = reference_capture
    sources = {
        row["kind"]: row["reference_id"] for row in bundle["references"]
        if row["kind"] in refs.EXTERNAL
    }
    missing = next(row["reference_id"] for row in bundle["references"]
                   if row["target_id"] == MISSING)
    expected = {"github": (404, "unknown", "absence_unconfirmed"),
                "github_ci": (403, "unknown", "access_restricted"),
                "documentation": (410, "public", "broken_confirmed_public"),
                "external": (429, "unknown", "network_or_server_limited")}
    evidence = [{
        "reference_id": sources[kind], "observed_at": now.isoformat(), "result": "http",
        "status_code": code, "visibility": visibility,
    } for kind, (code, visibility, _) in expected.items()]
    evidence.append({"reference_id": missing, "observed_at": now.isoformat(),
                     "result": "missing_confirmed"})
    observations = {"schema": 1, "capture_sha256": bundle["capture_sha256"], "entries": evidence}
    report = refs.audit(bundle, root_page=ROOT, as_of=now, observations=observations)
    statuses = {row["reference_id"]: row["status"] for row in report["references"]}
    assert all(statuses[sources[kind]] == result for kind, (_, _, result) in expected.items())
    assert statuses[missing] == "broken_confirmed_manual"
    with pytest.raises(ValueError, match="hors périmètre ou répétée"):
        refs.audit(bundle, root_page=ROOT, as_of=now,
                   observations={**observations, "entries": evidence + evidence[:1]})
    with pytest.raises(ValueError, match="hors fenêtre"):
        refs.audit(bundle, root_page=ROOT, as_of=now - timedelta(seconds=1),
                   observations=observations)


def test_audit_refuses_tampered_references_and_wrong_scope(
    reference_capture: tuple[dict[str, Any], datetime],
) -> None:
    bundle, now = reference_capture
    damaged = deepcopy(bundle)
    damaged["references"][0]["source_id"] = MISSING
    with pytest.raises(ValueError, match="source.*hors périmètre"):
        refs.audit(damaged, root_page=ROOT, as_of=now)
    damaged = deepcopy(bundle)
    damaged["references"].pop()
    with pytest.raises(ValueError, match="empreinte de capture"):
        refs.audit(damaged, root_page=ROOT, as_of=now)
    with pytest.raises(ValueError, match="hors périmètre"):
        refs.audit(bundle, root_page=MISSING, as_of=now)


@pytest.mark.skipif(os.name != "posix", reason="private POSIX files")
def test_audit_cli_keeps_report_private(
    tmp_path: Path, reference_capture: tuple[dict[str, Any], datetime],
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle, now = reference_capture
    tmp_path.chmod(0o700)
    source, output = tmp_path / "references.json", tmp_path / "audit.json"
    source.write_text(json.dumps(bundle), encoding="utf-8")
    source.chmod(0o600)
    args = ["audit", "--page", ROOT, "--capture-file", str(source), "--output", str(output),
            "--as-of", now.isoformat()]
    assert refs.main(args) == 0
    assert output.stat().st_mode & 0o777 == 0o600
    assert json.loads(output.read_text())["remote_write"] is False
    assert refs.main(args) == 2
    assert ROOT not in capsys.readouterr().out
