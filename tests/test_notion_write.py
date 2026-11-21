"""Offline security and behavior checks of the controlled Notion revision workflow."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from clawfedora import notion_write as nw

PAGE = "a" * 32
BLOCK = "b" * 32
OTHER_PAGE = "c" * 32


def _stub(monkeypatch: pytest.MonkeyPatch, *, source: str = "Texte initial") -> dict[str, Any]:
    state: dict[str, Any] = {"value": source, "edited": "2026-11-21T10:00:00Z", "patches": []}

    def api(
        method: str, resource: str, *, write: bool = False,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if resource == f"/v1/pages/{PAGE}" and method == "GET":
            return {"id": PAGE, "archived": False}
        if resource == f"/v1/blocks/{BLOCK}" and method == "GET":
            return {
                "id": BLOCK, "type": "paragraph", "archived": False,
                "has_children": False, "last_edited_time": state["edited"],
                "parent": {"type": "page_id", "page_id": PAGE},
                "paragraph": {
                    "rich_text": [{
                        "type": "text", "plain_text": state["value"], "href": None,
                        "text": {"content": state["value"], "link": None},
                        "annotations": {
                            "bold": False, "italic": False, "underline": False,
                            "strikethrough": False, "code": False, "color": "default",
                        },
                    }],
                },
            }
        if resource == f"/v1/blocks/{BLOCK}" and method == "PATCH":
            assert write is True
            assert body is not None
            state["patches"].append(body)
            state["value"] = body["paragraph"]["rich_text"][0]["text"]["content"]
            state["edited"] = "2026-11-21T10:03:00Z"
            return {"id": BLOCK}
        pytest.fail("unexpected endpoint or verb")

    monkeypatch.setattr(nw, "_request", api)
    return state


def test_plan_displays_diff_but_never_writes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = _stub(monkeypatch)
    target = tmp_path / "notion-plan.json"
    result = nw.preview(PAGE, BLOCK, "Texte corrigé", target)
    assert result["mode"] == "PREVIEW_ONLY"
    assert "-Texte initial" in result["diff"]
    assert "+Texte corrigé" in result["diff"]
    assert not state["patches"]
    assert target.stat().st_mode & 0o077 == 0
    plan = json.loads(target.read_text(encoding="utf-8"))
    assert plan["new_text"] == "Texte corrigé"
    assert "Texte initial" not in target.read_text(encoding="utf-8")
    assert len(plan["manifest_sha256"]) == 64


def test_exact_approval_and_single_use(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = _stub(monkeypatch)
    path = tmp_path / "plan.json"
    plan = nw.preview(PAGE, BLOCK, "Version relue", path)
    with pytest.raises(nw.NotionWriteError, match="approbation"):
        nw.apply(path, PAGE, "0" * 64)
    assert state["patches"] == []
    result = nw.apply(path, PAGE, plan["manifest_sha256"])
    assert result["mode"] == "NOTION_BLOCK_UPDATED_VERIFIED"
    assert state["value"] == "Version relue"
    assert len(state["patches"]) == 1
    with pytest.raises(nw.NotionWriteError, match="déjà présent"):
        nw.apply(path, PAGE, plan["manifest_sha256"])
    assert len(state["patches"]) == 1


def test_remote_drift_refuses_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = _stub(monkeypatch)
    plan_file = tmp_path / "plan.json"
    plan = nw.preview(PAGE, BLOCK, "Nouveau", plan_file)
    state["edited"] = "2026-11-21T10:01:00Z"
    with pytest.raises(nw.NotionWriteError, match="modifié"):
        nw.apply(plan_file, PAGE, plan["manifest_sha256"])
    assert state["patches"] == []


def test_foreign_page_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub(monkeypatch)
    with pytest.raises(nw.NotionWriteError, match="non direct"):
        nw.preview(OTHER_PAGE, BLOCK, "Nouveau", tmp_path / "plan.json")


def test_formatted_block_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(method: str, resource: str, **_kw: Any) -> dict[str, Any]:
        if resource == f"/v1/pages/{PAGE}":
            return {"id": PAGE, "archived": False}
        return {
            "id": BLOCK, "type": "paragraph", "archived": False,
            "parent": {"type": "page_id", "page_id": PAGE}, "has_children": False,
            "paragraph": {"rich_text": [{
                "type": "text", "plain_text": "Important",
                "text": {"content": "Important", "link": None}, "href": None,
                "annotations": {"bold": True},
            }]},
        }

    monkeypatch.setattr(nw, "_request", fake)
    with pytest.raises(nw.NotionWriteError, match="formatage"):
        nw.preview(PAGE, BLOCK, "Réécrit", tmp_path / "plan.json")


def test_tampered_plan_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = _stub(monkeypatch)
    path = tmp_path / "plan.json"
    plan = nw.preview(PAGE, BLOCK, "Version A", path)
    content = json.loads(path.read_text(encoding="utf-8"))
    content["new_text"] = "Version B"
    path.write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(nw.NotionWriteError, match="intégrité"):
        nw.apply(path, PAGE, plan["manifest_sha256"])
    assert state["patches"] == []


def test_cli_dry_refusal_cannot_call_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(nw, "_request", lambda *_a, **_k: pytest.fail("network"))
    assert nw.main([
        "apply", "--plan", str(tmp_path / "missing.json"), "--approve-page", PAGE,
        "--approve-manifest", "0" * 64,
    ]) == 2
    assert "REFUSED_OR_INCOMPLETE" in capsys.readouterr().out


def test_no_redirect_and_no_unscoped_http(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTION_API_TOKEN", "fake")
    with pytest.raises(nw.NotionWriteError, match="endpoint"):
        nw._request("GET", "/v1/users/me")
    with pytest.raises(nw.NotionWriteError, match="méthode"):
        nw._request("DELETE", f"/v1/blocks/{BLOCK}")


def test_no_unapproved_token_in_previews(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub(monkeypatch)
    monkeypatch.setenv("NOTION_WRITE_TOKEN", "supersecret")
    plan = nw.preview(PAGE, BLOCK, "Version", tmp_path / "plan.json")
    assert "supersecret" not in json.dumps(plan)
    assert "supersecret" not in (tmp_path / "plan.json").read_text(encoding="utf-8")
