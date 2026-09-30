from __future__ import annotations

import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

import pytest

from app.backup import backup_database, main


def test_backup_and_restore_include_committed_wal_but_not_uncommitted_rows(tmp_path: Path) -> None:
    source = tmp_path / "live #数据库.db"
    backup = tmp_path / "backup.db"
    restored = tmp_path / "restored.db"
    with closing(sqlite3.connect(source)) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("CREATE TABLE records (value TEXT)")
        writer.execute("INSERT INTO records VALUES ('committed')")
        writer.commit()
        assert Path(f"{source}-wal").stat().st_size > 0
        writer.execute("INSERT INTO records VALUES ('uncommitted')")
        backup_database(source, backup)
        assert writer.execute("SELECT COUNT(*) FROM records").fetchone() == (2,)
        writer.rollback()
    backup_database(backup, restored)
    with closing(sqlite3.connect(restored)) as database:
        assert database.execute("SELECT value FROM records").fetchall() == [("committed",)]
        assert database.execute("PRAGMA quick_check").fetchone() == ("ok",)
    if os.name != "nt":
        assert backup.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("same_file", [False, True])
def test_backup_preserves_existing_destination(tmp_path: Path, same_file: bool) -> None:
    source = tmp_path / "source.db"
    with closing(sqlite3.connect(source)) as database:
        database.execute("CREATE TABLE records (value TEXT)")
    destination = source if same_file else tmp_path / "existing.db"
    if not same_file:
        destination.write_bytes(b"preserve-existing-content")
    before = destination.read_bytes()
    with pytest.raises(FileExistsError):
        backup_database(source, destination)
    assert destination.read_bytes() == before


@pytest.mark.parametrize("missing", [False, True])
def test_failed_backup_leaves_no_partial_destination(tmp_path: Path, missing: bool) -> None:
    source = tmp_path / "invalid.db"
    destination = tmp_path / "backup.db"
    if not missing:
        source.write_bytes(b"not-a-sqlite-database")
    with pytest.raises((FileNotFoundError, sqlite3.DatabaseError)):
        backup_database(source, destination)
    assert not destination.exists()


def test_cli_reports_failure_without_exposing_database_contents(
    tmp_path: Path, monkeypatch, capsys,
) -> None:
    source = tmp_path / "source.db"
    destination = tmp_path / "backup.db"
    with closing(sqlite3.connect(source)) as database:
        database.execute("CREATE TABLE records (value TEXT)")
        database.execute("INSERT INTO records VALUES ('private-test-record')")
        database.commit()
    monkeypatch.setattr(sys, "argv", ["app.backup", str(source), str(destination)])
    main()
    success = capsys.readouterr()
    assert success.out.strip() == "SQLite backup and integrity check PASS"
    before = destination.read_bytes()
    with pytest.raises(SystemExit) as failure:
        main()
    assert failure.value.code == 1
    error = capsys.readouterr().err
    assert "FileExistsError" in error
    assert "private-test-record" not in success.out + error
    assert destination.read_bytes() == before
