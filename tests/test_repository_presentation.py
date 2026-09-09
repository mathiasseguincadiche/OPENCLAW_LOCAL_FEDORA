from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"


def test_repository_landing_page_has_clear_identity_and_status() -> None:
    text = README.read_text(encoding="utf-8")
    for marker in (
        "Fedora 44 · Local AI · 8 agents · Intel Arc B580 · Vulkan · Fail-closed",
        "## Pourquoi ce projet ?",
        "## État en un coup d'œil",
        "## Architecture",
        "```mermaid",
        "## Installation rapide",
        "## Parcours de documentation",
        "## Qualification",
        "## Sécurité et invariants",
        "## Sources de vérité",
    ):
        assert marker in text


def test_repository_landing_page_exposes_real_project_badges() -> None:
    text = README.read_text(encoding="utf-8")
    for marker in (
        "actions/workflows/ci.yml/badge.svg?branch=main",
        "actions/workflows/codeql.yml/badge.svg?branch=main",
        "Fedora-44",
        "OpenClaw-2026.9.2",
        "Python-3.12%20%7C%203.13",
        "License-MIT",
    ):
        assert marker in text


def test_repository_landing_page_preserves_truthful_readiness_language() -> None:
    text = README.read_text(encoding="utf-8")
    for marker in (
        "qualification matérielle B580 en attente",
        "PASS logiciel",
        "À exécuter sur la machine réelle",
        "V1 | **Non approuvée**",
        "exactement `2026.9.2`",
        "Aucun fallback LLM cloud silencieux",
    ):
        assert marker in text


def test_repository_landing_page_preserves_one_universal_documentation_path() -> None:
    text = README.read_text(encoding="utf-8")
    assert "qu'une seule documentation et un seul parcours" in text
    assert "sans connaissance préalable" in text
    assert "ils ne créent pas de parcours séparés" in text
    for forbidden in ("Parcours expert", "Documentation expert", "Réservé aux experts"):
        assert forbidden not in text


def test_repository_landing_page_stays_concise() -> None:
    text = README.read_text(encoding="utf-8")
    assert len(text) < 9000
