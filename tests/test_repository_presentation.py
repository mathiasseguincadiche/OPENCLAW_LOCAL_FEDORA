from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
METADATA = ROOT / ".github/repository-metadata.yml"
SOCIAL_PREVIEW = ROOT / ".github/social-preview.svg"


def test_repository_landing_page_has_clear_identity_and_status() -> None:
    text = README.read_text(encoding="utf-8")
    assert text.startswith("# Atelier IA local — Infrastructure & OPS\n")
    for marker in (
        ".github/social-preview.svg",
        "docs/GUIDE_UTILISATEUR.md",
        "docs/guide-utilisateur.pdf",
        "docs/diagrams/atelier-architecture.drawio",
        "docs/diagrams/atelier-roles.drawio",
        "## Une architecture proportionnée",
        "## Les rôles et leur utilité",
        "## Premier démarrage",
        "## Utiliser l’atelier",
        "## Documentation et maintenance",
    ):
        assert marker in text


def test_repository_landing_page_exposes_real_project_badges() -> None:
    text = README.read_text(encoding="utf-8")
    for marker in (
        "actions/workflows/ci.yml/badge.svg?branch=main",
        "actions/workflows/codeql.yml/badge.svg?branch=main",
        "Fedora-44",
        "Licence-MIT",
    ):
        assert marker in text


def test_repository_landing_page_preserves_truthful_readiness_language() -> None:
    text = README.read_text(encoding="utf-8")
    for marker in (
        "qualification sur la machine Fedora/B580 à produire",
        "Les tests logiciels ne prouvent pas",
        "V1 reste non approuvée",
        "Qwen 3.5 9B Q4_K_M",
        "Une génération à la fois",
        "Un seul modèle quotidien",
        "pas une affirmation de dernière version disponible",
    ):
        assert marker in text


def test_repository_landing_page_preserves_one_universal_documentation_path() -> None:
    text = README.read_text(encoding="utf-8")
    assert "commun à tous" in text
    assert "sans connaissance préalable" in text
    assert "renvoient aux mêmes procédures" in text
    for forbidden in ("Parcours expert", "Documentation expert", "Réservé aux experts"):
        assert forbidden not in text


def test_repository_landing_page_stays_concise() -> None:
    text = README.read_text(encoding="utf-8")
    assert len(text) < 9000


def test_canonical_repository_metadata_is_versioned() -> None:
    payload = yaml.safe_load(METADATA.read_text(encoding="utf-8"))
    repository = payload["repository"]
    assert repository["description"].startswith("Atelier IA local — Infrastructure & OPS")
    assert "sept rôles" in repository["description"]
    assert "Qualification Arc B580/Vulkan à produire" in repository["description"]
    assert repository["homepage"] is None
    assert repository["topics"] == [
        "fedora",
        "fedora-linux",
        "openclaw",
        "local-ai",
        "llm",
        "multi-agent",
        "vulkan",
        "intel-arc",
        "intel-arc-b580",
        "ollama",
        "llama-cpp",
        "devops",
        "python",
        "systemd",
    ]


def test_social_preview_source_matches_project_invariants() -> None:
    payload = yaml.safe_load(METADATA.read_text(encoding="utf-8"))
    preview = payload["social_preview"]
    assert preview["source"] == ".github/social-preview.svg"
    assert preview["width"] == 1280
    assert preview["height"] == 640
    assert SOCIAL_PREVIEW.is_file()

    text = SOCIAL_PREVIEW.read_text(encoding="utf-8")
    for marker in (
        "Atelier IA local — Infrastructure &amp; OPS",
        "Fedora 44",
        "OpenClaw 2026.9.8",
        "sept rôles spécialisés",
        "Intel Arc B580",
        "Vulkan",
        "Qualification matérielle Intel Arc B580/Vulkan à produire",
    ):
        assert marker in text
