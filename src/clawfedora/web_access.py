"""Operator-controlled Web search/fetch isolation for the seven local agents.

The persistent marker is a *desired configuration*, not proof that a running Gateway
has reloaded it. Enabling private mode requires a native config apply and service
restart; local model selection alone never implies offline networking.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

MARKER = Path("state/web-access/private.enabled")
APPROVAL = "private-web-tools-v1"
WEB_TOOLS = ("web_search", "web_fetch")


def private_mode(runtime: Path) -> bool:
    """Read a 0600 regular marker; reject tampering instead of silently enabling Web."""
    path = runtime / MARKER
    if (runtime / "state").is_symlink() or path.parent.is_symlink():
        raise ValueError("état accès Web lié interdit")
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(mode) or mode & 0o077:
        raise ValueError("marqueur d'accès Web non privé ou lié")
    if path.read_text(encoding="utf-8").strip() != APPROVAL:
        raise ValueError("marqueur d'accès Web non reconnu")
    if not (runtime / ".openclaw-fedora-runtime").is_file():
        raise ValueError("mode Web privé : runtime géré requis")
    return True


def set_private_mode(runtime: Path, enabled: bool) -> bool:
    """Stage a Web access mode without asserting that services were reconfigured.

    Return whether the marker changed. No changes on an unmanaged runtime.
    """
    if not (runtime / ".openclaw-fedora-runtime").is_file():
        raise ValueError("runtime géré requis")
    if runtime.is_symlink() or (runtime / "state").is_symlink():
        raise ValueError("état accès Web lié interdit")
    state = runtime / "state"
    if not state.is_dir():
        raise ValueError("état runtime absent")
    directory = runtime / MARKER.parent
    if directory.is_symlink():
        raise ValueError("répertoire accès Web lié interdit")
    directory.mkdir(mode=0o700, exist_ok=True)
    directory.chmod(0o700)
    existing = private_mode(runtime)
    if existing == enabled:
        return False
    path = runtime / MARKER
    if enabled:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        fd = os.open(path, flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(APPROVAL + "\n")
    else:
        path.unlink()
    return True
