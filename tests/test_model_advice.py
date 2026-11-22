"""Le conseil de modèle suit les sept rôles exclusivement locaux."""
from __future__ import annotations

import pytest

from clawfedora.model_advice import CATEGORIES, SUGGESTIONS, advise


@pytest.mark.parametrize("category", CATEGORIES)
def test_every_category_is_grounded_in_local_role_and_capabilities(category: str) -> None:
    item = SUGGESTIONS[category]
    response = advise(category)
    assert item.agent in response and item.model in response
    assert "sans analyse des documents" in response
    assert "Aucune route OpenRouter" in response


@pytest.mark.parametrize(
    ("request", "model"),
    [
        ("linux", "Qwen"),
        ("PRIVE", "Qwen ou Ornith"),
        ("terraform", "Ornith"),
        ("pipeline", "Ornith"),
        ("documents", "Qwen"),
        ("audit", "Qwen"),
        ("securite", "Qwen"),
    ],
)
def test_aliases_resolve_to_the_right_specialist(request: str, model: str) -> None:
    assert model in advise(request)


def test_unrecognized_free_text_never_leads_to_a_provider_call() -> None:
    result = advise("Voici un secret et une longue conversation")
    assert "Catégorie non reconnue" in result
    assert "Aucun contenu n'a été envoyé à une IA" in result


def test_overview_keeps_all_route_choices_local_and_deterministic() -> None:
    overview = advise()
    assert "Qwen" in overview and "Ornith" in overview
    assert "DeepSeek" not in overview and "Sol" not in overview
    assert "Aucune route OpenRouter" in overview
    assert "aucune escalade implicite" in overview
