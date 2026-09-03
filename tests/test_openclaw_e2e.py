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


def test_gateway_ready_accepts_rpc_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        openclaw_e2e,
        "_run_json",
        lambda _command, timeout: {"rpc": {"ok": True}, "timeout": timeout},
    )
    result = openclaw_e2e._gateway_ready("openclaw", timeout=2)
    assert result["rpc"]["ok"] is True


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

    monkeypatch.setattr(openclaw_e2e.shutil, "which", lambda name: "/usr/bin/openclaw" if name == "openclaw" else None)
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
