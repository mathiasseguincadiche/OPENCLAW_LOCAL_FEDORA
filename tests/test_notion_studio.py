"""Studio plans are read-only until approved; all API operations are mocked."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from clawfedora import notion_studio as ns
from clawfedora import notion_write as nw

PARENT = "1" * 32
HOME = "2" * 32
CHILD = "3" * 32
UPLOAD = "4" * 32
DB = "5" * 32
SOURCE = "6" * 32
ROW = "7" * 32
VIEW = "8" * 32


def _setup(tmp_path: Path) -> tuple[Path, Path, Path]:
    media = tmp_path / "media"
    media.mkdir()
    Image.new("RGB", (100, 100), "navy").save(media / "cover.png")
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({
        "home": {"title": "Studio", "cover_file": "cover.png",
                 "blocks": [{"type": "paragraph", "text": "Projet fictif"}]},
        "pages": [{"title": "Comprendre", "blocks": [
            {"type": "paragraph", "text": "Lire le mécanisme"},
        ], "images": [{"file": "cover.png", "caption": "Illustration"}]}],
        "tracker": {"title": "Parcours", "activities": ["Découvrir"], "views": ["gallery"]},
    }, ensure_ascii=False))
    return spec, media, tmp_path / "plan.json"


class FakeAPI:
    def __init__(self) -> None:
        self.writes: list[str] = []
        self.pages: dict[str, dict[str, Any]] = {}
        self.children: dict[str, list[dict[str, Any]]] = {}
        self.database: dict[str, Any] = {}
        self.view: dict[str, Any] = {}
        self.upload: dict[str, Any] = {}
        self.stamp = "2026-11-25T20:00:00Z"
        self.fail_view = False

    def __call__(self, method, resource, *, body=None, binary=None, content_type=None):
        if method == "POST":
            self.writes.append(resource)
            if resource == "/v1/file_uploads":
                self.upload = {**body, "object": "file_upload", "id": UPLOAD,
                               "status": "pending"}
                return self.upload
            if resource.endswith("/send"):
                assert b"Content-Disposition: form-data;" in binary
                assert b"cover.png" in binary and "multipart/form-data" in content_type
                data = binary.split(b"\r\n\r\n", 1)[1].rsplit(b"\r\n--", 1)[0]
                self.upload.update(status="uploaded", content_length=len(data))
                return self.upload
            if resource == "/v1/pages":
                if body["parent"]["type"] == "data_source_id":
                    ident = ROW
                else:
                    ident = HOME if body["parent"]["page_id"] == PARENT else CHILD
                self.pages[ident] = {"id": ident, "in_trash": False, **body}
                if body.get("cover", {}).get("type") == "file_upload":
                    self.pages[ident]["cover"] = {
                        "type": "file", "file": {"url": "https://example.invalid/signed"},
                    }
                blocks = []
                for block in body.get("children", []):
                    kind = block["type"]
                    value = block[kind]
                    if kind == "image":
                        value = {"type": "file", "file": {"url": "https://example.invalid"},
                                 "caption": value["caption"]}
                    blocks.append({"id": "9" * 32, "type": kind, kind: value,
                                   "has_children": False})
                self.children[ident] = blocks
                return {"id": ident}
            if resource == "/v1/databases":
                self.database = {"id": DB, **body, "data_sources": [{"id": SOURCE}]}
                return {"id": DB}
            if resource == "/v1/views":
                if self.fail_view:
                    raise nw.NotionWriteError("résultat ambigu")
                self.view = {"id": VIEW, **body, "parent": {
                    "type": "database_id", "database_id": DB,
                }}
                return {"id": VIEW}
            raise AssertionError(resource)
        assert method == "GET"
        if resource == f"/v1/pages/{PARENT}":
            return {"id": PARENT, "parent": {"type": "workspace"}, "in_trash": False,
                    "last_edited_time": self.stamp}
        if resource.startswith("/v1/pages/"):
            return self.pages[resource.rsplit("/", 1)[1]]
        if resource.startswith("/v1/blocks/"):
            return {"results": self.children[resource.split("/")[3]], "has_more": False}
        if resource == f"/v1/databases/{DB}":
            return self.database
        if resource == f"/v1/data_sources/{SOURCE}":
            return {"id": SOURCE, "properties": {
                k: {"type": next(iter(v)), **v} for k, v in ns.FIELDS.items()
            }}
        if resource == f"/v1/views/{VIEW}":
            return self.view
        if resource == f"/v1/file_uploads/{UPLOAD}":
            return {**self.upload, "expiry_time": None}
        raise AssertionError(resource)


def test_studio_plan_and_apply(tmp_path, monkeypatch):
    spec, media, plan = _setup(tmp_path)
    api = FakeAPI()
    monkeypatch.setattr(ns, "_request", api)
    result = ns.preview(PARENT, spec, media, plan)
    assert not result["remote_writes"] and not api.writes
    html = Path(result["preview_file"])
    assert html.stat().st_mode & 0o077 == 0
    assert "data:image/png;base64," in html.read_text()
    assert "aucune publication" in html.read_text()
    assert "<script" not in html.read_text()
    assert result["assets"][0]["sha256"] == hashlib.sha256(
        (media / "cover.png").read_bytes(),
    ).hexdigest()
    with pytest.raises(nw.NotionWriteError, match="approbation"):
        ns.apply(plan, PARENT, "0" * 64)
    assert not api.writes
    receipt = ns.apply(plan, PARENT, result["manifest_sha256"])
    assert receipt["root_page_id"] == HOME
    assert receipt["page_ids"] == [CHILD]
    assert receipt["tracker"]["data_source_id"] == SOURCE
    assert receipt["tracker"]["views"] == [{"id": VIEW, "type": "gallery"}]
    assert receipt["assets"][0]["upload_id"] == UPLOAD
    assert "signed" not in json.dumps(receipt)
    assert api.writes.count("/v1/file_uploads") == 1
    assert api.writes.count("/v1/pages") == 3
    with pytest.raises(nw.NotionWriteError, match="déjà tenté"):
        ns.apply(plan, PARENT, result["manifest_sha256"])


def test_changed_asset_and_parent_refused_before_write(tmp_path, monkeypatch):
    spec, media, plan = _setup(tmp_path)
    api = FakeAPI()
    monkeypatch.setattr(ns, "_request", api)
    result = ns.preview(PARENT, spec, media, plan)
    data = (media / "cover.png").read_bytes()
    Image.new("RGB", (100, 100), "green").save(media / "cover.png")
    with pytest.raises(nw.NotionWriteError, match="média modifié"):
        ns.apply(plan, PARENT, result["manifest_sha256"])
    (media / "cover.png").write_bytes(data)
    api.stamp = "2026-11-25T21:00:00Z"
    with pytest.raises(nw.NotionWriteError, match="parent modifié"):
        ns.apply(plan, PARENT, result["manifest_sha256"])
    assert not api.writes


def test_partial_creation_never_retries(tmp_path, monkeypatch):
    spec, media, plan = _setup(tmp_path)
    api = FakeAPI()
    api.fail_view = True
    monkeypatch.setattr(ns, "_request", api)
    result = ns.preview(PARENT, spec, media, plan)
    with pytest.raises(nw.NotionWriteError, match="ambigu"):
        ns.apply(plan, PARENT, result["manifest_sha256"])
    root = plan.with_name(plan.name + ".root.json")
    assert json.loads(root.read_text())["root_page_id"] == HOME
    assert not plan.with_name(plan.name + ".verified.json").exists()
    count = len(api.writes)
    with pytest.raises(nw.NotionWriteError, match="déjà tenté"):
        ns.apply(plan, PARENT, result["manifest_sha256"])
    assert len(api.writes) == count


@pytest.mark.parametrize("name", ["../secret.png", "bad.svg", "quote\n.png"])
def test_asset_name_rejected(tmp_path, name):
    with pytest.raises(nw.NotionWriteError):
        ns._read_asset(tmp_path, name)


def test_link_and_disguised_media_refused(tmp_path):
    actual = tmp_path / "actual.png"
    actual.write_text("not an image")
    linked = tmp_path / "linked.png"
    linked.symlink_to(actual)
    with pytest.raises(nw.NotionWriteError, match="lié"):
        ns._read_asset(tmp_path, linked.name)
    with pytest.raises(nw.NotionWriteError, match="non lisible"):
        ns._read_asset(tmp_path, actual.name)


def test_request_rejects_other_endpoints():
    for method, endpoint in [
        ("DELETE", f"/v1/pages/{PARENT}"), ("POST", "/v1/search"),
        ("GET", "https://example.invalid"), ("PATCH", f"/v1/pages/{PARENT}"),
    ]:
        with pytest.raises(nw.NotionWriteError, match="endpoint"):
            ns._request(method, endpoint)

def test_preview_escapes_untrusted_text(tmp_path, monkeypatch):
    spec, media, plan = _setup(tmp_path)
    raw = json.loads(spec.read_text())
    raw["home"]["title"] = '<script>alert("test")</script>'
    spec.write_text(json.dumps(raw))
    monkeypatch.setattr(ns, "_request", FakeAPI())
    result = ns.preview(PARENT, spec, media, plan)
    html = Path(result["preview_file"]).read_text()
    assert "&lt;script&gt;" in html
    assert "<script>" not in html
