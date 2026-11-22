"""Per-conversation LM Studio project claim, admitted by the existing local bridge.

The bridge bearer already authenticates the sole local caller. The claim is a
user's per-chat plugin setting, not a model instruction. No folder name, source
content, model reply or other untrusted text grants a project switch.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from clawfedora import chat_projects
from clawfedora.project_common import PROJECT_ID_RE


def resolve(
    body: dict[str, Any],
    runtime: Path,
    *,
    previous: str | None,
    referenced: set[str],
    native_webui: str | None,
) -> str | None:
    if "clawfedora_lmstudio_project" not in body:
        return None
    requested = body["clawfedora_lmstudio_project"]
    if not isinstance(requested, str) or not PROJECT_ID_RE.fullmatch(requested):
        raise ValueError("LM Studio : identifiant de projet explicite invalide")
    if native_webui is not None:
        raise ValueError("LM Studio et dossier WebUI ne peuvent pas imposer deux contextes")
    if (previous is not None and previous != requested) or (
        referenced and referenced != {requested}
    ):
        raise ValueError(
            "Ce fil contient déjà un autre projet : ouvrez une nouvelle "
            "conversation LM Studio et sélectionnez le nouveau projet."
        )
    if chat_projects.open_project(runtime, requested) is None:
        raise ValueError("LM Studio : projet absent ou intégrité du chemin invalide")
    return requested
