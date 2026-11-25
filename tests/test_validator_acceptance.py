"""Synthetic smoke contract; CI does not launch a container."""

from pathlib import Path

import pytest

from clawfedora import devops_lab, validator_acceptance as acceptance

IMAGE = "sha256:" + "a" * 64


def test_smoke_plan_never_runs_lab(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(acceptance, "run_lab", lambda *_a, **_kw: pytest.fail("no lab"))
    report = acceptance.qualify(None, apply=False)
    assert set(acceptance.CASES) == devops_lab.TOOLS
    assert len(report["cases"]) == 16
    assert all(row["status"] == "NOT_RUN" for row in report["cases"])
    assert report["qualified"] is False and report["approved"] is False
    with pytest.raises(devops_lab.LabRefusal, match="immuable"):
        acceptance.qualify("latest", apply=True)


@pytest.mark.parametrize("failure", [None, 124, 125, 126, 127, 0])
def test_smoke_never_confuses_negative_or_runtime_failure_with_qualification(
    monkeypatch: pytest.MonkeyPatch, failure: int | None,
) -> None:
    seen: list[str] = []

    def fake_lab(root: Path, tool: str, image: str | None, apply: bool) -> int:
        assert image == IMAGE and apply
        name, good, bad = acceptance.CASES[tool]
        manifest = devops_lab.snapshot_manifest(root)
        assert manifest == (Path(name),)
        assert devops_lab.command_for(tool, root, manifest)
        seen.append(tool)
        if (root / name).read_text() == good:
            return 0
        assert (root / name).read_text() == bad
        return 1 if failure is None else failure

    monkeypatch.setattr(acceptance, "run_lab", fake_lab)
    result = acceptance.qualify(IMAGE, apply=True)
    assert len(seen) == 16 and result["qualified"] is False and result["approved"] is False
    assert result["status"] == ("SMOKE_REVIEW_REQUIRED" if failure is None else "SMOKE_FAILED")
    negatives = [row for row in result["cases"] if row["case"] == "negative"]
    if failure is None:
        assert all(row["status"] == "REVIEW_NEGATIVE_LOG" for row in negatives)
