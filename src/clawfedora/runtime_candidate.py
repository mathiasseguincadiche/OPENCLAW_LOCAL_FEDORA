from __future__ import annotations

import hashlib
import json
import os
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from clawfedora.core_config import root_contract

SUPPORTED_BACKENDS = {"llama-cpp-vulkan": "vulkan", "llama-cpp-sycl": "sycl"}


@dataclass(frozen=True)
class RuntimeFiles:
    backend: str
    server: Path
    preset: Path
    launcher: Path
    unit_name: str
    unit_path: Path
    endpoint: str


def _mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("L6 runtime: objet attendu")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_runtime_path(runtime_root: Path, relative: str) -> Path:
    value = Path(relative)
    if not relative or value.is_absolute() or ".." in value.parts:
        raise ValueError(f"L6 runtime: chemin relatif interdit: {relative}")
    root = runtime_root.resolve()
    target = (root / value).resolve(strict=False)
    if target == root or root not in target.parents:
        raise ValueError(f"L6 runtime: chemin hors runtime: {relative}")
    return target


def _manifest(repo_root: Path, runtime_root: Path) -> tuple[Path, dict[str, Any]]:
    policy = root_contract(repo_root, "optimization_policy.yaml")
    paths = _mapping(policy.get("paths"))
    model_dir = _safe_runtime_path(runtime_root, str(paths.get("llama_models", "")))
    manifest_path = model_dir / "ARTIFACT_MANIFEST.json"
    if not manifest_path.is_file():
        raise ValueError("L6 runtime: ARTIFACT_MANIFEST.json absent; exécuter le staging explicite")
    value = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest = _mapping(value)
    models = _mapping(manifest.get("models"))
    if len(models) != 3:
        raise ValueError("L6 runtime: manifest doit contenir exactement 3 modèles")
    return model_dir, manifest


def _verify_source(entry: dict[str, Any]) -> Path:
    source = Path(str(entry.get("source", ""))).expanduser().resolve()
    expected = str(entry.get("sha256", ""))
    if not source.is_file() or not expected or _sha256(source) != expected:
        raise ValueError(f"L6 runtime: artefact modèle invalide: {source}")
    return source


def _preset_text(manifest: dict[str, Any], context_tokens: int, gpu_layers: int) -> str:
    lines = [
        "version = 1",
        "",
        "[*]",
        f"c = {context_tokens}",
        f"n-gpu-layers = {gpu_layers}",
        "jinja = true",
        "",
    ]
    models = _mapping(manifest.get("models"))
    for alias in sorted(models):
        entry = _mapping(models[alias])
        runtime_id = str(entry.get("runtime_id", ""))
        if not runtime_id or "\n" in runtime_id or "[" in runtime_id or "]" in runtime_id:
            raise ValueError(f"L6 runtime: runtime_id INI invalide: {runtime_id}")
        primary = _verify_source(entry)
        lines.extend([f"[{runtime_id}]", f"model = {primary}"])
        projectors: list[Path] = []
        auxiliaries = entry.get("auxiliary", [])
        if not isinstance(auxiliaries, list):
            raise ValueError(f"L6 runtime: auxiliary invalide pour {alias}")
        for raw in auxiliaries:
            auxiliary = _mapping(raw)
            source = _verify_source(auxiliary)
            if auxiliary.get("directive") == "PROJECTOR":
                projectors.append(source)
        if len(projectors) > 1:
            raise ValueError(f"L6 runtime: plusieurs PROJECTOR pour {alias}")
        if projectors:
            lines.append(f"mmproj = {projectors[0]}")
        lines.append("")
    return "\n".join(lines)


def _launcher_text(backend: str, server: Path, args: list[str]) -> str:
    command = " ".join(shlex.quote(str(value)) for value in [server, *args])
    lines = ["#!/usr/bin/env bash", "set -Eeuo pipefail"]
    if backend == "llama-cpp-sycl":
        lines.extend(
            [
                "if [[ -r /opt/intel/oneapi/setvars.sh ]]; then",
                "  set +u",
                "  # shellcheck disable=SC1091",
                "  source /opt/intel/oneapi/setvars.sh >/dev/null",
                "  set -u",
                "fi",
                "command -v icpx >/dev/null 2>&1 || { echo 'SYCL toolchain absent' >&2; exit 3; }",
                "export GGML_SYCL_DEVICE='0'",
            ]
        )
    lines.append(f"exec {command}")
    return "\n".join(lines) + "\n"


def prepare_runtime_files(
    repo_root: Path,
    runtime_root: Path,
    backend: str,
    *,
    unit_dir: Path,
) -> RuntimeFiles:
    if backend not in SUPPORTED_BACKENDS:
        raise ValueError(f"L6 runtime: backend non supporté: {backend}")
    policy = root_contract(repo_root, "optimization_policy.yaml")
    paths = _mapping(policy.get("paths"))
    services = _mapping(policy.get("services"))
    backend_key = SUPPORTED_BACKENDS[backend]
    service = _mapping(services.get(backend_key))
    build_relative = str(paths.get(f"llama_{backend_key}_build", ""))
    build_dir = _safe_runtime_path(runtime_root, build_relative)
    server = build_dir / "bin/llama-server"
    marker = build_dir / "OPENCLAW_BUILD_COMMIT"
    expected_commit = str(_mapping(_mapping(policy.get("pins")).get("llama_cpp")).get("commit", ""))
    if not server.is_file() or not os.access(server, os.X_OK):
        raise ValueError(f"L6 runtime: llama-server absent/non exécutable: {server}")
    if not marker.is_file() or marker.read_text(encoding="utf-8").strip() != expected_commit:
        raise ValueError("L6 runtime: build llama.cpp non conforme au commit pinné")

    model_dir, manifest = _manifest(repo_root, runtime_root)
    generated = runtime_root.resolve() / "runtime/generated/l6"
    generated.mkdir(parents=True, exist_ok=True)
    preset = generated / f"models-{backend_key}.ini"
    context = int(service.get("context_tokens", 8192))
    gpu_layers = int(service.get("gpu_layers", 999))
    preset.write_text(_preset_text(manifest, context, gpu_layers), encoding="utf-8")

    host = str(services.get("host", "127.0.0.1"))
    if host != "127.0.0.1":
        raise ValueError("L6 runtime: host loopback obligatoire")
    port = int(service.get("port", 0))
    if port not in {8080, 8081}:
        raise ValueError("L6 runtime: port candidat inattendu")
    args = [
        "--host",
        host,
        "--port",
        str(port),
        "--models-preset",
        str(preset),
        "--models-max",
        str(int(service.get("models_max", 1))),
        "--models-autoload",
        "--offline",
        "--jinja",
        "--metrics",
        "--no-webui",
    ]
    launcher = generated / f"launch-{backend_key}.sh"
    launcher.write_text(_launcher_text(backend, server, args), encoding="utf-8")
    launcher.chmod(0o750)

    unit_name = str(service.get("unit", ""))
    if not unit_name.startswith("openclaw-llama-") or not unit_name.endswith(".service"):
        raise ValueError("L6 runtime: nom unité invalide")
    unit_dir.mkdir(parents=True, exist_ok=True)
    unit_path = unit_dir / unit_name
    read_write_paths = " ".join(
        str(runtime_root.resolve() / relative)
        for relative in ("runtime", "proofs", "benchmarks")
    )
    unit = "\n".join(
        [
            "[Unit]",
            f"Description=OPENCLAW_LOCAL_FEDORA L6 {backend} candidate",
            "After=network.target",
            "",
            "[Service]",
            "Type=simple",
            f"ExecStart={launcher}",
            "Restart=on-failure",
            "RestartSec=2",
            "NoNewPrivileges=true",
            "PrivateTmp=true",
            "ProtectSystem=strict",
            "ProtectHome=read-only",
            f"ReadOnlyPaths={model_dir}",
            f"ReadWritePaths={read_write_paths}",
            "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6",
            "",
            "[Install]",
            "WantedBy=default.target",
            "",
        ]
    )
    unit_path.write_text(unit, encoding="utf-8")
    return RuntimeFiles(
        backend=backend,
        server=server,
        preset=preset,
        launcher=launcher,
        unit_name=unit_name,
        unit_path=unit_path,
        endpoint=f"http://{host}:{port}/v1",
    )
