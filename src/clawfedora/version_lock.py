from __future__ import annotations

import re

_OPENCLAW_VERSION_RE = re.compile(r"(?<![0-9.])([0-9]{4}\.[0-9]+\.[0-9]+)(?![0-9.])")


def extract_openclaw_version(output: str) -> str:
    """Extract one exact OpenClaw calendar-version token from CLI output.

    Fail closed on missing or ambiguous version output so a prefix such as
    ``2026.9.2`` can never validate ``2026.9.20``.
    """

    versions = list(dict.fromkeys(_OPENCLAW_VERSION_RE.findall(output)))
    if len(versions) != 1:
        raise ValueError(f"version OpenClaw absente ou ambiguë: {output!r}")
    return versions[0]
