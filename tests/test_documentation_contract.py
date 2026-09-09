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
    "docs/GETTING_STARTED.md",
    "docs/INSTALLATION.md",
    "docs/OPERATIONS.md",
    "docs/TROUBLESHOOTING.md",
    "docs/ARCHITECTURE.md",
    "docs/MULTI_AGENT_CORE.md",
    "docs/PROJECT_ENGINE.md",
    "docs/OPENCLAW_SYSTEMD.md",
    "docs/LIFECYCLE.md",
    "docs/FEDORA_B580.md",
    "docs/KERNEL_POLICY.md",
    "docs/UPGRADE.md",
    "docs/QUALIFICATION.md",
    "docs/ROADMAP.md",
)

PROGRESSION_FIELDS = (
    "Pour qui",
    "Position dans le parcours",
    "Prérequis",
    "Objectif",
    "Résultat attendu",
    "Critère d’arrêt",
    "Continuer avec",
    "Source de vérité",
)

NEXT_STEP = {
    "docs/GETTING_STARTED.md": "INSTALLATION.md",
    "docs/INSTALLATION.md": "OPERATIONS.md",
    "docs/OPERATIONS.md": "TROUBLESHOOTING.md",
    "docs/TROUBLESHOOTING.md": "ARCHITECTURE.md",
    "docs/ARCHITECTURE.md": "MULTI_AGENT_CORE.md",
    "docs/MULTI_AGENT_CORE.md": "PROJECT_ENGINE.md",
    "docs/PROJECT_ENGINE.md": "OPENCLAW_SYSTEMD.md",
    "docs/OPENCLAW_SYSTEMD.md": "LIFECYCLE.md",
    "docs/LIFECYCLE.md": "FEDORA_B580.md",
    "docs/FEDORA_B580.md": "KERNEL_POLICY.md",
    "docs/KERNEL_POLICY.md": "UPGRADE.md",
    "docs/UPGRADE.md": "QUALIFICATION.md",
    "docs/QUALIFICATION.md": "ROADMAP.md",
    "docs/ROADMAP.md": "STATUS.md",
}


def test_operator_documentation_set_is_complete() -> None:
    missing = [path for path in REQUIRED_DOCS if not (ROOT / path).is_file()]
    assert missing == []


def test_root_readme_is_an_entry_point_to_operator_docs() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for path in REQUIRED_DOCS[:6]:
        assert path in readme
    assert len(readme) < 9000, "README doit rester une porte d'entrée, pas le manuel complet"


def test_docs_index_links_to_all_progression_guides() -> None:
    index = (ROOT / "docs/README.md").read_text(encoding="utf-8")
    for path in PEDAGOGICAL_GUIDES:
        assert Path(path).name in index


def test_docs_index_exposes_one_universal_learning_path() -> None:
    index = (ROOT / "docs/README.md").read_text(encoding="utf-8")
    assert "## Parcours unique" in index
    assert "une seule documentation, un seul parcours, compréhensible par tout le monde" in index

    forbidden_segmented_paths = (
        "### Débutant",
        "### Opérateur",
        "### Expert",
        "## Parcours guidés",
    )
    for marker in forbidden_segmented_paths:
        assert marker not in index

    path_section = index.split("## Parcours unique", 1)[1].split(
        "## Contrat de progression des guides", 1
    )[0]
    positions = [path_section.index(Path(path).name) for path in PEDAGOGICAL_GUIDES]
    assert positions == sorted(positions)
    assert path_section.index("STATUS.md") > positions[-1]


def test_reference_guides_form_one_continuous_progression() -> None:
    failures: list[str] = []
    total = len(PEDAGOGICAL_GUIDES)
    position_pattern = re.compile(r"\| \*\*Position dans le parcours\*\* \| ([^|]+) \|")

    for index, relative in enumerate(PEDAGOGICAL_GUIDES, start=1):
        path = ROOT / relative
        text = path.read_text(encoding="utf-8")
        header = "\n".join(text.splitlines()[:40])

        if "## Repères de progression" not in header:
            failures.append(f"{relative}: section Repères de progression absente")
            continue

        for field in PROGRESSION_FIELDS:
            if f"| **{field}** |" not in header:
                failures.append(f"{relative}: repère de progression absent: {field}")

        if "| **Pour qui** | Toute personne" not in header:
            failures.append(
                f"{relative}: le guide doit être explicitement accessible à toute personne"
            )

        if "| **Niveau** |" in header or "| **Public cible** |" in header:
            failures.append(f"{relative}: segmentation par niveau/public interdite")

        match = position_pattern.search(header)
        expected_position = f"{index}/{total}"
        if match is None or match.group(1).strip() != expected_position:
            failures.append(
                f"{relative}: position attendue {expected_position}, "
                f"observée {match.group(1).strip() if match else 'absente'}"
            )

        expected_next = NEXT_STEP[relative]
        continue_row = next(
            (line for line in header.splitlines() if line.startswith("| **Continuer avec** |")),
            "",
        )
        if expected_next not in continue_row:
            failures.append(f"{relative}: étape suivante attendue {expected_next}")

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
