"""Deterministic model recommendation is a read-only user hint, not routing."""

from __future__ import annotations

import pytest

from clawfedora.model_advice import CATEGORIES, SUGGESTIONS, advise


@pytest.mark.parametrize("category", CATEGORIES)
def test_each_supported_category_has_a_clear_and_safe_advice(category: str) -> None:
    recommendation = advise(category)
    assert SUGGESTIONS[category].route in recommendation
    assert "aucun passage automatique" in recommendation.lower()
    assert "sans requête Qwen ou DeepSeek" in recommendation
    assert "manuel" in recommendation


@pytest.mark.parametrize(
    ("category", "expected"),
    [
        ("linux", "Qwen local"),
        ("PRIVE", "Qwen local uniquement"),
        ("terraform", "DeepSeek cloud"),
        ("pipeline", "DeepSeek"),
        ("documents", "DeepSeek"),
    ],
)
def test_aliases_are_stable_and_do_not_modify_the_route(
    category: str, expected: str
) -> None:
    assert expected in advise(category)


def test_no_arbitrary_text_is_regarded_as_safe_for_cloud() -> None:
    text = advise("Voici ma clef confidentielle ou un dump interne")
    assert "Catégorie non reconnue" in text
    assert "Aucun contenu n'a été envoyé à une IA" in text
    assert "confidenti" not in text.split("Catégorie non reconnue")[0]


def test_overview_warns_about_project_consent_and_confidentiality() -> None:
    overview = advise()
    assert "Qwen local" in overview
    assert "DeepSeek" in overview
    assert "historique" in overview
    assert "accord cloud valide" in overview
    assert "aucun passage automatique" in overview.lower()
