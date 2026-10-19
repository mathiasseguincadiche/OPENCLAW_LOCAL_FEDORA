"""Public documentation must stay navigable and aligned with code contracts.

This is intentionally a fast static test: no network, browser, model or GPU.
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

import yaml

ROOT = Path(__file__).resolve().parents[1]
DOCS = (
    *sorted(ROOT.glob("*.md")),
    *sorted((ROOT / "docs").rglob("*.md")),
    *sorted((ROOT / ".github").glob("*.md")),
)
LOCAL_LINK = re.compile(r"!?(?:\[[^\]\n]*\])\(([^)\n]+)\)")


def test_all_repository_documentation_links_are_resolvable() -> None:
    broken: list[str] = []
    for file in DOCS:
        for match in LOCAL_LINK.finditer(file.read_text(encoding="utf-8")):
            href = match.group(1).strip().split(' "', 1)[0].strip("<>")
            if not href or href.startswith(("#", "http://", "https://", "mailto:", "data:")):
                continue
            target = unquote(href.split("#", 1)[0].split("?", 1)[0])
            if not target:
                continue
            candidate = file.parent / target
            if not candidate.exists():
                broken.append(f"{file.relative_to(ROOT)} -> {href}")
    assert not broken, "Liens locaux introuvables:\n" + "\n".join(broken)


def test_current_versions_documented_without_updating_history() -> None:
    versions = yaml.safe_load(
        (ROOT / "config/runtime_versions.yaml").read_text(encoding="utf-8")
    )
    webui = yaml.safe_load(
        (ROOT / "config/webui_policy.yaml").read_text(encoding="utf-8")
    )
    status = (ROOT / "STATUS.md").read_text(encoding="utf-8")
    integrity = (ROOT / "docs/INSTALLATION_INTEGRITE.md").read_text(encoding="utf-8")
    for text in (status, integrity):
        assert versions["openclaw"]["version"] in text
        assert versions["ollama"]["version"] in text
        assert str(webui["release"]) in text
        assert "/IA/Openclaw" in text
    assert "32K" not in (ROOT / "docs/INSTALLATION_SIMPLE_FEDORA45.md").read_text(
        encoding="utf-8"
    ).split("## 3. Un seul contrôle rapide", 1)[0]


def test_public_navigation_and_quick_check_match_runtime() -> None:
    main = (ROOT / "README.md").read_text(encoding="utf-8")
    docs = (ROOT / "docs/README.md").read_text(encoding="utf-8")
    guide = (ROOT / "docs/GUIDE.md").read_text(encoding="utf-8")
    menu = (ROOT / "menu.sh").read_text(encoding="utf-8")
    assert "/IA/Openclaw" in main and "/IA/Openclaw" in docs and "/IA/Openclaw" in guide
    assert "quick-check)" in menu
    for content in (main, docs, guide):
        assert "./menu.sh --action quick-check" in content
    for folder in ("reference", "validation", "archives/2026"):
        assert (ROOT / "docs" / folder / "README.md").is_file()
    for path in sorted((ROOT / "docs/fiches").glob("*.md")):
        assert path.name in docs, path.name


def test_historical_plans_are_identified_as_non_normative() -> None:
    plans = (
        "PROGRAMME_AMELIORATION_2026.md",
        "PLAN_QUALITE_2026.md",
        "PLAN_MIGRATION_HYBRIDE.md",
        "MIGRATION_OPENCLAW_2026_10_2.md",
        "PLAN_INTEGRATION_WEBUI.md",
        "AUDIT_COMPLEMENTAIRE_2026_10.md",
    )
    for name in plans:
        path = ROOT / "docs" / name
        assert "Archive de conception 2026" in path.read_text(encoding="utf-8")
