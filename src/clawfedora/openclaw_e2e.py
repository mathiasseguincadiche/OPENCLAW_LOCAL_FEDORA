from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from clawfedora.core_config import AGENT_IDS, resolve_runtime_root, root_contract


def dry_run(backend: str) -> dict[str, Any]:
    if backend not in {"ollama-vulkan", "llama-cpp-vulkan", "llama-cpp-sycl"}:
        raise ValueError(f"backend L4 invalide: {backend}")
    return {
        "verdict": "PASS",
        "mode": "DRY-RUN",
        "gate": "L4",
        "backend": backend,
        "sequence": [
            "openclaw-version",
            "config-validate",
            "gateway-rpc-readiness",
            "agents-list-exactly-8",
            "eight-agent-smokes",
            "tool-write-read-proof",
            "tool-error-repair",
            "stability-3-runs",
        ],
        "agent_smoke_timeout_seconds": 300,
        "tool_timeout_seconds": 300,
        "gateway_timeout_seconds": 90,
        "cloud_enabled": False,
        "transport_required": "gateway",
    }


def _run_json(command: list[str], timeout: int) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    text = (completed.stdout + "\n" + completed.stderr).strip()
    if completed.returncode != 0:
        raise RuntimeError(f"commande en échec ({completed.returncode}): {text[-1200:]}")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"OpenClaw n'a pas retourné un JSON valide: {text[-1200:]}") from exc
    if not isinstance(payload, dict) and not isinstance(payload, list):
        raise ValueError("OpenClaw: réponse JSON inattendue")
    if isinstance(payload, list):
        return {"list": payload}
    return payload


def _state_root() -> Path:
    explicit = os.environ.get("OPENCLAW_STATE_DIR")
    if explicit:
        return Path(explicit).expanduser().resolve()
    xdg = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "state"
    return (base / "openclaw-local").resolve()


def _config() -> dict[str, Any]:
    path = _state_root() / "openclaw.json"
    if not path.is_file():
        raise FileNotFoundError(f"configuration OpenClaw absente: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("openclaw.json invalide")
    return payload


def _agent_entries(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    agents = config.get("agents", {})
    if not isinstance(agents, dict):
        raise ValueError("openclaw.json: agents invalide")
    entries = agents.get("list", [])
    if not isinstance(entries, list):
        raise ValueError("openclaw.json: agents.list invalide")
    result: dict[str, dict[str, Any]] = {}
    for raw in entries:
        if isinstance(raw, dict) and raw.get("id"):
            result[str(raw["id"])] = raw
    if set(result) != set(AGENT_IDS):
        raise ValueError(f"OpenClaw doit exposer exactement 8 agents: {sorted(result)}")
    return result


def _model_ref(entry: dict[str, Any]) -> str:
    model = entry.get("model", {})
    if not isinstance(model, dict):
        raise ValueError("agent: model invalide")
    value = str(model.get("primary", ""))
    if "/" not in value:
        raise ValueError(f"agent: référence modèle invalide: {value}")
    return value


def _provider(model_ref: str) -> str:
    return model_ref.split("/", 1)[0]


def _workspace(entry: dict[str, Any]) -> Path:
    value = str(entry.get("workspace", ""))
    if not value:
        raise ValueError("agent: workspace absent")
    path = Path(value).expanduser().resolve()
    if not path.is_dir():
        raise FileNotFoundError(f"workspace absent: {path}")
    return path


def _visible_text(payload: dict[str, Any]) -> str:
    result = payload.get("result")
    if isinstance(result, dict):
        meta = result.get("meta")
        if isinstance(meta, dict):
            value = meta.get("finalAssistantVisibleText")
            if isinstance(value, str) and value.strip():
                return value.strip()
    final = payload.get("final")
    if isinstance(final, str) and final.strip():
        return final.strip()
    payloads = payload.get("payloads")
    if isinstance(payloads, list):
        texts = [
            str(item.get("text", "")).strip()
            for item in payloads
            if isinstance(item, dict) and str(item.get("text", "")).strip()
        ]
        return "\n".join(texts)
    return ""


def _assert_agent_success(payload: dict[str, Any], expected_provider: str) -> None:
    result = payload.get("result")
    if not isinstance(result, dict):
        raise ValueError("résultat agent absent")
    meta = result.get("meta")
    if not isinstance(meta, dict):
        raise ValueError("métadonnées agent absentes")
    error = meta.get("error")
    if isinstance(error, dict) and any(str(value).strip() for value in error.values()):
        raise RuntimeError(f"erreur agent OpenClaw: {error}")
    liveness = str(meta.get("livenessState", "")).casefold()
    if liveness in {"blocked", "error", "failed"}:
        raise RuntimeError(f"liveness agent invalide: {liveness}")
    status = str(payload.get("status", "")).casefold()
    if status and status != "ok":
        raise RuntimeError(f"status agent invalide: {status}")
    serialized = json.dumps(payload, ensure_ascii=False)
    provider_marker = f'"provider": "{expected_provider}"'
    provider_marker_compact = f'"provider":"{expected_provider}"'
    if provider_marker not in serialized and provider_marker_compact not in serialized:
        raise RuntimeError(f"preuve provider={expected_provider} absente")
    if '"transport":"embedded"' in serialized.replace(" ", ""):
        raise RuntimeError("transport embedded interdit pour L4")
    if '"fallbackFrom":"gateway"' in serialized.replace(" ", ""):
        raise RuntimeError("fallback silencieux depuis Gateway interdit")


def _gateway_ready(openclaw: str, timeout: int = 90) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        try:
            last = _run_json(
                [openclaw, "gateway", "status", "--require-rpc", "--json"],
                timeout=15,
            )
        except (RuntimeError, ValueError, subprocess.TimeoutExpired):
            time.sleep(2)
            continue
        rpc = last.get("rpc")
        if isinstance(rpc, dict) and rpc.get("ok") is True:
            return last
        time.sleep(2)
    raise TimeoutError(f"Gateway RPC non prêt après {timeout}s: {last}")


def _agent_call(
    openclaw: str,
    *,
    agent: str,
    session: str,
    message: str,
    timeout: int,
    thinking: str = "off",
) -> dict[str, Any]:
    return _run_json(
        [
            openclaw,
            "agent",
            "--agent",
            agent,
            "--session-key",
            session,
            "--message",
            message,
            "--thinking",
            thinking,
            "--timeout",
            str(timeout),
            "--json",
        ],
        timeout=timeout + 30,
    )


def _proof(payload: dict[str, Any], text: str, provider: str) -> dict[str, Any]:
    return {
        "provider": provider,
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "text_chars": len(text),
        "status": payload.get("status"),
    }


def run_e2e(
    repo_root: Path,
    *,
    backend: str,
    runtime_root: Path | None = None,
) -> tuple[int, Path | None]:
    plan = dry_run(backend)
    runtime = runtime_root or resolve_runtime_root()
    openclaw = shutil.which("openclaw")
    if not openclaw:
        print("L4_RESULT=FAIL openclaw absent")
        return 2, None
    versions = root_contract(repo_root, "runtime_versions.yaml")
    expected_version = str(dict(versions["openclaw"])["initial_qualification_pin"])
    version = subprocess.run(
        [openclaw, "--version"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    actual_version = (version.stdout + version.stderr).strip()
    if version.returncode != 0 or expected_version not in actual_version:
        print(f"L4_RESULT=FAIL OpenClaw attendu={expected_version} reçu={actual_version}")
        return 2, None

    try:
        _run_json([openclaw, "config", "validate", "--json"], timeout=30)
        gateway = _gateway_ready(openclaw)
        config = _config()
        entries = _agent_entries(config)
        listed = _run_json([openclaw, "agents", "list", "--json"], timeout=30)
        raw_list = listed.get("list") or listed.get("agents")
        if not isinstance(raw_list, list) or len(raw_list) != 8:
            raise ValueError("OpenClaw agents list doit contenir exactement 8 agents")
    except (FileNotFoundError, RuntimeError, ValueError, TimeoutError) as exc:
        print(f"L4_RESULT=FAIL preflight={exc}")
        return 2, None

    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    session_prefix = f"fedora-e2e-{stamp}"
    order = sorted(AGENT_IDS, key=lambda agent: _model_ref(entries[agent]))
    evidence: dict[str, Any] = {
        "schema_version": "1.0.0",
        "gate": "L4",
        "backend": backend,
        "openclaw_version": actual_version,
        "gateway": gateway,
        "cloud_enabled": False,
        "transport": "gateway",
        "agent_smokes": [],
        "tool_call": None,
        "repair": None,
        "stability": [],
        "plan": plan,
    }
    try:
        for agent in order:
            provider = _provider(_model_ref(entries[agent]))
            payload = _agent_call(
                openclaw,
                agent=agent,
                session=f"{session_prefix}-smoke-{agent}",
                message=f"N'utilise aucun outil. Réponds exactement: AGENT_OK {agent}",
                timeout=300,
            )
            _assert_agent_success(payload, provider)
            text = _visible_text(payload)
            if text != f"AGENT_OK {agent}":
                raise RuntimeError(f"smoke {agent}: réponse inattendue {text!r}")
            evidence["agent_smokes"].append(
                {
                    "agent": agent,
                    "model_ref": _model_ref(entries[agent]),
                    **_proof(payload, text, provider),
                }
            )

        tool_agent = "ingenieur-devops"
        tool_entry = entries[tool_agent]
        tool_provider = _provider(_model_ref(tool_entry))
        workspace = _workspace(tool_entry)
        scratch = workspace / ".openclaw-e2e" / stamp
        scratch.mkdir(parents=True, exist_ok=False)
        relative = f".openclaw-e2e/{stamp}/tool-ok.txt"
        tool_prompt = (
            f"Crée le fichier {relative} avec exactement TOOL_OK. Utilise les outils fichiers. "
            "Si nécessaire utilise tool_search puis tool_call. N'utilise pas exec. "
            "Après écriture réponds exactement TOOL_OK."
        )
        payload = _agent_call(
            openclaw,
            agent=tool_agent,
            session=f"{session_prefix}-tool",
            message=tool_prompt,
            timeout=300,
        )
        _assert_agent_success(payload, tool_provider)
        text = _visible_text(payload)
        marker = workspace / relative
        if text != "TOOL_OK" or marker.read_text(encoding="utf-8").strip() != "TOOL_OK":
            raise RuntimeError("preuve tool-calling invalide")
        evidence["tool_call"] = {
            **_proof(payload, text, tool_provider),
            "file_sha256": hashlib.sha256(marker.read_bytes()).hexdigest(),
        }

        missing_relative = f".openclaw-e2e/{stamp}/missing.txt"
        repair_relative = f".openclaw-e2e/{stamp}/repair-ok.txt"
        repair_prompt = (
            f"Essaie d'abord de lire {missing_relative}; ce fichier n'existe pas. "
            f"Après l'erreur outil, crée {repair_relative} avec exactement REPAIR_OK, "
            "puis réponds exactement REPAIR_OK. N'utilise pas exec."
        )
        payload = _agent_call(
            openclaw,
            agent=tool_agent,
            session=f"{session_prefix}-repair",
            message=repair_prompt,
            timeout=300,
        )
        _assert_agent_success(payload, tool_provider)
        text = _visible_text(payload)
        repaired = workspace / repair_relative
        if text != "REPAIR_OK" or repaired.read_text(encoding="utf-8").strip() != "REPAIR_OK":
            raise RuntimeError("preuve réparation après erreur outil invalide")
        evidence["repair"] = {
            **_proof(payload, text, tool_provider),
            "file_sha256": hashlib.sha256(repaired.read_bytes()).hexdigest(),
        }

        for index in range(1, 4):
            expected = f"STABLE_OK {index}"
            payload = _agent_call(
                openclaw,
                agent=tool_agent,
                session=f"{session_prefix}-stable-{index}",
                message=f"N'utilise aucun outil. Réponds exactement: {expected}",
                timeout=300,
            )
            _assert_agent_success(payload, tool_provider)
            text = _visible_text(payload)
            if text != expected:
                raise RuntimeError(f"stabilité {index}: réponse inattendue {text!r}")
            evidence["stability"].append(
                {"run": index, **_proof(payload, text, tool_provider)}
            )
    except (
        FileNotFoundError,
        OSError,
        RuntimeError,
        ValueError,
        subprocess.TimeoutExpired,
    ) as exc:
        evidence["verdict"] = "FAIL"
        evidence["error"] = str(exc)
        return _save_evidence(runtime, evidence, success=False)

    evidence["verdict"] = "PASS"
    return _save_evidence(runtime, evidence, success=True)


def _save_evidence(
    runtime_root: Path,
    evidence: dict[str, Any],
    *,
    success: bool,
) -> tuple[int, Path]:
    directory = runtime_root / "proofs" / "openclaw-e2e"
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    path = directory / f"l4_{stamp}.json"
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"EVIDENCE={path}")
    print(f"L4_RESULT={'PASS' if success else 'FAIL'}")
    return (0 if success else 2), path
