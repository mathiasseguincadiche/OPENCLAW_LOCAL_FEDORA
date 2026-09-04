from __future__ import annotations

import json
from pathlib import Path

import pytest

from clawfedora import optimization_cli
from clawfedora.optimization import ComparisonReport
from clawfedora.runtime_candidate import RuntimeFiles

ROOT = Path(__file__).resolve().parents[1]


def _report(kind: str = "runtime") -> ComparisonReport:
    return ComparisonReport(
        kind=kind,
        candidate_id="candidate",
        verdict="KEEP_BASELINE",
        aggregate_improvement_pct=1.0,
        per_model_change_pct={"qwen-max": 1.0},
        reasons=("below-target",),
        baseline_runs=("b1", "b2", "b3"),
        candidate_runs=("c1", "c2", "c3"),
    )


def test_root_and_paths_helpers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    explicit = optimization_cli._root(str(tmp_path))
    assert explicit == tmp_path.resolve()
    monkeypatch.setenv("OPENCLAW_LOCAL_FEDORA_REPO", str(tmp_path / "repo"))
    assert optimization_cli._root(None) == (tmp_path / "repo").resolve()
    monkeypatch.delenv("OPENCLAW_LOCAL_FEDORA_REPO")
    assert optimization_cli._root(None) == ROOT
    assert optimization_cli._paths([str(tmp_path / "a"), str(tmp_path / "b")]) == [
        (tmp_path / "a").resolve(),
        (tmp_path / "b").resolve(),
    ]


def test_validate_cli_text_and_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        optimization_cli,
        "validate_optimization_contracts",
        lambda _root: ((), ("warning",)),
    )
    code = optimization_cli.main(
        ["--root", str(ROOT), "--runtime-root", str(tmp_path), "validate"]
    )
    assert code == 0
    output = capsys.readouterr().out
    assert "WARN warning" in output
    assert "L6_CONTRACT_RESULT=PASS" in output

    monkeypatch.setattr(
        optimization_cli,
        "validate_optimization_contracts",
        lambda _root: (("failure",), ()),
    )
    code = optimization_cli.main(
        [
            "--root",
            str(ROOT),
            "--runtime-root",
            str(tmp_path),
            "validate",
            "--json",
        ]
    )
    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["verdict"] == "FAIL"
    assert payload["failures"] == ["failure"]


def test_stage_models_cli_success_and_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        optimization_cli,
        "stage_ollama_artifacts",
        lambda _repo, _runtime, apply: {"apply": apply, "models": {}},
    )
    code = optimization_cli.main(
        [
            "--root",
            str(ROOT),
            "--runtime-root",
            str(tmp_path),
            "stage-models",
            "--apply",
            "--json",
        ]
    )
    assert code == 0
    output = capsys.readouterr().out
    assert '"apply": true' in output
    assert "L6_STAGE_RESULT=PASS apply=true" in output

    def fail_stage(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise ValueError("boom")

    monkeypatch.setattr(optimization_cli, "stage_ollama_artifacts", fail_stage)
    code = optimization_cli.main(
        ["--root", str(ROOT), "--runtime-root", str(tmp_path), "stage-models"]
    )
    assert code == 2
    assert "L6_STAGE_RESULT=FAIL error=boom" in capsys.readouterr().out


def test_runtime_files_cli_success_and_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    files = RuntimeFiles(
        backend="llama-cpp-vulkan",
        server=tmp_path / "server",
        preset=tmp_path / "preset",
        launcher=tmp_path / "launcher",
        unit_name="openclaw-llama-vulkan.service",
        unit_path=tmp_path / "unit",
        endpoint="http://127.0.0.1:8081/v1",
    )
    monkeypatch.setattr(
        optimization_cli,
        "prepare_runtime_files",
        lambda *_args, **_kwargs: files,
    )
    code = optimization_cli.main(
        [
            "--root",
            str(ROOT),
            "--runtime-root",
            str(tmp_path),
            "runtime-files",
            "--backend",
            "llama-cpp-vulkan",
            "--unit-dir",
            str(tmp_path / "units"),
            "--json",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["unit_name"] == "openclaw-llama-vulkan.service"
    assert payload["endpoint"] == "http://127.0.0.1:8081/v1"

    monkeypatch.setattr(
        optimization_cli,
        "prepare_runtime_files",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("bad runtime")),
    )
    code = optimization_cli.main(
        [
            "--root",
            str(ROOT),
            "--runtime-root",
            str(tmp_path),
            "runtime-files",
            "--backend",
            "llama-cpp-vulkan",
            "--unit-dir",
            str(tmp_path / "units"),
        ]
    )
    assert code == 2
    assert "L6_RUNTIME_FILES_RESULT=FAIL" in capsys.readouterr().out


def test_snapshot_cli_success_and_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    evidence = tmp_path / "snapshot.json"
    monkeypatch.setattr(
        optimization_cli,
        "run_performance_snapshot",
        lambda *_args, **_kwargs: evidence,
    )
    code = optimization_cli.main(
        [
            "--root",
            str(ROOT),
            "--runtime-root",
            str(tmp_path),
            "snapshot",
            "--backend",
            "ollama-vulkan",
            "--endpoint",
            "http://127.0.0.1:11434",
            "--kind",
            "runtime",
            "--candidate-id",
            "baseline",
            "--output",
            str(evidence),
        ]
    )
    assert code == 0
    assert f"evidence={evidence.resolve()}" in capsys.readouterr().out

    monkeypatch.setattr(
        optimization_cli,
        "run_performance_snapshot",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("snapshot failed")),
    )
    code = optimization_cli.main(
        [
            "--root",
            str(ROOT),
            "--runtime-root",
            str(tmp_path),
            "snapshot",
            "--backend",
            "ollama-vulkan",
            "--endpoint",
            "http://127.0.0.1:11434",
            "--kind",
            "runtime",
            "--candidate-id",
            "baseline",
            "--output",
            str(evidence),
        ]
    )
    assert code == 2
    assert "L6_SNAPSHOT_RESULT=FAIL" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("command", "attribute", "kind"),
    [
        ("compare-runtime", "compare_runtime", "runtime"),
        ("compare-kernel", "compare_kernel", "kernel"),
        ("compare-challenger", "compare_model_challenger", "model-challenger"),
    ],
)
def test_compare_cli_dispatches_all_comparators(
    command: str,
    attribute: str,
    kind: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _report(kind)
    monkeypatch.setattr(optimization_cli, attribute, lambda *_args: report)
    decision = tmp_path / f"{command}.json"
    monkeypatch.setattr(
        optimization_cli,
        "write_decision",
        lambda _report, _output: decision,
    )
    code = optimization_cli.main(
        [
            "--root",
            str(ROOT),
            "--runtime-root",
            str(tmp_path),
            command,
            "--baseline",
            str(tmp_path / "b1.json"),
            "--candidate",
            str(tmp_path / "c1.json"),
            "--output",
            str(decision),
        ]
    )
    assert code == 0
    output = capsys.readouterr().out
    assert '"verdict": "KEEP_BASELINE"' in output
    assert f"decision={decision}" in output


def test_compare_cli_reports_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        optimization_cli,
        "compare_runtime",
        lambda *_args: (_ for _ in ()).throw(ValueError("comparison failed")),
    )
    code = optimization_cli.main(
        [
            "--root",
            str(ROOT),
            "--runtime-root",
            str(tmp_path),
            "compare-runtime",
            "--baseline",
            str(tmp_path / "b.json"),
            "--candidate",
            str(tmp_path / "c.json"),
            "--output",
            str(tmp_path / "decision.json"),
        ]
    )
    assert code == 2
    assert "L6_COMPARE_RESULT=FAIL error=comparison failed" in capsys.readouterr().out
