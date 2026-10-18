"""Synthetic cross-component recovery: projects, WebUI SQLite, and backup integrity.

This is not an end-to-end test of Fedora GNOME, a running WebUI browser,
the Arc B580, real cloud billing, or a live model.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from clawfedora.backup_acceptance import verify_backup_restore
from clawfedora.chat_projects import list_projects
from clawfedora.lifecycle import create_backup, restore_backup
from clawfedora.project_intake import create_project

ROOT = Path(__file__).resolve().parents[1]


def test_four_projects_and_webui_database_survive_backup_restore(
    tmp_path: Path,
) -> None:
    runtime = tmp_path / "production-fake"
    (runtime / "state/webui/data").mkdir(parents=True)
    (runtime / ".openclaw-fedora-runtime").write_text("managed", encoding="utf-8")
    request = tmp_path / "input.md"
    request.write_text("Expliquer une infrastructure Terraform et Ansible.", encoding="utf-8")
    for index in range(1, 5):
        slug = f"atelier-{index}"
        project = create_project(
            ROOT, runtime, slug, f"Projet {index}", intake_items=[request],
        )
        (project / "work").mkdir(exist_ok=True)
        (project / "work" / "notes.txt").write_text(
            f"Travail du projet {index}", encoding="utf-8"
        )

    database = runtime / "state/webui/data/webui.db"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE smoke (id INTEGER PRIMARY KEY, value TEXT)")
        db.execute("INSERT INTO smoke VALUES (1, 'WebUI preserved')")

    # Tokens must not be restored as valid access credentials.
    (runtime / "state/webui/bridge.token").write_text("synthetic-secret", encoding="utf-8")
    before = {item["id"] for item in list_projects(ROOT, runtime)}
    assert before == {f"atelier-{n}" for n in range(1, 5)}

    archive = create_backup(runtime)
    evidence = verify_backup_restore(archive)
    assert evidence["verdict"] == "RESTORE_VERIFIED"
    assert evidence["sqlite_databases_checked"] == 1

    restored = tmp_path / "restored-copy"
    restore_backup(archive, restored)
    after = {item["id"] for item in list_projects(ROOT, restored)}
    assert after == before
    for index in range(1, 5):
        note = restored / f"projects/atelier-{index}/work/notes.txt"
        assert note.read_text(encoding="utf-8") == f"Travail du projet {index}"
    assert not (restored / "state/webui/bridge.token").exists()
    with sqlite3.connect(restored / "state/webui/data/webui.db") as db:
        assert db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert db.execute("SELECT value FROM smoke WHERE id=1").fetchone()[0] == (
            "WebUI preserved"
        )
    assert (
        runtime / "state/webui/bridge.token"
    ).read_text(encoding="utf-8") == "synthetic-secret"
