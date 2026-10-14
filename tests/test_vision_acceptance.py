from __future__ import annotations

from pathlib import Path
from typing import Any

from clawfedora.vision_acceptance import main, vision_smoke


def test_synthetic_image_and_scanned_pdf_generate_distinct_local_requests(
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    def fake_local_vision(
        repo: Path, runtime: Path, source: Path, name: str, *, maximum_output: int
    ) -> dict[str, Any]:
        assert repo == tmp_path
        assert runtime == tmp_path / "runtime"
        assert source.is_file() and source.stat().st_size < 2_000_000
        assert maximum_output == 12_000
        calls.append(source.suffix)
        return {"text": "Une forme rouge sur fond blanc."}

    report = vision_smoke(tmp_path, tmp_path / "runtime", vision=fake_local_vision)
    assert calls == [".png", ".pdf"]
    assert report["cloud_route_enabled_by_test"] is False
    assert report["manual_review_required"] is True
    assert len(report["results"]) == 2
    assert all(x["response_received"] for x in report["results"])


def test_visual_smoke_default_is_non_mutating(tmp_path: Path, capsys: Any) -> None:
    assert main(["--root", str(tmp_path), "--runtime-root", str(tmp_path / "not-created")]) == 0
    assert "requests_sent" in capsys.readouterr().out
    assert not (tmp_path / "not-created").exists()
