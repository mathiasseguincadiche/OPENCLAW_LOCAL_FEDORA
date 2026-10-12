"""Privacy-preserving checks for a disposable Open WebUI SQLite migration.

No content is emitted: only record counts, opaque IDs and salted-free hashes
to compare the original *copy* and its offline migrated canary. Not a backup.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any

TABLES = ("user", "chat", "function")
MAX_FUNCTION_ROWS = 10_000


def snapshot(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("base SQLite canary absente ou liée")
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5) as db:
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("base SQLite canary corrompue")
        names = {
            str(row[0])
            for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        if not set(TABLES).issubset(names):
            raise ValueError("tables WebUI requises absentes")
        counts: dict[str, int] = {}
        for table in TABLES:
            # Identifier from a fixed constant tuple, not arbitrary input.
            counts[table] = int(db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
        if counts["function"] > MAX_FUNCTION_ROWS:
            raise ValueError("trop de fonctions à comparer")
        rows = db.execute(
            'SELECT id, content, is_active, is_global FROM "function" ORDER BY id'
        )
        functions: dict[str, dict[str, Any]] = {}
        for identifier, content, active, global_flag in rows:
            if (
                not isinstance(identifier, str) or not identifier
                or not isinstance(content, str) or identifier in functions
            ):
                raise ValueError("fonction WebUI incomplète")
            functions[identifier] = {
                "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                "is_active": bool(active),
                "is_global": bool(global_flag),
            }
    return {"counts": counts, "functions": functions}


def verify_preservation(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Fail closed if a migration removes records or changes installed functions."""
    first, second = before.get("counts"), after.get("counts")
    if not isinstance(first, dict) or not isinstance(second, dict):
        raise ValueError("instantanés SQLite incomplets")
    for table in TABLES:
        original = first.get(table)
        migrated = second.get(table)
        if (
            type(original) is not int or type(migrated) is not int
            or original < 0 or migrated < original
        ):
            raise ValueError(f"enregistrements WebUI perdus dans {table}")
    functions = before.get("functions")
    current = after.get("functions")
    if not isinstance(functions, dict) or not isinstance(current, dict):
        raise ValueError("état des fonctions WebUI incomplet")
    for name, record in functions.items():
        if name not in current or current[name] != record:
            raise ValueError("fonction WebUI modifiée ou perdue pendant le canary")
    return {
        "verdict": "PASS",
        "tables_preserved": list(TABLES),
        "functions_preserved": len(functions),
        "scope": "disposable_sqlite_canary_only",
    }
