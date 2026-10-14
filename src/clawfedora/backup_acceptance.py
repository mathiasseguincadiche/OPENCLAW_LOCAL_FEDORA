"""Read-only qualification of an existing backup by extracting into a private throwaway directory.

No production files are overwritten. Report contains counts only, no filenames or secrets.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import stat
import tempfile
from pathlib import Path
from typing import Any

from clawfedora.lifecycle import RUNTIME_MARKER, restore_backup


def verify_backup_restore(archive: Path) -> dict[str, Any]:
    if archive.is_symlink() or not archive.is_file():
        raise ValueError("archive de sauvegarde absente ou liée")
    with tempfile.TemporaryDirectory(prefix="clawfedora-restore-check-") as directory:
        target = Path(directory) / "restored"
        restore_backup(archive, target)
        marker = target / RUNTIME_MARKER
        if not marker.is_file() or marker.is_symlink():
            raise ValueError("marqueur runtime absent de la sauvegarde")
        files = sorted(path for path in target.rglob("*") if path.is_file())
        if not files:
            raise ValueError("aucune donnée restaurée")
        sqlite_count = 0
        for path in files:
            if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
                raise ValueError("fichier restauré irrégulier")
            with path.open("rb") as stream:
                is_sqlite = stream.read(16) == b"SQLite format 3\x00"
            if is_sqlite:
                with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
                    if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                        raise ValueError("base SQLite restaurée invalide")
                sqlite_count += 1
        # Destination is automatically deleted before the verdict is returned.
        return {
            "verdict": "RESTORE_VERIFIED",
            "files_checked": len(files),
            "sqlite_databases_checked": sqlite_count,
            "destination": "private_temporary_directory_deleted",
            "production_runtime_modified": False,
            "gpu_webui_browser_tested": False,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Tester une restauration réelle dans une destination isolée et jetable"
    )
    parser.add_argument("archive", type=Path)
    args = parser.parse_args(argv)
    try:
        result = verify_backup_restore(args.archive)
    except (ValueError, OSError, sqlite3.DatabaseError, EOFError) as exc:
        print(json.dumps({"verdict": "RESTORE_REFUSED", "reason": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
