from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from reportlab.pdfgen import canvas

from clawfedora import chat_files, local_vision

ROOT = Path(__file__).resolve().parents[1]


def _runtime(tmp_path: Path) -> Path:
    runtime = tmp_path / "runtime"
    (runtime / "state/webui").mkdir(parents=True)
    (runtime / ".openclaw-fedora-runtime").touch()
    return runtime


def _enable(runtime: Path) -> None:
    path = runtime / local_vision.MARKER
    path.write_text(local_vision.APPROVAL + "\n")
    path.chmod(0o600)


def _png() -> bytes:
    target = io.BytesIO()
    Image.new("RGB", (24, 18)).save(target, format="PNG")
    return target.getvalue()


def _upload(runtime: Path, name: str, data: bytes) -> dict[str, Any]:
    path = runtime / "state/webui/data/uploads" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {
        "filename": name,
        "path": "/app/backend/data/uploads/" + name,
        "size": len(data),
    }


def test_default_vision_disabled_and_marker_must_be_private(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    assert local_vision.enabled(runtime) is False
    preview = chat_files.standalone_texts(
        runtime, [_upload(runtime, "image.png", _png())], repo_root=ROOT
    )
    assert "image-metadata-only" in preview
    assert "image-vision-local-qwen" not in preview
    _enable(runtime)
    assert local_vision.enabled(runtime)
    (runtime / local_vision.MARKER).chmod(0o644)
    with pytest.raises(ValueError, match="privée"):
        chat_files.standalone_texts(
            runtime, [_upload(runtime, "image.png", _png())], repo_root=ROOT
        )


def test_vision_uses_exact_local_model_and_preflight_under_worker_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime(tmp_path)
    _enable(runtime)
    upload = _upload(runtime, "photo.png", _png())
    calls: list[str] = []

    def fake_preflight(*_args: Any, **kwargs: Any) -> Any:
        assert kwargs == {"preflight_only": True}

        def check(role: str, prompt: str, session: str) -> dict[str, str]:
            assert role == "chef-operations"
            calls.append("preflight")
            return {"text": "", "route": "local"}

        return check

    def fake_http(endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        assert payload["model"] == "qwen3.5:9b-q4_K_M"
        calls.append(endpoint)
        if endpoint == "/api/show":
            return {"capabilities": ["completion", "vision"]}
        assert endpoint == "/api/chat"
        assert len(payload["messages"][1]["images"]) == 1
        assert payload["stream"] is False
        assert payload["think"] is False
        assert payload["options"]["num_predict"] == 512
        return {
            "model": "qwen3.5:9b-q4_K_M", "done": True,
            "message": {"role": "assistant", "content": "Une architecture réseau."},
        }

    monkeypatch.setattr(local_vision, "openclaw_runner", fake_preflight)
    monkeypatch.setattr(local_vision, "_local_json", fake_http)
    output = chat_files.standalone_texts(runtime, [upload], repo_root=ROOT)
    assert "image-vision-local-qwen" in output
    assert "Une architecture réseau." in output
    assert calls == ["preflight", "/api/show", "/api/chat"]


@pytest.mark.parametrize("show,chat", [
    ({"capabilities": ["completion"]}, None),
    ({"capabilities": ["vision"]}, {
        "model": "cloud-model", "done": True,
        "message": {"role": "assistant", "content": "secret"},
    }),
    ({"capabilities": ["vision"]}, {
        "model": "qwen3.5:9b-q4_K_M", "done": False,
        "message": {"role": "assistant", "content": "incomplete"},
    }),
    ({"capabilities": ["vision"]}, {
        "model": "qwen3.5:9b-q4_K_M", "done": True,
        "message": {"role": "tool", "content": "wrong role"},
    }),
])
def test_vision_refuses_unverified_capabilities_and_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    show: dict[str, Any], chat: dict[str, Any] | None,
) -> None:
    runtime = _runtime(tmp_path)
    _enable(runtime)
    calls: list[str] = []
    monkeypatch.setattr(local_vision, "openclaw_runner", lambda *_a, **_kw: (
        lambda *_args: {"route": "local", "text": ""}
    ))

    def mock(endpoint: str, _payload: dict[str, Any]) -> dict[str, Any]:
        calls.append(endpoint)
        return show if endpoint == "/api/show" else (chat or {})

    monkeypatch.setattr(local_vision, "_local_json", mock)
    with pytest.raises(ValueError):
        chat_files.standalone_texts(
            runtime, [_upload(runtime, "photo.png", _png())], repo_root=ROOT
        )
    assert calls[0] == "/api/show"
    assert all(route in {"/api/show", "/api/chat"} for route in calls)


def test_scanned_pdf_canary_is_local_only_and_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime(tmp_path)
    _enable(runtime)
    stream = io.BytesIO()
    report = canvas.Canvas(stream)
    report.showPage()
    report.save()
    pdf = _upload(runtime, "scan.pdf", stream.getvalue())
    monkeypatch.setattr(local_vision, "_scanned_pdf", lambda _path: [_png()])
    monkeypatch.setattr(local_vision, "openclaw_runner", lambda *_a, **_kw: (
        lambda *_args: {"route": "local", "text": ""}
    ))
    monkeypatch.setattr(local_vision, "_describe",
                        lambda *_args: "Texte visuel local, à confirmer")
    result = chat_files.standalone_texts(runtime, [pdf], repo_root=ROOT)
    assert "scanned-pdf-vision-local-qwen" in result
    assert "Texte visuel local, à confirmer" in result


def test_local_api_never_accepts_remote_hosts_or_arbitrary_paths() -> None:
    with pytest.raises(ValueError, match="non autorisée"):
        local_vision._local_json("https://api.openrouter.ai/", {})
    with pytest.raises(ValueError, match="non autorisée"):
        local_vision._local_json("/v1/chat/completions", {})



def test_opt_in_marker_rejects_links_and_non_private_content(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    marker = runtime / local_vision.MARKER
    other = tmp_path / "external"
    other.write_text(local_vision.APPROVAL + "\n")
    marker.symlink_to(other)
    with pytest.raises(ValueError, match="liée"):
        local_vision.enabled(runtime)
    marker.unlink()
    _enable(runtime)
    alias = tmp_path / "extra-link"
    alias.hardlink_to(marker)
    with pytest.raises(ValueError, match="privée"):
        local_vision.enabled(runtime)
    alias.unlink()
    marker.write_text(local_vision.APPROVAL + "\n" + ("X" * 200))
    with pytest.raises(ValueError, match="privée"):
        local_vision.enabled(runtime)
    marker.write_text(local_vision.APPROVAL)
    with pytest.raises(ValueError, match="non reconnue"):
        local_vision.enabled(runtime)


def test_marker_directory_symlinks_are_refused(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    _enable(runtime)
    alias = tmp_path / "alias"
    alias.symlink_to(runtime, target_is_directory=True)
    with pytest.raises(ValueError, match="lié"):
        local_vision.enabled(alias)


def test_ollama_local_request_is_only_fixed_post_with_no_proxies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[dict[str, Any]] = []

    class Response:
        status = 200

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def read(self, maximum: int) -> bytes:
            return b'{"capabilities":["vision"]}'[:maximum]

    class Opener:
        def open(self, request: Any, timeout: int) -> Response:
            seen.append({
                "url": request.full_url, "method": request.get_method(),
                "payload": json.loads(request.data), "timeout": timeout,
            })
            return Response()

    def factory(*handlers: Any) -> Opener:
        assert any(isinstance(x, local_vision._NoRedirect) for x in handlers)
        assert any(isinstance(x, local_vision.urllib.request.ProxyHandler)
                   and not x.proxies for x in handlers)
        return Opener()

    monkeypatch.setattr(local_vision.urllib.request, "build_opener", factory)
    result = local_vision._local_json("/api/show", {"model": "qwen3.5:9b-q4_K_M"})
    assert result["capabilities"] == ["vision"]
    assert seen == [{
        "url": "http://127.0.0.1:11434/api/show",
        "method": "POST",
        "payload": {"model": "qwen3.5:9b-q4_K_M"},
        "timeout": 12,
    }]
