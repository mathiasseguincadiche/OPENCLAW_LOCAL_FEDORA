from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from clawfedora.core_contracts import validate_core_contracts

ROOT = Path(__file__).resolve().parents[1]


def _sandbox(tmp_path: Path) -> Path:
    shutil.copy(ROOT / "VERSION", tmp_path / "VERSION")
    shutil.copytree(ROOT / "config", tmp_path / "config")
    shutil.copytree(ROOT / "agents", tmp_path / "agents")
    return tmp_path


def _mutate_yaml(root: Path, relative: str, mutate: object) -> None:
    path = root / relative
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    assert callable(mutate)
    mutate(payload)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_core_contracts_pass() -> None:
    failures, warnings = validate_core_contracts(ROOT)
    assert failures == ()
    assert warnings


def test_default_agent_cannot_change_silently(tmp_path: Path) -> None:
    root = _sandbox(tmp_path)
    _mutate_yaml(
        root,
        "config/core/agents.yaml",
        lambda payload: payload["policy"].__setitem__("default_agent", "ingenieur-devops"),
    )
    failures, _ = validate_core_contracts(root)
    assert any("agent par défaut" in failure for failure in failures)


def test_agent_routing_must_match_declared_model(tmp_path: Path) -> None:
    root = _sandbox(tmp_path)
    _mutate_yaml(
        root,
        "config/core/model_routing.yaml",
        lambda payload: payload["agents"]["ingenieur-devops"].__setitem__(
            "local_primary", "gemma-deep"
        ),
    )
    failures, _ = validate_core_contracts(root)
    assert any("divergence de routage" in failure for failure in failures)


def test_exec_mode_cannot_be_weakened(tmp_path: Path) -> None:
    root = _sandbox(tmp_path)
    _mutate_yaml(
        root,
        "config/core/tool_policy.yaml",
        lambda payload: payload["security_defaults"].__setitem__("exec_mode", "allow"),
    )
    failures, _ = validate_core_contracts(root)
    assert any("exec.mode=ask" in failure for failure in failures)


def test_non_loopback_backend_is_rejected(tmp_path: Path) -> None:
    root = _sandbox(tmp_path)
    _mutate_yaml(
        root,
        "config/runtime_backends.yaml",
        lambda payload: payload["backends"]["llama-cpp-vulkan"].__setitem__(
            "endpoint", "http://0.0.0.0:8081/v1"
        ),
    )
    failures, _ = validate_core_contracts(root)
    assert any("non loopback" in failure for failure in failures)


def test_missing_agent_asset_is_rejected(tmp_path: Path) -> None:
    root = _sandbox(tmp_path)
    (root / "agents" / "auditeur-qualite" / "SOUL.md").unlink()
    failures, _ = validate_core_contracts(root)
    assert any("auditeur-qualite/SOUL.md" in failure for failure in failures)
