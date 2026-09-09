from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".md", ".yaml", ".yml", ".py", ".sh", ".toml"}
SCAN_ROOTS = ("agents", "config", "docs", "scripts", "src", "tests")
ROOT_FILES = ("README.md", "STATUS.md", "menu.sh", "pyproject.toml")


def _active_text_files() -> list[Path]:
    paths: list[Path] = []
    for relative in SCAN_ROOTS:
        base = ROOT / relative
        if not base.exists():
            continue
        paths.extend(
            path
            for path in base.rglob("*")
            if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES
        )
    paths.extend(ROOT / name for name in ROOT_FILES if (ROOT / name).is_file())
    return sorted(set(paths))


def test_active_project_has_single_vulkan_gpu_path() -> None:
    forbidden = (
        "s" + "ycl",
        "level" + " zero",
        "level" + "_zero",
        "intel-" + "s" + "ycl",
    )
    failures: list[str] = []
    for path in _active_text_files():
        text = path.read_text(encoding="utf-8").casefold()
        for token in forbidden:
            if token in text:
                failures.append(f"{path.relative_to(ROOT)} contains forbidden GPU-path token")
    assert failures == []


def test_runtime_matrix_is_exactly_vulkan() -> None:
    backends = yaml.safe_load((ROOT / "config/runtime_backends.yaml").read_text(encoding="utf-8"))
    assert set(backends["backends"]) == {"ollama-vulkan", "llama-cpp-vulkan"}
    assert all(item["accelerator"] == "vulkan" for item in backends["backends"].values())

    optimization = yaml.safe_load(
        (ROOT / "config/optimization_policy.yaml").read_text(encoding="utf-8")
    )
    assert optimization["runtime_comparison"]["baseline"] == "ollama-vulkan"
    assert optimization["runtime_comparison"]["candidates"] == ["llama-cpp-vulkan"]

    qualification = yaml.safe_load(
        (ROOT / "config/qualification_policy.yaml").read_text(encoding="utf-8")
    )
    assert qualification["runtime_comparison"]["candidates"] == [
        "ollama-vulkan",
        "llama-cpp-vulkan",
    ]
