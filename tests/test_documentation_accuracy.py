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


def test_release_documentation_uses_real_line_breaks() -> None:
    """Reject literal backslash-n left by programmatic Markdown updates."""
    for name in ("STATUS.md", "docs/PYTHON_RUNTIME_LOCK.md"):
        content = (ROOT / name).read_text(encoding="utf-8")
        assert "\\n" not in content, f"{name}: escaped newline instead of Markdown line break"
    status_lines = (ROOT / "STATUS.md").read_text(encoding="utf-8").splitlines()
    assert any(line.startswith("| Runtime Python IA |") for line in status_lines)


def test_documented_menu_actions_exist_in_the_shipped_menu() -> None:
    """Reject stale --action commands in current public guides."""
    menu = (ROOT / "menu.sh").read_text(encoding="utf-8")
    action_block = menu.split('case "$ACTION" in', 1)[1]
    choices = set()
    for match in re.finditer(r"^  ([a-z][a-z0-9_-]*(?:\|[a-z0-9_-]+)*)\)", action_block, re.M):
        choices.update(match.group(1).split("|"))
    assert {"install", "quick-check", "cloud-status", "validate"} <= choices
    pattern = re.compile(r"\./menu\.sh\s+--action\s+([a-z][a-z0-9_-]*)")
    stale = []
    for path in DOCS:
        if (
            path.parent == ROOT / "docs"
            and "Archive de conception 2026" in path.read_text(encoding="utf-8")
        ):
            continue
        for match in pattern.finditer(path.read_text(encoding="utf-8")):
            if match.group(1) not in choices:
                stale.append(f"{path.relative_to(ROOT)}: {match.group(1)}")
    assert not stale, "Actions documentées inconnues:\n" + "\n".join(stale)


def test_pedagogy_and_preferences_are_documented_in_public_entrypoints() -> None:
    policy = yaml.safe_load((ROOT / "config/evals/pedagogy_conversations.yaml").read_text(
        encoding="utf-8"
    ))
    assert len(policy["scenarios"]) == 4
    assert all(len(item["turns"]) >= 3 for item in policy["scenarios"])
    guide = (ROOT / "docs/EVALUATION_PEDAGOGIE.md").read_text(encoding="utf-8")
    assert "clawfedora-pedagogy --plan" in guide
    for word in ("Clarté", "Profondeur", "Interactivité", "Exactitude"):
        assert word in guide
    for name in (
        "README.md",
        "docs/README.md",
        "docs/GUIDE.md",
        "docs/validation/README.md",
        "docs/fiches/05-apprendre.md",
        "docs/fiches/12-cloud.md",
    ):
        assert "EVALUATION_PEDAGOGIE.md" in (ROOT / name).read_text(encoding="utf-8")
    for field in ("explanation_style", "learning_summary"):
        assert field in (ROOT / "src/clawfedora/mentor.py").read_text(encoding="utf-8")
        assert field in (ROOT / "docs/fiches/08-reglages.md").read_text(encoding="utf-8")


def test_install_guide_uses_real_line_breaks_instead_of_escaped_newlines() -> None:
    guide = (ROOT / "docs/INSTALLATION_SIMPLE_FEDORA45.md").read_text(
        encoding="utf-8"
    )
    assert "\\nLe Python" not in guide
    assert "\\nen **Python" not in guide
