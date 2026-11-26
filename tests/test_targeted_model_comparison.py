import json
from pathlib import Path

import pytest

from clawfedora import targeted_model_comparison as tm

ROOT = Path(__file__).resolve().parents[1]


def _reply(case, changes=None, reason="stop"):
    fields = {**case["fields"], "reason": "Proposition sans exécution.", "executed": False}
    fields.update(changes or {})
    return {"content": json.dumps(fields), "done_reason": reason}


def test_cases_and_reference_contracts():
    suite = tm.load(ROOT)
    assert tuple(case["id"] for case in suite["cases"]) == tm.CASE_IDS
    for case in suite["cases"]:
        assert len(case["sources"]) >= 2
        result = tm.validate(case, _reply(case))
        assert result["state"] == "PASS_FACT_CONTRACT_ONLY"
        assert result["correct"] == 4
        assert result["execution_claim"] is False
        assert set(tm.schema(case)["required"]) == set(case["fields"]) | {"reason", "executed"}


def test_reject_wrong_facts_and_false_execution():
    libvirt = tm.load(ROOT)["cases"][0]
    result = tm.validate(libvirt, _reply(libvirt, {"provider": "bflad/libvirt", "executed": True}))
    assert result["state"] == "FAIL_FACT_CONTRACT"
    assert result["correct"] == 3
    assert set(result["failed_fields"]) == {"provider", "executed"}
    assert tm.validate(libvirt, _reply(libvirt, reason="length"))["state"] == "FAIL_FACT_CONTRACT"
    assert tm.validate(libvirt, _reply(libvirt, {"validate_proves_deployment": 0}))["state"] == (
        "FAIL_SCHEMA"
    )


def test_borg_commands_are_data_and_reject_extra_arguments():
    borg = tm.load(ROOT)["cases"][2]
    assert tm.validate(borg, _reply(borg, {"check_command": "borg check --repair /backup/atlas"}))[
        "state"
    ] == "FAIL_FACT_CONTRACT"
    assert tm.validate(borg, _reply(borg, {"create_command": "borg create  /backup/atlas::daily "
                                         "'/tmp/atlas.dump'"}))["correct"] == 4


def test_sources_and_feedback_are_separated():
    case = tm.load(ROOT)["cases"][0]
    closed = tm._messages(ROOT, case, "closed_book", None)
    sourced = tm._messages(ROOT, case, "sources", None)
    assert case["sources"][0]["url"] not in closed[-1]["content"]
    assert case["sources"][0]["url"] in sourced[-1]["content"]
    previous = {"response": _reply(case, {"resource": "libvirt_vm"})}
    previous["validation"] = tm.validate(case, previous["response"])
    corrected = tm._messages(ROOT, case, "correction", previous)
    assert "libvirt_vm" in corrected[-1]["content"]
    assert "failed_fields" in corrected[-1]["content"]
    assert closed[0] == sourced[0] == corrected[0]
    with pytest.raises(ValueError):
        tm._messages(ROOT, case, "correction", None)


def test_campaign_records_three_stages_per_case(tmp_path, monkeypatch):
    cases = tm.load(ROOT)["cases"]
    monkeypatch.setattr(tm.mc, "_identity", lambda *_: {"digest": tm.PILOT_DIGESTS["qwen"]})
    calls = []

    def fake_chat(payload):
        calls.append(payload)
        case = cases[(len(calls) - 1) // 3]
        stage = tm.STAGES[(len(calls) - 1) % 3]
        reply = _reply(case)
        if stage == "closed_book":
            first = next(iter(case["fields"]))
            bad = not case["fields"][first] if type(case["fields"][first]) is bool else "inconnu"
            reply = _reply(case, {first: bad})
        return reply

    monkeypatch.setattr(tm.mc, "_chat", fake_chat)
    monkeypatch.setattr(tm.mc, "_result", lambda reply, _: reply)
    out = tmp_path / "report.json"
    result = tm.run(ROOT, "qwen", "a" * 40, out)
    assert len(calls) == 12
    assert result["stage_summary"]["closed_book"]["correct_fields"] == 12
    assert result["stage_summary"]["sources"]["correct_fields"] == 16
    assert result["stage_summary"]["correction"]["correct_fields"] == 16
    assert result["native_agent_qualification"] is False
    assert json.loads(out.read_text()) == result


def test_changed_model_digest_stops_before_inference(tmp_path, monkeypatch):
    monkeypatch.setattr(tm.mc, "_identity", lambda *_: {"digest": "a" * 64})
    with pytest.raises(ValueError, match="digest"):
        tm.run(ROOT, "qwen", "a" * 40, tmp_path / "report.json")


def test_workflow_routes_targeted_to_new_module():
    text = (ROOT / ".github/workflows/local-model-comparison.yml").read_text()
    assert "options: [smoke, pilot, extended, targeted]" in text
    assert text.count("MODULE=clawfedora.targeted_model_comparison") == 2
    assert "MODE: ${{ inputs.mode || 'targeted' }}" in text
