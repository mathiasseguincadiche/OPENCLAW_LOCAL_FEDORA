"""Contract checks for copy-ready Notion wiki templates (not a visual Notion test)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_wiki_home_template_preserves_five_spaces_and_no_false_proof() -> None:
    content = (ROOT / "templates/notion/accueil-wiki.md").read_text(encoding="utf-8")
    for name in ("Comprendre", "Préparer", "Pratiquer", "Suivre", "Ressources"):
        assert f"<b>{name}</b>" in content
    assert "<columns>" in content
    assert "<callout" in content
    assert "État réel" in content
    assert "preuve" in content.lower()
    assert "<!--" not in content


def test_exercise_template_preserves_installation_and_verification() -> None:
    content = (ROOT / "templates/notion/exercice-infraops.md").read_text(encoding="utf-8")
    for expected in (
        "<table-of-contents",
        "Situation professionnelle",
        "Préparer l'environnement et installer si nécessaire",
        "Inventaire",
        "Vérifier le résultat",
        "Diagnostiquer",
        "Aide reçue",
        "non attribué",
    ):
        assert expected.lower() in content.lower()
    assert "<toggle" in content
    assert "<!--" not in content


def test_design_charter_never_confuses_notions_and_github_roles() -> None:
    content = (ROOT / "docs/NOTION_WIKI_DESIGN_SYSTEM.md").read_text(encoding="utf-8")
    assert "GitHub" in content and "Notion" in content
    assert "l'installation" in content
    assert "lecture mobile" in content or "mobile" in content
    assert "STRUCTURE_VERIFIEE" in content
    assert "RENDU_VISUEL_VERIFIE" in content
    assert "TECHNIQUE_EXECUTEE" in content
