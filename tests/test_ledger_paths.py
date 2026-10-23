"""Filesystem names must not change which ledger or SQLite mode is opened."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from chronicler.errors import LedgerError
from chronicler.ledger.reader import SqliteEdgeRecordReader


def _ledger(path: Path, fingerprint: str) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE tasks (id TEXT PRIMARY KEY);
            CREATE TABLE failures (
                id INTEGER PRIMARY KEY, task_id TEXT, session_id TEXT, category TEXT,
                fingerprint TEXT, summary TEXT, created REAL
            );
            CREATE TABLE events (seq INTEGER PRIMARY KEY, type TEXT, task_id TEXT, data TEXT, created REAL);
            """
        )
        connection.execute(
            "INSERT INTO failures VALUES (1, 'synthetic-task', NULL, 'synthetic', ?, 'synthetic failure', 1760000100.0)",
            (fingerprint,),
        )


@pytest.mark.parametrize("name", ["ledger#archive.sqlite", "ledger?mode=rw", "ledger%23archive.sqlite", "ledger space 日本.sqlite"])
@pytest.mark.parametrize("relative", [False, True], ids=["absolute", "relative"])
def test_reader_uses_exact_filesystem_path_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, relative: bool
) -> None:
    # URI metacharacters must not redirect the read to either decoy.
    _ledger(tmp_path / "ledger", "synthetic-decoy")
    if name != "ledger#archive.sqlite":
        _ledger(tmp_path / "ledger#archive.sqlite", "synthetic-percent-decoy")
    target = tmp_path / name
    _ledger(target, "synthetic-requested")
    monkeypatch.chdir(tmp_path)
    reader = SqliteEdgeRecordReader(name if relative else str(target))

    audits = reader.fetch_new_failures(since=None, limit=10)

    assert [audit.fingerprint for audit in audits] == ["synthetic-requested"]
    connection = reader._connect()
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute("INSERT INTO tasks VALUES ('synthetic-write')")
    finally:
        connection.close()


def test_missing_path_with_fragment_cannot_read_a_different_ledger(tmp_path: Path) -> None:
    _ledger(tmp_path / "ledger", "synthetic-decoy")
    target = tmp_path / "ledger#missing.sqlite"

    with pytest.raises(LedgerError):
        SqliteEdgeRecordReader(str(target)).fetch_new_failures(since=None, limit=1)

    assert not target.exists()
