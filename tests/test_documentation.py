from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = [
    ROOT / "README.md",
    ROOT / "STATUS.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "SECURITY.md",
    ROOT / "CHANGELOG.md",
    ROOT / "CODE_OF_CONDUCT.md",
    ROOT / "docs/DECISION_MODELE.md",
    ROOT / "docs/PLAN_INTEGRATION_WEBUI.md",
    ROOT / "docs/GUIDE.md",
    ROOT / "docs/PROMPTS.md",
    *sorted((ROOT / "docs/fiches").glob("*.md")),
]
LINK = re.compile(r"\[[^\]]*\]\(([^)#\s]+)(?:#[^)]*)?\)")


def test_every_local_link_resolves() -> None:
    broken: list[str] = []
    for document in DOCUMENTS:
        for target in LINK.findall(document.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            if not (document.parent / target).resolve().exists():
                broken.append(f"{document.relative_to(ROOT)} -> {target}")
    assert broken == []


def test_guide_links_to_every_sheet_and_sheets_link_back() -> None:
    guide = (ROOT / "docs/GUIDE.md").read_text(encoding="utf-8")
    sheets = sorted((ROOT / "docs/fiches").glob("*.md"))
    assert len(sheets) == 12
    for sheet in sheets:
        assert f"fiches/{sheet.name}" in guide, sheet.name
        assert "[← Guide](../GUIDE.md)" in sheet.read_text(encoding="utf-8"), sheet.name


def test_documented_menu_actions_and_scripts_exist() -> None:
    menu = (ROOT / "menu.sh").read_text(encoding="utf-8")
    known = set(re.findall(r"^  ([a-z|-]+)\)", menu, flags=re.M))
    actions = {name for group in known for name in group.split("|")}
    for document in DOCUMENTS:
        text = document.read_text(encoding="utf-8")
        for action in re.findall(r"menu\.sh --action ([a-z-]+)", text):
            assert action in actions, f"{document.name}: action inconnue {action}"
        for script in re.findall(r"scripts/linux/(\d\d_[a-z_]+\.sh)", text):
            assert (ROOT / "scripts/linux" / script).is_file(), f"{document.name}: {script}"
        for config in re.findall(r"`(config/[a-z_/]+\.yaml)`", text):
            assert (ROOT / config).is_file(), f"{document.name}: {config}"


def test_documentation_states_what_is_not_measured_yet() -> None:
    status = (ROOT / "STATUS.md").read_text(encoding="utf-8")
    assert "À mesurer" in status and "À faire" in status
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/GUIDE.md" in readme and "n'a pas encore tourné sur le PC" in readme
