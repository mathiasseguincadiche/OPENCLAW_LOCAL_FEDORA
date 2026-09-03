from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from clawfedora import runtime_candidate

LLAMA_COMMIT = "b95502ba9aa0eb73a2f4fc8878d7fbe6a847a0b9"
MODELS = {
    "qwen-max": "qwen3.5:9b-q4_K_M",
    "gemma-deep": "gemma3:12b-it-q4_K_M",
    "devstral-devops": "qwen2.5-coder:14b-instruct-q4_K_M",
}


def _policy() -> dict[str, object]:
    return {
        "pins": {"llama_cpp": {"commit": LLAMA_COMMIT}},
        "paths": {
            "llama_models": "models/llama-router",
            "llama_vulkan_build": "runtime/llama.cpp/vulkan",
            "llama_sycl_build": "runtime/llama.cpp/sycl",
        },
        "services": {
            "host": "127.0.0.1",
            "vulkan": {
                "unit": "openclaw-llama-vulkan.service",
                "port": 8081,
                "models_max": 1,
                "context_tokens": 8192,
                "gpu_layers": 999,
            },
            "sycl": {
                "unit": "openclaw-llama-sycl.service",
                "port": 8080,
                "models_max": 1,
                "context_tokens": 8192,
                "gpu_layers": 999,
            },
        },
    }


def _fake_root_contract(_repo_root: Path, name: str) -> dict[str, object]:
    assert name == "optimization_policy.yaml"
    return _policy()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _runtime_tree(tmp_path: Path) -> Path:
    runtime_root = tmp_path / "runtime-root"
    model_dir = runtime_root / "models/llama-router"
    model_dir.mkdir(parents=True)
    models: dict[str, object] = {}
    for alias, runtime_id in MODELS.items():
        source = tmp_path / f"{alias}.gguf"
        source.write_bytes(f"model:{alias}".encode())
        projector = tmp_path / f"{alias}-projector.gguf"
        projector.write_bytes(f"projector:{alias}".encode())
        models[alias] = {
            "runtime_id": runtime_id,
            "source": str(source),
            "sha256": _sha(source),
            "auxiliary": [
                {
                    "directive": "PROJECTOR",
                    "source": str(projector),
                    "sha256": _sha(projector),
                }
            ],
        }
    (model_dir / "ARTIFACT_MANIFEST.json").write_text(
        json.dumps({"models": models}),
        encoding="utf-8",
    )
    for backend in ("vulkan", "sycl"):
        build = runtime_root / f"runtime/llama.cpp/{backend}"
        server = build / "bin/llama-server"
        server.parent.mkdir(parents=True)
        server.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        server.chmod(0o755)
        (build / "OPENCLAW_BUILD_COMMIT").write_text(LLAMA_COMMIT, encoding="utf-8")
    return runtime_root


def test_safe_runtime_path_and_sha(tmp_path: Path) -> None:
    path = tmp_path / "artifact"
    path.write_bytes(b"abc")
    assert runtime_candidate._sha256(path) == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
    assert runtime_candidate._safe_runtime_path(tmp_path, "runtime/x") == (
        tmp_path / "runtime/x"
    ).resolve()
    with pytest.raises(ValueError, match="chemin relatif interdit"):
        runtime_candidate._safe_runtime_path(tmp_path, "../escape")


def test_prepare_runtime_files_for_vulkan_and_sycl(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = _runtime_tree(tmp_path)
    monkeypatch.setattr(runtime_candidate, "root_contract", _fake_root_contract)
    unit_dir = tmp_path / "units"

    vulkan = runtime_candidate.prepare_runtime_files(
        tmp_path,
        runtime_root,
        "llama-cpp-vulkan",
        unit_dir=unit_dir,
    )
    assert vulkan.endpoint == "http://127.0.0.1:8081/v1"
    assert vulkan.server.is_file()
    assert vulkan.launcher.stat().st_mode & 0o100
    preset = vulkan.preset.read_text(encoding="utf-8")
    for runtime_id in MODELS.values():
        assert f"[{runtime_id}]" in preset
    assert "n-gpu-layers = 999" in preset
    assert "--offline" in vulkan.launcher.read_text(encoding="utf-8")
    unit = vulkan.unit_path.read_text(encoding="utf-8")
    assert "NoNewPrivileges=true" in unit
    assert "ProtectSystem=strict" in unit
    assert "ReadOnlyPaths=" in unit
    assert "ReadWritePaths=" in unit

    sycl = runtime_candidate.prepare_runtime_files(
        tmp_path,
        runtime_root,
        "llama-cpp-sycl",
        unit_dir=unit_dir,
    )
    launcher = sycl.launcher.read_text(encoding="utf-8")
    assert sycl.endpoint == "http://127.0.0.1:8080/v1"
    assert "/opt/intel/oneapi/setvars.sh" in launcher
    assert "GGML_SYCL_DEVICE='0'" in launcher
    assert "command -v icpx" in launcher


def test_runtime_helpers_reject_invalid_manifest_and_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runtime_candidate, "root_contract", _fake_root_contract)
    runtime_root = tmp_path / "runtime-root"
    with pytest.raises(ValueError, match="ARTIFACT_MANIFEST.json absent"):
        runtime_candidate._manifest(tmp_path, runtime_root)

    model_dir = runtime_root / "models/llama-router"
    model_dir.mkdir(parents=True)
    (model_dir / "ARTIFACT_MANIFEST.json").write_text(
        json.dumps({"models": {"one": {}, "two": {}}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="exactement 3 modèles"):
        runtime_candidate._manifest(tmp_path, runtime_root)

    missing = {"source": str(tmp_path / "missing.gguf"), "sha256": "bad"}
    with pytest.raises(ValueError, match="artefact modèle invalide"):
        runtime_candidate._verify_source(missing)


def test_preset_rejects_invalid_runtime_id_and_multiple_projectors(tmp_path: Path) -> None:
    source = tmp_path / "model.gguf"
    source.write_bytes(b"model")
    projector_a = tmp_path / "a.gguf"
    projector_b = tmp_path / "b.gguf"
    projector_a.write_bytes(b"a")
    projector_b.write_bytes(b"b")

    invalid_id = {
        "models": {
            "slot": {
                "runtime_id": "bad[id]",
                "source": str(source),
                "sha256": _sha(source),
                "auxiliary": [],
            }
        }
    }
    with pytest.raises(ValueError, match="runtime_id INI invalide"):
        runtime_candidate._preset_text(invalid_id, 8192, 999)

    multiple = {
        "models": {
            "slot": {
                "runtime_id": "valid",
                "source": str(source),
                "sha256": _sha(source),
                "auxiliary": [
                    {
                        "directive": "PROJECTOR",
                        "source": str(projector_a),
                        "sha256": _sha(projector_a),
                    },
                    {
                        "directive": "PROJECTOR",
                        "source": str(projector_b),
                        "sha256": _sha(projector_b),
                    },
                ],
            }
        }
    }
    with pytest.raises(ValueError, match="plusieurs PROJECTOR"):
        runtime_candidate._preset_text(multiple, 8192, 999)


def test_prepare_runtime_files_rejects_backend_build_marker_host_and_port(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = _runtime_tree(tmp_path)
    unit_dir = tmp_path / "units"
    monkeypatch.setattr(runtime_candidate, "root_contract", _fake_root_contract)
    with pytest.raises(ValueError, match="backend non supporté"):
        runtime_candidate.prepare_runtime_files(
            tmp_path,
            runtime_root,
            "invalid",
            unit_dir=unit_dir,
        )

    server = runtime_root / "runtime/llama.cpp/vulkan/bin/llama-server"
    server.chmod(0o644)
    with pytest.raises(ValueError, match="absent/non exécutable"):
        runtime_candidate.prepare_runtime_files(
            tmp_path,
            runtime_root,
            "llama-cpp-vulkan",
            unit_dir=unit_dir,
        )
    server.chmod(0o755)

    marker = runtime_root / "runtime/llama.cpp/vulkan/OPENCLAW_BUILD_COMMIT"
    marker.write_text("wrong", encoding="utf-8")
    with pytest.raises(ValueError, match="commit pinné"):
        runtime_candidate.prepare_runtime_files(
            tmp_path,
            runtime_root,
            "llama-cpp-vulkan",
            unit_dir=unit_dir,
        )
    marker.write_text(LLAMA_COMMIT, encoding="utf-8")

    bad_host = _policy()
    services = bad_host["services"]
    assert isinstance(services, dict)
    services["host"] = "0.0.0.0"
    monkeypatch.setattr(runtime_candidate, "root_contract", lambda *_args: bad_host)
    with pytest.raises(ValueError, match="host loopback obligatoire"):
        runtime_candidate.prepare_runtime_files(
            tmp_path,
            runtime_root,
            "llama-cpp-vulkan",
            unit_dir=unit_dir,
        )

    bad_port = _policy()
    services = bad_port["services"]
    assert isinstance(services, dict)
    vulkan = services["vulkan"]
    assert isinstance(vulkan, dict)
    vulkan["port"] = 9999
    monkeypatch.setattr(runtime_candidate, "root_contract", lambda *_args: bad_port)
    with pytest.raises(ValueError, match="port candidat inattendu"):
        runtime_candidate.prepare_runtime_files(
            tmp_path,
            runtime_root,
            "llama-cpp-vulkan",
            unit_dir=unit_dir,
        )
