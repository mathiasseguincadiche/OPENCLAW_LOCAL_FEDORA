"""Recapture an authorized edit without trusting its write result."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from clawfedora import notion_native_inventory as ni
from clawfedora import notion_non_regression as nr
from clawfedora import notion_write as nw

ROOT = "a" * 32
TARGET = "b" * 32
ARCHIVE = "c" * 32
LINK = "d" * 32
ATTACHMENT = "e" * 32
EXTRA = "f" * 32


def _block(ident: str, kind: str, **payload: Any) -> dict[str, Any]:
    return {"object": "block", "id": ident, "type": kind, kind: payload,
            "parent": {"type": "page_id", "page_id": ROOT}, "has_children": False}


def _text(ident: str, value: str, color: str = "default") -> dict[str, Any]:
    return _block(ident, "paragraph", color=color, rich_text=[{
        "type": "text", "text": {"content": value, "link": None}, "plain_text": value, "href": None,
    }])


def _plan(*, batch: bool = False, ident: str = TARGET) -> dict[str, Any]:
    base: dict[str, Any] = {"schema": 1, "page_id": ROOT, "created_at": "2026-11-27T12:00:00+00:00"}
    fields = {"block_id": ident, "old_sha256": "1" * 64, "new_text": "Version 2"}
    if batch:
        base.update(action="replace_plain_text_batch", inventory_sha256="2" * 64,
                    edits=[{**fields, "type": "paragraph"}])
    else:
        base.update(action="replace_plain_text", block_type="paragraph", **fields)
    return nr._seal(base, "manifest_sha256")


def _capture(
    monkeypatch: pytest.MonkeyPatch, *, changed: bool = False, text: str = "Version 2",
    regression: bool = False,
) -> dict[str, Any]:
    day = "28" if changed else "27"
    blocks = [
        _text(TARGET, text if changed else "version 2", "red" if regression else "default"),
        _text(ARCHIVE, "Historique revu" if regression else "Historique privé"),
        _block(LINK, "bookmark", url=f"https://example.invalid/{'other' if regression else 'ref'}"),
        _block(ATTACHMENT, "file", type="file", file={
            "url": f"https://example.invalid/signed?key={day}",
            "expiry_time": f"2026-11-{day}T15:00:00+00:00",
        }),
    ]
    if regression:
        blocks[1], blocks[2] = blocks[2], blocks[1]
        blocks.append(_text(EXTRA, "Ajout privé"))

    def get(path: str, params: dict[str, str]) -> dict[str, Any]:
        if path == f"/v1/pages/{ROOT}":
            return {"object": "page", "id": ROOT}
        assert path == f"/v1/blocks/{ROOT}/children"
        return {"results": blocks, "has_more": False, "next_cursor": None}

    monkeypatch.setattr(ni, "_get", get)
    monkeypatch.setattr(ni.time, "sleep", lambda _: None)
    recorded = nr.capture(ROOT)
    bundle = recorded["references"]
    inventory = bundle["inventory"]
    inventory["captured_at"] = f"2026-11-{day}T12:00:00+00:00"
    inventory["inventory_sha256"] = nw._digest(
        {key: value for key, value in inventory.items() if key != "inventory_sha256"}
    )
    bundle["capture_sha256"] = nw._digest(
        {key: value for key, value in bundle.items() if key != "capture_sha256"}
    )
    return nr._seal({key: value for key, value in recorded.items() if key != "capture_sha256"},
                    "capture_sha256")


def _prepare(before: dict[str, Any], approved: dict[str, Any]) -> dict[str, Any]:
    return nr.prepare(
        before, root_page=ROOT, page=ROOT, plan=approved,
        approved_manifest=approved["manifest_sha256"],
        annotations={"schema": 1, "root_page": ROOT,
                     "structure_sha256": before["references"]["inventory"]["structure_sha256"],
                     "entries": [{"id": ARCHIVE, "category": "block", "context": ["archive"]}]},
    )


@pytest.mark.parametrize("batch", [False, True])
def test_audit_confirms_exact_text_and_ignores_temporary_url_refresh(
    monkeypatch: pytest.MonkeyPatch, batch: bool,
) -> None:
    before = _capture(monkeypatch)
    after = _capture(monkeypatch, changed=True)
    expected = _prepare(before, _plan(batch=batch))
    report = nr.audit(before, after, expected, root_page=ROOT)
    assert report["verdict"] == "CONFORME_OBSERVABLE"
    assert report["expected_changes"] == [{"id": TARGET, "status": "observed"}]
    assert report["changed_references"] == []
    assert report["protected_checked"] == 1
    assert report["protected_changes"] == []
    for raw in (before, after, expected, report):
        serialized = json.dumps(raw, ensure_ascii=False)
        assert all(s not in serialized for s in ("Version 2", "Historique privé", "https://"))
    wrong_case = _capture(monkeypatch, changed=True, text="version 2")
    result = nr.audit(before, wrong_case, expected, root_page=ROOT)
    assert result["verdict"] == "NON_CONFORME"
    assert result["expected_changes"][0]["status"] == "expected_text_not_observed"


def test_audit_detects_protected_change_and_navigation_regression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = _capture(monkeypatch)
    after = _capture(monkeypatch, changed=True, regression=True)
    report = nr.audit(before, after, _prepare(before, _plan()), root_page=ROOT)
    assert report["verdict"] == "NON_CONFORME"
    assert report["expected_changes"][0]["status"] == "surroundings_changed"
    assert report["protected_changes"][0]["id"] == ARCHIVE
    assert report["changed_references"][0]["id"] == LINK
    assert report["unexpected_changes"]["added"][0]["id"] == EXTRA
    assert report["unexpected_changes"]["reordered"]


def test_audit_refuses_protected_target_tampered_and_replayed_proofs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = _capture(monkeypatch)
    after = _capture(monkeypatch, changed=True)
    with pytest.raises(ValueError, match="protégé"):
        _prepare(before, _plan(ident=ARCHIVE))
    approved = _plan()
    expected = _prepare(before, approved)
    with pytest.raises(ValueError, match="empreinte approuvée"):
        _prepare(before, {**approved, "new_text": "Autre"})
    with pytest.raises(ValueError, match="strictement postérieure"):
        nr.audit(before, before, expected, root_page=ROOT)
    modified = deepcopy(after)
    modified["text_witnesses"][0]["text_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="empreinte"):
        nr.audit(before, modified, expected, root_page=ROOT)


def test_audit_cli_writes_private_report_on_regression(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    before = _capture(monkeypatch)
    after = _capture(monkeypatch, changed=True, regression=True)
    expected = _prepare(before, _plan())
    tmp_path.chmod(0o700)
    paths = [tmp_path / f"{name}.json" for name in ("before", "after", "expectation", "report")]
    for path, body in zip(paths[:3], (before, after, expected), strict=True):
        path.write_text(json.dumps(body), encoding="utf-8")
        path.chmod(0o600)
    args = ["audit", "--page", ROOT, "--before", str(paths[0]), "--after", str(paths[1]),
            "--expectation", str(paths[2]), "--expectation-sha256", expected["expectation_sha256"],
            "--output", str(paths[3])]
    assert nr.main(args) == 1
    assert paths[3].stat().st_mode & 0o777 == 0o600
    assert json.loads(paths[3].read_text())["verdict"] == "NON_CONFORME"
    assert nr.main(args) == 2
