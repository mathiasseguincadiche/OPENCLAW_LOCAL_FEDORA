from __future__ import annotations

import io
import sqlite3
import tarfile
from pathlib import Path

import pytest

from clawfedora.backup_acceptance import verify_backup_restore
from clawfedora.lifecycle import create_backup


def test_real_archive_can_restore_sqlite_wal_and_sources_into_temporary_directory(
    tmp_path: Path,
) -> None:
    runtime = tmp_path / "managed"
    (runtime / "state/webui/data").mkdir(parents=True)
    (runtime / "projects/sample").mkdir(parents=True)
    (runtime / ".openclaw-fedora-runtime").write_text("managed")
    (runtime / "projects/sample/notes.md").write_text("instructions")
    database = runtime / "state/webui/data/webui.db"
    with sqlite3.connect(database) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE test (value TEXT)")
        db.execute("INSERT INTO test VALUES ('committed')")
    (runtime / "state/webui/bridge.token").write_text("must-not-be-in-archive")
    archive = create_backup(runtime)
    with tarfile.open(archive) as tar:
        names = set(tar.getnames())
    assert "state/webui/bridge.token" not in names
    result = verify_backup_restore(archive)
    assert result["verdict"] == "RESTORE_VERIFIED"
    assert result["sqlite_databases_checked"] == 1
    assert result["production_runtime_modified"] is False
    assert (runtime / "projects/sample/notes.md").read_text() == "instructions"


def test_archive_tampering_is_rejected(tmp_path: Path) -> None:
    runtime = tmp_path / "managed"
    (runtime / "state").mkdir(parents=True)
    (runtime / ".openclaw-fedora-runtime").write_text("managed")
    (runtime / "state/notes.txt").write_text("original")
    archive = create_backup(runtime)
    altered = tmp_path / "altered.tar.gz"
    with tarfile.open(archive, "r:gz") as source, tarfile.open(altered, "w:gz") as target:
        for member in source:
            content = source.extractfile(member) if member.isfile() else None
            if member.name == "state/notes.txt":
                payload = b"tampered"
                member.size = len(payload)
                content = io.BytesIO(payload)
            target.addfile(member, content)
    with pytest.raises(ValueError, match="intégrité"):
        verify_backup_restore(altered)


def test_backup_verifier_refuses_links(tmp_path: Path) -> None:
    target = tmp_path / "archive.tar.gz"
    target.write_bytes(b"empty")
    alias = tmp_path / "link.tar.gz"
    alias.symlink_to(target)
    with pytest.raises(ValueError, match="liée"):
        verify_backup_restore(alias)
