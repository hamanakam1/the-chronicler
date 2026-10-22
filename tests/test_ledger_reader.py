"""Tests for the EdgeRecord-backed ledger reader."""

import sqlite3
from datetime import UTC

from chronicler.errors import LedgerError
from chronicler.ledger.reader import SqliteEdgeRecordReader
from chronicler.schemas import ExecutionAuditLog


def _make_ledger(path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE tasks (
            id TEXT PRIMARY KEY, objective TEXT NOT NULL, acceptance TEXT NOT NULL,
            kind TEXT NOT NULL, scope TEXT NOT NULL, status TEXT NOT NULL,
            token_budget INTEGER NOT NULL, created REAL NOT NULL
        );
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id), owner TEXT NOT NULL,
            status TEXT NOT NULL, lease_until REAL NOT NULL, tokens INTEGER NOT NULL DEFAULT 0,
            progress TEXT NOT NULL DEFAULT '', stagnant INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL
        );
        CREATE TABLE failures (
            id INTEGER PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id),
            session_id TEXT REFERENCES sessions(id), category TEXT NOT NULL,
            fingerprint TEXT NOT NULL, summary TEXT NOT NULL, created REAL NOT NULL
        );
        CREATE TABLE events (
            seq INTEGER PRIMARY KEY, type TEXT NOT NULL, task_id TEXT,
            data TEXT NOT NULL, created REAL NOT NULL
        );
        INSERT INTO tasks (id, objective, acceptance, kind, scope, status, token_budget, created)
        VALUES ('task-1', 'fix network', 'agents can reach gateway', 'bug', 'net', 'done', 1000, 1760000000.0);
        INSERT INTO failures (id, task_id, session_id, category, fingerprint, summary, created)
        VALUES (1, 'task-1', 'sess-1', 'network_config', 'sha256:deadbeef', 'Could not resolve host gateway', 1760000100.0);
        INSERT INTO events (seq, type, task_id, data, created)
        VALUES (1, 'failure_resolved', 'task-1', '{"resolution": "Set the gateway manually"}', 1760000200.0);
        """
    )
    connection.commit()
    connection.close()


def test_sqlite_reader_returns_new_failures_with_resolution(tmp_path) -> None:
    ledger = tmp_path / "ledger.sqlite"
    _make_ledger(ledger)
    reader = SqliteEdgeRecordReader(str(ledger))

    audits = reader.fetch_new_failures(since=None, limit=10)
    assert len(audits) == 1
    audit = audits[0]
    assert isinstance(audit, ExecutionAuditLog)
    assert audit.task_id == "task-1"
    assert audit.category == "network_config"
    assert audit.fingerprint == "sha256:deadbeef"
    assert audit.resolution == "Set the gateway manually"


def test_sqlite_reader_respects_watermark(tmp_path) -> None:
    ledger = tmp_path / "ledger.sqlite"
    _make_ledger(ledger)
    reader = SqliteEdgeRecordReader(str(ledger))

    from datetime import datetime

    audits = reader.fetch_new_failures(since=datetime.fromtimestamp(1760000050, tz=UTC), limit=10)
    assert len(audits) == 1
    assert audits[0].fingerprint == "sha256:deadbeef"

    audits = reader.fetch_new_failures(since=datetime.fromtimestamp(1760000100, tz=UTC), limit=10)
    assert audits == []


def test_sqlite_reader_missing_ledger_raises(tmp_path) -> None:
    reader = SqliteEdgeRecordReader(str(tmp_path / "nope.sqlite"))
    try:
        reader.fetch_new_failures(since=None, limit=5)
        raise AssertionError("expected LedgerError")
    except LedgerError:
        pass
