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
        # Counts alone can miss replaced conversations or user rows. Preserve a
        # private fingerprint of each stable ID and the chat JSON payload when
        # that column is present. No private chat text or identifier is returned.
        fingerprints: dict[str, dict[str, str]] = {}
        for table in ("user", "chat"):
            if counts[table] > 100_000:
                raise ValueError("trop de lignes WebUI à comparer")
            columns = {
                str(item[1])
                for item in db.execute(f'PRAGMA table_info("{table}")')
            }
            if "id" not in columns:
                raise ValueError(f"identifiant manquant dans {table}")
            fields = '"id", "chat"' if table == "chat" and "chat" in columns else '"id"'
            rows_for_table: dict[str, str] = {}
            for row in db.execute(f'SELECT {fields} FROM "{table}"'):
                identifier = row[0]
                if not isinstance(identifier, str) or not identifier:
                    raise ValueError("identifiant WebUI invalide")
                identity = hashlib.sha256(identifier.encode("utf-8")).hexdigest()
                if identity in rows_for_table:
                    raise ValueError("identifiant WebUI dupliqué")
                payload = row[1] if len(row) > 1 else ""
                if not isinstance(payload, str):
                    raise ValueError("contenu chat non textuel")
                rows_for_table[identity] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            fingerprints[table] = rows_for_table
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
    return {"counts": counts, "functions": functions, "record_fingerprints": fingerprints}


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
    previous_rows = before.get("record_fingerprints")
    current_rows = after.get("record_fingerprints")
    if not isinstance(previous_rows, dict) or not isinstance(current_rows, dict):
        raise ValueError("empreintes des conversations WebUI absentes")
    for table in ("user", "chat"):
        historical = previous_rows.get(table)
        migrated = current_rows.get(table)
        if not isinstance(historical, dict) or not isinstance(migrated, dict):
            raise ValueError(f"empreintes {table} incomplètes")
        for identifier, digest in historical.items():
            if migrated.get(identifier) != digest:
                raise ValueError(f"contenu ou identité WebUI perdue dans {table}")
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
