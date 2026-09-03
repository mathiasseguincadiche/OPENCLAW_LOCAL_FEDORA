from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_all_config_contracts_match_repository_version() -> None:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    paths = sorted((ROOT / "config").glob("*.yaml"))
    assert paths
    for path in paths:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(payload, dict), path
        assert str(payload.get("platform_version", "")) == version, path


def test_pyproject_version_matches_repository_version() -> None:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert f'version = "{version}"' in pyproject
