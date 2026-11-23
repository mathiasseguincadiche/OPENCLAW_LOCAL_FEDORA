"""Bounded native-chat context selection never mutates the durable transcript."""
from __future__ import annotations

import pytest

from clawfedora.chat_context import select_history


def _turn(question: str, answer: str) -> list[dict[str, str]]:
    return [{"role": "user", "content": question},
            {"role": "assistant", "content": answer}]


def test_keeps_complete_recent_turns_and_relevant_older_turns() -> None:
    history = (
        _turn("Erreur SELinux Ansible audit Rocky", "Correction SELinux sous vérification")
        + _turn("Parlons maintenant de la documentation", "Documentation mise en page")
        + _turn("Quel nom pour le rapport?", "Rapport hebdomadaire")
        + _turn("Autre sujet sans rapport", "Réponse neutre")
    )
    original = [dict(item) for item in history]
    selected, stats = select_history(
        history, "Reprendre l'erreur SELinux Ansible",
        char_budget=300, recent_turns=1, recalled_turns=2,
    )
    assert selected == history[:2] + history[-2:]
    assert stats["recalled_turns"] == 1
    assert stats["stored_turns"] == 4
    assert stats["omitted_turns"] == 2
    assert history == original
    assert stats["sent_chars"] <= 300


def test_never_sends_only_half_a_turn_or_exceeds_budget() -> None:
    history = (
        _turn("première", "A" * 200)
        + _turn("deuxième", "B" * 40)
        + _turn("troisième", "C" * 40)
    )
    selected, stats = select_history(
        history, "nouvelle question", char_budget=80,
        recent_turns=3, recalled_turns=0,
    )
    assert selected == history[-2:]
    assert stats["sent_turns"] == 1
    assert stats["omitted_turns"] == 2
    assert stats["sent_chars"] <= 80


def test_large_recent_turn_does_not_leak_beyond_budget() -> None:
    history = _turn("ancienne décision", "long" * 10) + _turn(
        "dernier message", "Z" * 300)
    selected, stats = select_history(
        history, "nouveau message", char_budget=100, recent_turns=2,
    )
    assert selected == []
    assert stats["stored_turns"] == 2
    assert stats["omitted_turns"] == 2


def test_refuses_invalid_history_or_undersized_budget() -> None:
    with pytest.raises(ValueError, match="non apparié"):
        select_history([{"role": "user", "content": "incomplet"}], "message")
    with pytest.raises(ValueError, match="invalide"):
        select_history(_turn("x", "y")[::-1], "message")
    with pytest.raises(ValueError, match="insuffisant"):
        select_history([], "grand message", char_budget=5)
