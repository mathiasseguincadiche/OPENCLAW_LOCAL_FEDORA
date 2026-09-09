from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_DOCS = (
    "docs/README.md",
    "docs/INSTALLATION.md",
    "docs/GETTING_STARTED.md",
    "docs/OPERATIONS.md",
    "docs/TROUBLESHOOTING.md",
    "docs/UPGRADE.md",
    "docs/ARCHITECTURE.md",
    "docs/QUALIFICATION.md",
)

PEDAGOGICAL_GUIDES = (
    "docs/INSTALLATION.md",
    "docs/GETTING_STARTED.md",
    "docs/OPERATIONS.md",
    "docs/TROUBLESHOOTING.md",
    "docs/UPGRADE.md",
    "docs/ARCHITECTURE.md",
    "docs/MULTI_AGENT_CORE.md",
    "docs/PROJECT_ENGINE.md",
    "docs/QUALIFICATION.md",
    "docs/FEDORA_B580.md",
    "docs/KERNEL_POLICY.md",
    "docs/OPENCLAW_SYSTEMD.md",
    "docs/LIFECYCLE.md",
    "docs/ROADMAP.md",
)

PEDAGOGICAL_FIELDS = (
    "Public cible",
    "Niveau",
    "Prérequis",
    "Objectif",
    "Résultat attendu",
    "Critère d’arrêt",
    "À lire ensuite",
    "Source de vérité",
)

PEDAGOGICAL_LEVELS = {"Découverte", "Intermédiaire", "Avancé", "Expert"}


def test_operator_documentation_set_is_complete() -> None:
    missing = [path for path in REQUIRED_DOCS if not (ROOT / path).is_file()]
    assert missing == []


def test_root_readme_is_an_entry_point_to_operator_docs() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for path in REQUIRED_DOCS[:6]:
        assert path in readme
    assert len(readme) < 9000, "README doit rester une porte d'entrée, pas le manuel complet"


def test_docs_index_links_to_operator_and_reference_docs() -> None:
    index = (ROOT / "docs/README.md").read_text(encoding="utf-8")
    for path in PEDAGOGICAL_GUIDES:
        assert Path(path).name in index


def test_docs_index_exposes_guided_reading_paths() -> None:
    index = (ROOT / "docs/README.md").read_text(encoding="utf-8")
    for marker in (
        "### Débutant — découvrir puis utiliser",
        "### Opérateur — exploiter et maintenir",
        "### Expert / mainteneur — comprendre les contrats et les preuves",
        "## Contrat pédagogique des guides",
    ):
        assert marker in index


def test_reference_guides_have_uniform_pedagogical_metadata() -> None:
    failures: list[str] = []
    level_pattern = re.compile(r"\| \*\*Niveau\*\* \| ([^|]+) \|")

    for relative in PEDAGOGICAL_GUIDES:
        path = ROOT / relative
        text = path.read_text(encoding="utf-8")
        header = "\n".join(text.splitlines()[:35])
        if "## Repères de lecture" not in header:
            failures.append(f"{relative}: section Repères de lecture absente du début du guide")
            continue
        for field in PEDAGOGICAL_FIELDS:
            if f"| **{field}** |" not in header:
                failures.append(f"{relative}: métadonnée pédagogique absente: {field}")
        match = level_pattern.search(header)
        if match is None or match.group(1).strip() not in PEDAGOGICAL_LEVELS:
            failures.append(f"{relative}: niveau pédagogique invalide")

    assert failures == []


def test_local_markdown_document_links_resolve() -> None:
    markdown_files = [ROOT / "README.md", ROOT / "STATUS.md", *sorted((ROOT / "docs").glob("*.md"))]
    link_pattern = re.compile(r"\[[^\]]+\]\(([^)]+\.md)(?:#[^)]+)?\)")
    broken: list[str] = []
    for document in markdown_files:
        text = document.read_text(encoding="utf-8")
        for target in link_pattern.findall(text):
            if target.startswith(("http://", "https://")):
                continue
            resolved = (document.parent / target).resolve()
            try:
                resolved.relative_to(ROOT.resolve())
            except ValueError:
                broken.append(f"{document.relative_to(ROOT)} -> {target} (hors dépôt)")
                continue
            if not resolved.is_file():
                broken.append(f"{document.relative_to(ROOT)} -> {target}")
    assert broken == []


def test_operator_banner_matches_architecture_v2_semantics() -> None:
    menu = (ROOT / "menu.sh").read_text(encoding="utf-8")
    for expected in (
        "Qwen 3.5 9B",
        "Gemma 4 12B",
        "Ministral 3 14B Reasoning",
        "Granite 4.2 8B hors routage",
        "exactement 3",
    ):
        assert expected in menu
    for obsolete in (
        "Gemma 3 12B",
        "Qwen 2.5 Coder 14B",
        "Ministral 3 14B hors routage",
    ):
        assert obsolete not in menu


def test_runbook_preserves_fedora_security_invariants() -> None:
    operations = (ROOT / "docs/OPERATIONS.md").read_text(encoding="utf-8")
    troubleshooting = (ROOT / "docs/TROUBLESHOOTING.md").read_text(encoding="utf-8")
    combined = operations + troubleshooting
    for invariant in (
        "SELinux",
        "Enforcing",
        "firewalld",
        "systemd --user",
        "ollama-vulkan",
        "rollback",
    ):
        assert invariant in combined
    assert "chmod -R 777" in troubleshooting
    assert "setenforce 0" in troubleshooting
    assert "ne constitue pas une correction acceptable" in troubleshooting
