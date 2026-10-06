from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from clawfedora.agents import deploy_workspaces
from clawfedora.core_config import AGENT_IDS
from clawfedora.mentor import save_profile
from clawfedora.pedagogy_eval import MODEL, capture, cases, compare, main
from clawfedora.project_common import read_json, write_json
from clawfedora.project_worker import worker_lock

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def runtime(tmp_path: Path) -> Path:
    path = tmp_path / "runtime"
    deploy_workspaces(ROOT, path)
    write_json(
        path / "state/model-identities.json",
        {"models": {MODEL: {"digest": "a" * 64, "quantization_level": "Q4_K_M"}}},
    )
    save_profile(path, {"human_approved": True, "background": "Je sais diagnostiquer DNS."})
    return path


def response(_role: str, _prompt: str, _session: str) -> dict[str, Any]:
    return {"text": "<script>alert('unsafe')</script>\nPrévoir, observer puis diagnostiquer."}


def test_capture_preserves_notes_sessions_and_all_roles_without_claiming_learning(
    runtime: Path,
    tmp_path: Path,
) -> None:
    seen: list[tuple[str, str, str]] = []
    original = (runtime / "state/mentor.json").read_bytes()

    def runner(role: str, prompt: str, session: str) -> dict[str, Any]:
        seen.append((role, prompt, session))
        with pytest.raises(ValueError, match="worker"), worker_lock(runtime):
            pass
        return response(role, prompt, session)

    manifest = read_json(capture(ROOT, runtime, tmp_path / "before", runner=runner))
    assert len(seen) == 12 and {role for role, _, _ in seen} == set(AGENT_IDS)
    assert len({session for _, _, session in seen}) == 12
    assert all("Je sais diagnostiquer DNS." in prompt for _, prompt, _ in seen)
    assert manifest["origin"] == "simulated" and manifest["status"] == "CAPTURED"
    assert manifest["pedagogical_verdict"] == "NOT_REVIEWED"
    assert manifest["skill_acquired"] is False
    assert (runtime / "state/mentor.json").read_bytes() == original
    assert not (runtime / "projects").exists()


def pair(runtime: Path, tmp_path: Path) -> tuple[Path, Path]:
    before, after = tmp_path / "before", tmp_path / "after"
    capture(ROOT, runtime, before, ["ansible-fading"], runner=response)
    prompt = runtime / "workspaces/ingenieur-devops/AGENTS.md"
    prompt.write_text(prompt.read_text() + "\nNouvelle charte testée.\n")
    capture(ROOT, runtime, after, ["ansible-fading"], runner=response)
    return before, after


def test_blinded_report_escapes_answers_and_has_no_automatic_verdict(
    runtime: Path,
    tmp_path: Path,
) -> None:
    before, after = pair(runtime, tmp_path)
    report = compare(before, after, tmp_path / "review")
    document = report.read_text()
    assert "SIMULATION" in document and "&lt;script&gt;" in document
    assert "<script>" not in document and "zéro changement" in document
    mapping = read_json(report.parent / "correspondance.json")["ansible-fading"]
    assert set(mapping.values()) == {"before", "after"}
    assert read_json(report.parent / "provenance.json")["verdict"] == "NOT_REVIEWED"
    assert "Réponse A" in document and "Réponse B" in document


@pytest.mark.parametrize(
    "condition", ["model", "mentor_context_sha256", "origin", "deployed_prompts"]
)
def test_uncontrolled_conditions_or_identical_profiles_block_comparison(
    runtime: Path,
    tmp_path: Path,
    condition: str,
) -> None:
    before, after = pair(runtime, tmp_path)
    path = after / "manifest.json"
    payload = read_json(path)
    if condition == "origin":
        payload[condition] = "native-openclaw"
    elif condition == "deployed_prompts":
        payload["conditions"][condition] = read_json(before / "manifest.json")["conditions"][
            condition
        ]
    else:
        payload["conditions"][condition] = "different"
    write_json(path, payload)
    with pytest.raises(ValueError):
        compare(before, after, tmp_path / "review")
    assert not (tmp_path / "review").exists()


def test_partial_changed_or_tampered_captures_are_rejected(runtime: Path, tmp_path: Path) -> None:
    def mutate(role: str, prompt: str, session: str) -> dict[str, Any]:
        asset = runtime / "workspaces" / role / "AGENTS.md"
        asset.write_text(asset.read_text() + "change")
        return response(role, prompt, session)

    with pytest.raises(ValueError, match="conditions modifiées"):
        capture(ROOT, runtime, tmp_path / "partial", ["ansible-fading"], runner=mutate)
    assert read_json(tmp_path / "partial/manifest.json")["status"] == "INCOMPLETE"
    with pytest.raises(ValueError, match="incomplète"):
        compare(tmp_path / "partial", tmp_path / "partial", tmp_path / "review")
    before, after = pair(runtime, tmp_path)
    (before / "ansible-fading.json").write_text("{}")
    with pytest.raises(ValueError, match="capture modifiée"):
        compare(before, after, tmp_path / "review")


def test_case_selection_and_cli_errors_are_explicit(
    runtime: Path,
    tmp_path: Path,
    monkeypatch: Any,
    capsys: Any,
) -> None:
    assert len(cases(ROOT, ["ansible-fading"])) == 1
    with pytest.raises(ValueError):
        cases(ROOT, ["../escape"])
    with pytest.raises(ValueError):
        cases(ROOT, ["ansible-fading", "ansible-fading"])
    monkeypatch.setattr(
        "sys.argv",
        [
            "eval",
            "compare",
            "--before",
            str(tmp_path / "absent"),
            "--after",
            str(tmp_path / "absent"),
            "--output",
            str(tmp_path / "report"),
        ],
    )
    assert main() == 2
    assert "Évaluation non terminée" in capsys.readouterr().out
