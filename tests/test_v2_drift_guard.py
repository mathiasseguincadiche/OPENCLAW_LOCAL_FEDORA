from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".md", ".py", ".sh", ".toml", ".yaml", ".yml"}
SCAN_ROOTS = ("agents", "config", "docs", "scripts", "src", "tests")

CURRENT_IDS = (
    "qwen3.5:9b-q4_K_M",
    "gemma4:12b-it-q4_K_M",
    "hf.co/mistralai/Ministral-3-14B-Reasoning-2512-GGUF:Q4_K_M",
    "granite4.2:8b-q4_K_M",
    "2026.9.2",
)

# Construits en fragments afin que le garde ne se signale pas lui-même.
LEGACY_TOKENS = (
    "gemma" + "3:12b-it-q4_K_M",
    "qwen2.5-" + "coder:14b-instruct-q4_K_M",
    "2026.7." + "1-2",
    "ministral-3:" + "14b-instruct-2512-q4_K_M",
)


def _text_files() -> list[Path]:
    paths: list[Path] = []
    for root_name in SCAN_ROOTS:
        root = ROOT / root_name
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in TEXT_SUFFIXES:
                paths.append(path)
    for name in ("README.md", "STATUS.md", "menu.sh", "pyproject.toml"):
        path = ROOT / name
        if path.is_file():
            paths.append(path)
    return sorted(set(paths))


def test_architecture_v2_has_no_legacy_runtime_identifiers() -> None:
    offenders: dict[str, list[str]] = {}
    for path in _text_files():
        text = path.read_text(encoding="utf-8")
        found = [token for token in LEGACY_TOKENS if token in text]
        if found:
            offenders[str(path.relative_to(ROOT))] = found
    assert offenders == {}, f"identifiants V1/V2 obsolètes détectés: {offenders}"


def test_canonical_contract_contains_current_fleet_and_openclaw_pin() -> None:
    catalog = (ROOT / "config/model_catalog.yaml").read_text(encoding="utf-8")
    versions = (ROOT / "config/runtime_versions.yaml").read_text(encoding="utf-8")
    for runtime_id in CURRENT_IDS[:4]:
        assert runtime_id in catalog
    assert CURRENT_IDS[4] in versions
    assert "exact_required_model_count: 3" in catalog
    assert "challenger_counts_toward_required_fleet: false" in catalog
