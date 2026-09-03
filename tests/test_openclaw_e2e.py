from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from clawfedora import openclaw_e2e
from clawfedora.core_config import AGENT_IDS

ROOT = Path(__file__).resolve().parents[1]


def _payload(text: str, provider: str = "ollama") -> dict[str, object]:
    return {
        "status": "ok",
        "result": {
            "meta": {
                "error": {},
                "livenessState": "alive",
                "finalAssistantVisibleText": text,
                "provider": provider,
            }
        },
    }


def test_l4_dry_run_is_linux_local_and_complete() -> None:
    payload = openclaw_e2e.dry_run("ollama-vulkan")
    assert payload["verdict"] == "PASS"
    assert payload["gate"] == "L4"
    assert payload["cloud_enabled"] is False
    assert "eight-agent-smokes" in payload["sequence"]
    assert "tool-error-repair" in payload["sequence"]
    with pytest.raises(ValueError, match="backend L4 invalide"):
        openclaw_e2e.dry_run("invalid")


def test_run_json_handles_list_invalid_json_and_command_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        openclaw_e2e.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout='[{"id": 1}]', stderr=""),
    )
    assert openclaw_e2e._run_json(["openclaw", "x"], 1) == {"list": [{"id": 1}]}

    monkeypatch.setattr(
        openclaw_e2e.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout="not-json", stderr=""),
    )
    with pytest.raises(ValueError, match="JSON valide"):
        openclaw_e2e._run_json(["openclaw", "x"], 1)

    monkeypatch.setattr(
        openclaw_e2e.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=3, stdout="", stderr="boom"),
    )
    with pytest.raises(RuntimeError, match="commande en échec"):
        openclaw_e2e._run_json(["openclaw", "x"], 1)


def test_agent_config_and_payload_validation(tmp_path: Path) -> None:
    entries = []
    for agent in AGENT_IDS:
        workspace = tmp_path / agent
        workspace.mkdir()
        entries.append(
            {
                "id": agent,
                "model": {"primary": "ollama/test-model"},
                "workspace": str(workspace),
            }
        )
    parsed = openclaw_e2e._agent_entries({"agents": {"list": entries}})
    assert set(parsed) == set(AGENT_IDS)
    assert openclaw_e2e._provider(openclaw_e2e._model_ref(parsed[AGENT_IDS[0]])) == "ollama"
    assert openclaw_e2e._workspace(parsed[AGENT_IDS[0]]).is_dir()
    payload = _payload("AGENT_OK")
    openclaw_e2e._assert_agent_success(payload, "ollama")
    assert openclaw_e2e._visible_text(payload) == "AGENT_OK"
    with pytest.raises(RuntimeError, match="preuve provider"):
        openclaw_e2e._assert_agent_success(payload, "intel-vulkan")


def test_agent_helpers_reject_invalid_shapes_and_failed_runtime(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="agents invalide"):
        openclaw_e2e._agent_entries({"agents": []})
    with pytest.raises(ValueError, match="agents.list invalide"):
        openclaw_e2e._agent_entries({"agents": {"list": {}}})
    with pytest.raises(ValueError, match="exactement 8 agents"):
        openclaw_e2e._agent_entries({"agents": {"list": []}})
    with pytest.raises(ValueError, match="model invalide"):
        openclaw_e2e._model_ref({"model": "bad"})
    with pytest.raises(ValueError, match="référence modèle invalide"):
        openclaw_e2e._model_ref({"model": {"primary": "bad"}})
    with pytest.raises(ValueError, match="workspace absent"):
        openclaw_e2e._workspace({})
    with pytest.raises(FileNotFoundError, match="workspace absent"):
        openclaw_e2e._workspace({"workspace": str(tmp_path / "missing")})

    payload = _payload("x")
    result = payload["result"]
    assert isinstance(result, dict)
    meta = result["meta"]
    assert isinstance(meta, dict)
    meta["error"] = {"message": "failure"}
    with pytest.raises(RuntimeError, match="erreur agent"):
        openclaw_e2e._assert_agent_success(payload, "ollama")

    blocked = _payload("x")
    blocked_result = blocked["result"]
    assert isinstance(blocked_result, dict)
    blocked_meta = blocked_result["meta"]
    assert isinstance(blocked_meta, dict)
    blocked_meta["livenessState"] = "blocked"
    with pytest.raises(RuntimeError, match="liveness"):
        openclaw_e2e._assert_agent_success(blocked, "ollama")

    wrong_status = _payload("x")
    wrong_status["status"] = "failed"
    with pytest.raises(RuntimeError, match="status agent"):
        openclaw_e2e._assert_agent_success(wrong_status, "ollama")


def test_visible_text_fallback_shapes() -> None:
    assert openclaw_e2e._visible_text({"final": " FINAL "}) == "FINAL"
    assert openclaw_e2e._visible_text({"payloads": [{"text": "one"}, {"text": "two"}]}) == (
        "one\ntwo"
    )
    assert openclaw_e2e._visible_text({}) == ""


def test_gateway_ready_accepts_rpc_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        openclaw_e2e,
        "_run_json",
        lambda _command, timeout: {"rpc": {"ok": True}, "timeout": timeout},
    )
    result = openclaw_e2e._gateway_ready("openclaw", timeout=2)
    assert result["rpc"]["ok"] is True


def test_run_e2e_refuses_missing_binary_and_wrong_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(openclaw_e2e.shutil, "which", lambda _name: None)
    code, evidence = openclaw_e2e.run_e2e(ROOT, backend="ollama-vulkan", runtime_root=tmp_path)
    assert (code, evidence) == (2, None)

    monkeypatch.setattr(openclaw_e2e.shutil, "which", lambda _name: "/usr/bin/openclaw")
    monkeypatch.setattr(
        openclaw_e2e.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout="OpenClaw 0.0.0",
            stderr="",
        ),
    )
    code, evidence = openclaw_e2e.run_e2e(ROOT, backend="ollama-vulkan", runtime_root=tmp_path)
    assert (code, evidence) == (2, None)


def test_save_evidence_records_failed_verdict(tmp_path: Path) -> None:
    code, path = openclaw_e2e._save_evidence(
        tmp_path,
        {"verdict": "FAIL", "error": "synthetic"},
        success=False,
    )
    assert code == 2
    assert path.is_file()
    assert '"error": "synthetic"' in path.read_text(encoding="utf-8")


def test_full_l4_simulation_creates_tool_repair_and_stability_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = tmp_path / "runtime"
    workspace_root = tmp_path / "workspaces"
    entries: list[dict[str, object]] = []
    for agent in AGENT_IDS:
        workspace = workspace_root / agent
        workspace.mkdir(parents=True)
        entries.append(
            {
                "id": agent,
                "model": {"primary": "ollama/test-model"},
                "workspace": str(workspace),
            }
        )
    config = {"agents": {"list": entries}}
    devops_workspace = workspace_root / "ingenieur-devops"

    monkeypatch.setattr(
        openclaw_e2e.shutil,
        "which",
        lambda name: "/usr/bin/openclaw" if name == "openclaw" else None,
    )
    monkeypatch.setattr(
        openclaw_e2e.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout="OpenClaw 2026.7.1-2\n",
            stderr="",
        ),
    )
    monkeypatch.setattr(openclaw_e2e, "_config", lambda: config)
    monkeypatch.setattr(openclaw_e2e, "_gateway_ready", lambda _openclaw: {"rpc": {"ok": True}})

    def run_json(command: list[str], timeout: int) -> dict[str, object]:
        del timeout
        if command[1:3] == ["config", "validate"]:
            return {"status": "ok"}
        if command[1:3] == ["agents", "list"]:
            return {"list": [{"id": agent} for agent in AGENT_IDS]}
        raise AssertionError(command)

    monkeypatch.setattr(openclaw_e2e, "_run_json", run_json)

    stable_counter = {"value": 0}

    def agent_call(
        _openclaw: str,
        *,
        agent: str,
        session: str,
        message: str,
        timeout: int,
        thinking: str = "off",
    ) -> dict[str, object]:
        del session, timeout, thinking
        if "AGENT_OK" in message:
            return _payload(f"AGENT_OK {agent}")
        if "TOOL_OK" in message:
            match = re.search(r"(\.openclaw-e2e/[^/]+/tool-ok\.txt)", message)
            assert match
            target = devops_workspace / match.group(1)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("TOOL_OK\n", encoding="utf-8")
            return _payload("TOOL_OK")
        if "REPAIR_OK" in message:
            match = re.search(r"(\.openclaw-e2e/[^/]+/repair-ok\.txt)", message)
            assert match
            target = devops_workspace / match.group(1)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("REPAIR_OK\n", encoding="utf-8")
            return _payload("REPAIR_OK")
        if "STABLE_OK" in message:
            stable_counter["value"] += 1
            return _payload(f"STABLE_OK {stable_counter['value']}")
        raise AssertionError(message)

    monkeypatch.setattr(openclaw_e2e, "_agent_call", agent_call)
    code, evidence = openclaw_e2e.run_e2e(
        ROOT,
        backend="ollama-vulkan",
        runtime_root=runtime,
    )
    assert code == 0
    assert evidence is not None and evidence.is_file()
    text = evidence.read_text(encoding="utf-8")
    assert '"verdict": "PASS"' in text
    assert '"tool_call"' in text
    assert '"repair"' in text
    assert text.count('"run":') == 3
