"""Content-free usage metrics; missing provider fields are not zero."""

from __future__ import annotations

import math
from typing import Any


def reported_cost(usage: dict[str, Any]) -> float | None:
    value = usage.get("cost")
    if not isinstance(value, int | float) or isinstance(value, bool) or value < 0:
        return None
    try:
        return float(value) if math.isfinite(value) else None
    except OverflowError:
        return None


def token_counts(usage: dict[str, Any]) -> dict[str, int]:
    """Keep only known, nonnegative counters; never store arbitrary provider metadata."""
    counts: dict[str, int] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = usage.get(key)
        if type(value) is int and value >= 0:
            counts[key] = value
    for group, key, parent in (
        ("prompt_tokens_details", "cached_tokens", "prompt_tokens"),
        ("prompt_tokens_details", "cache_write_tokens", "prompt_tokens"),
        ("completion_tokens_details", "reasoning_tokens", "completion_tokens"),
    ):
        details = usage.get(group)
        value = details.get(key) if isinstance(details, dict) else None
        if type(value) is int and parent in counts and 0 <= value <= counts[parent]:
            counts[key] = value
    return counts
