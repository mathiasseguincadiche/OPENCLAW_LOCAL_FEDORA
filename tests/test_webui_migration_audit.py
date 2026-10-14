from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from clawfedora.webui_migration_audit import snapshot, verify_preservation


def _db(path: Path) -> Path:
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE "user" (id TEXT PRIMARY KEY)')
        db.execute('CREATE TABLE "chat" (id TEXT PRIMARY KEY)')
        db.execute(
            'CREATE TABLE "function" '
            '(id TEXT PRIMARY KEY, content TEXT, is_active INTEGER, is_global INTEGER)'
        )
        db.execute('INSERT INTO "user" (id) VALUES ("alice")')
        db.execute('INSERT INTO "chat" (id) VALUES ("chat1")')
        db.execute(
            'INSERT INTO "function" VALUES '
            '("clawfedora", "def action(): pass", 1, 1)'
        )
    return path


def test_disposable_webui_migration_preserves_counts_and_exact_functions(
    tmp_path: Path,
) -> None:
    original = _db(tmp_path / "before.db")
    migrated = tmp_path / "canary.db"
    shutil.copyfile(original, migrated)
    initial = snapshot(original)
    assert verify_preservation(initial, snapshot(migrated)) == {
        "verdict": "PASS",
        "tables_preserved": ["user", "chat", "function"],
        "functions_preserved": 1,
        "scope": "disposable_sqlite_canary_only",
    }
    with sqlite3.connect(migrated) as db:
        db.execute('INSERT INTO "chat" (id) VALUES ("new-chat")')
    assert verify_preservation(initial, snapshot(migrated))["verdict"] == "PASS"


@pytest.mark.parametrize("change", ["remove-user", "remove-function", "mutate-function"])
def test_webui_migration_detects_data_or_plugin_regressions(
    tmp_path: Path, change: str,
) -> None:
    before = _db(tmp_path / "before.db")
    after = tmp_path / "after.db"
    shutil.copyfile(before, after)
    sql = {
        "remove-user": 'DELETE FROM "user"',
        "remove-function": 'DELETE FROM "function"',
        "mutate-function": 'UPDATE "function" SET is_global=0',
    }[change]
    with sqlite3.connect(after) as db:
        db.execute(sql)
    with pytest.raises(ValueError):
        verify_preservation(snapshot(before), snapshot(after))


def test_canary_rejects_symlink_and_missing_tables(tmp_path: Path) -> None:
    real = _db(tmp_path / "real.db")
    symlink = tmp_path / "symlink.db"
    symlink.symlink_to(real)
    with pytest.raises(ValueError, match="liée"):
        snapshot(symlink)
    with sqlite3.connect(tmp_path / "empty.db"):
        pass
    with pytest.raises(ValueError, match="tables"):
        snapshot(tmp_path / "empty.db")


def test_same_count_chat_replacement_and_content_edit_are_detected(tmp_path: Path) -> None:
    original = _db(tmp_path / "original.db")
    initial = snapshot(original)
    replacement = tmp_path / "replacement.db"
    shutil.copyfile(original, replacement)
    with sqlite3.connect(replacement) as db:
        db.execute('UPDATE "chat" SET id="different-chat"')
    assert snapshot(replacement)["counts"] == initial["counts"]
    with pytest.raises(ValueError, match="identité WebUI"):
        verify_preservation(initial, snapshot(replacement))


def test_chat_json_payload_drift_is_detected(tmp_path: Path) -> None:
    path = _db(tmp_path / "original.db")
    with sqlite3.connect(path) as db:
        db.execute('ALTER TABLE "chat" ADD COLUMN chat TEXT')
        db.execute('UPDATE "chat" SET chat=?', ('{"history":["original"]}',))
    initial = snapshot(path)
    migrated = tmp_path / "migrated.db"
    shutil.copyfile(path, migrated)
    with sqlite3.connect(migrated) as db:
        db.execute('UPDATE "chat" SET chat=?', ('{"history":["changed"]}',))
    assert snapshot(migrated)["counts"] == initial["counts"]
    with pytest.raises(ValueError, match="contenu ou identité"):
        verify_preservation(initial, snapshot(migrated))
