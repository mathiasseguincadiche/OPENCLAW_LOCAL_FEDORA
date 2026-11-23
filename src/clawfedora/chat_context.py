"""Deterministic, bounded context selection for long native Atelier discussions.

The full conversation remains on disk. This module only decides which *complete*
past exchanges are sent to the model; historical messages are never instructions,
approvals, or a substitute for the project's canonical records.
"""
from __future__ import annotations

import re

# Characters, not tokens: intentionally conservative relative to the 32K model
# contract, which also has to accommodate role instructions, tools and the reply.
HISTORY_CHAR_BUDGET = 20_000
RECENT_TURNS = 6
RECALLED_TURNS = 3
_STOP = frozenset({
    "avec", "dans", "pour", "sans", "comme", "cette", "cela", "mais",
    "nous", "vous", "leur", "elles", "alors", "depuis", "avoir", "être",
    "what", "when", "where", "with", "from", "this", "that", "have",
})


def _terms(value: str) -> set[str]:
    return {word for word in re.findall(r"[^\W_]{4,}", value.casefold())
            if word not in _STOP}


def select_history(
    messages: list[dict[str, str]],
    current_message: str,
    *,
    char_budget: int = HISTORY_CHAR_BUDGET,
    recent_turns: int = RECENT_TURNS,
    recalled_turns: int = RECALLED_TURNS,
) -> tuple[list[dict[str, str]], dict[str, int]]:
    """Keep a recent contiguous suffix, then a few relevant older user/assistant pairs.

    Never split or rewrite a past message. A lexical match is only conversational
    context, not a verified fact or permission. All project permissions and
    approvals remain enforced by the OpenClaw policy bridge.
    """
    if not isinstance(current_message, str) or char_budget <= len(current_message):
        raise ValueError("Budget de contexte insuffisant pour le nouveau message")
    if recent_turns < 0 or recalled_turns < 0 or len(messages) % 2:
        raise ValueError("Historique de conversation non apparié")
    pairs: list[tuple[dict[str, str], dict[str, str]]] = []
    for i in range(0, len(messages), 2):
        user, assistant = messages[i:i + 2]
        if (not isinstance(user, dict) or not isinstance(assistant, dict)
                or user.get("role") != "user" or assistant.get("role") != "assistant"
                or not isinstance(user.get("content"), str)
                or not isinstance(assistant.get("content"), str)):
            raise ValueError("Historique de conversation invalide")
        pairs.append((user, assistant))

    remaining = char_budget - len(current_message)
    selected: set[int] = set()
    recent_start = max(0, len(pairs) - recent_turns)
    # A contiguous suffix is more reliable than isolated recent exchanges.
    for i in range(len(pairs) - 1, recent_start - 1, -1):
        cost = sum(len(msg["content"]) for msg in pairs[i])
        if cost > remaining:
            break
        selected.add(i)
        remaining -= cost

    query = _terms(current_message)
    older: list[tuple[int, int]] = []
    for i, (user, assistant) in enumerate(pairs):
        if i in selected:
            continue
        user_matches = len(query & _terms(user["content"]))
        answer_matches = len(query & _terms(assistant["content"]))
        score = 3 * user_matches + answer_matches
        if score > 0:
            older.append((score, i))
    older.sort(key=lambda item: (-item[0], -item[1]))
    recalled = 0
    for _, i in older:
        if recalled >= recalled_turns:
            break
        cost = sum(len(msg["content"]) for msg in pairs[i])
        if cost <= remaining:
            selected.add(i)
            remaining -= cost
            recalled += 1

    result = [
        {"role": message["role"], "content": message["content"]}
        for i in sorted(selected)
        for message in pairs[i]
    ]
    return result, {
        "stored_turns": len(pairs),
        "sent_turns": len(selected),
        "omitted_turns": len(pairs) - len(selected),
        "recalled_turns": recalled,
        "sent_chars": char_budget - remaining,
        "budget_chars": char_budget,
    }
