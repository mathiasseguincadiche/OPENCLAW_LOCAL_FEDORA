"""Independent loopback bridge for LM Studio, sharing ClawFedora's policy engine.

No Open WebUI container, accounts, ORM or native folders are required.
"""

from __future__ import annotations

import argparse
import os
import re
from contextlib import suppress
from pathlib import Path

from clawfedora.storage import load_settings, require_storage
from clawfedora.webui_bridge import make_server

PORT = 18894
TOKEN_PATH = "state/lmstudio/bridge.token"


def read_token(runtime: Path) -> str:
    token_file = runtime / TOKEN_PATH
    for parent in (runtime, runtime / "state", runtime / "state/lmstudio", token_file):
        if parent.is_symlink():
            raise PermissionError("LM Studio : chemin du jeton lié interdit")
    stat = token_file.stat()
    if not token_file.is_file() or stat.st_mode & 0o077:
        raise PermissionError("LM Studio : jeton local privé 0600 requis")
    if stat.st_uid != os.getuid():
        raise PermissionError("LM Studio : jeton appartenant à un autre compte")
    token = token_file.read_text(encoding="utf-8").strip()
    if re.fullmatch(r"[a-f0-9]{64}", token) is None:
        raise ValueError("LM Studio : jeton de pont invalide")
    return token


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--runtime-root", required=True, type=Path)
    args = parser.parse_args(argv)
    require_storage(args.runtime_root, load_settings(args.root))
    token = read_token(args.runtime_root)
    with (
        make_server(args.root, args.runtime_root, token, PORT) as server,
        suppress(KeyboardInterrupt),
    ):
        server.serve_forever()


if __name__ == "__main__":
    main()
