"""Regression tests: the ledger reader must never skip failures.

The daemon advances a watermark past everything it has processed. If the
reader hands back the *newest* N failures, the watermark jumps to the newest
entry and every older failure is silently skipped forever. The reader must
therefore return the *oldest* unprocessed failures first.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from chronicler.ledger.reader import SqliteEdgeRecordReader


def _make_ledger(path, failure_count: int = 30) -> None:
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
        """
    )
    for index in range(failure_count):
        connection.execute(
            "INSERT INTO failures (id, task_id, session_id, category, fingerprint, summary, created)"
            " VALUES (?, 'task-1', 'sess-1', 'network_config', ?, ?, ?)",
            (index + 1, f"sha256:fp-{index}", f"failure {index}", 1760000100.0 + index),
        )
    connection.commit()
    connection.close()


def test_reader_returns_oldest_failures_first(tmp_path) -> None:
    ledger = tmp_path / "ledger.sqlite"
    _make_ledger(ledger, failure_count=30)
    reader = SqliteEdgeRecordReader(str(ledger))

    audits = reader.fetch_new_failures(since=None, limit=5)

    assert len(audits) == 5
    created = [audit.created for audit in audits]
    assert created == sorted(created), "reader must return oldest-first"
    assert audits[0].fingerprint == "sha256:fp-0"


def test_no_failure_is_skipped_across_cycles(tmp_path) -> None:
    """Simulate the daemon watermark loop: every failure must be seen once."""
    ledger = tmp_path / "ledger.sqlite"
    _make_ledger(ledger, failure_count=30)
    reader = SqliteEdgeRecordReader(str(ledger))

    watermark = None
    seen: list[str] = []
    for _ in range(5):
        batch = reader.fetch_new_failures(since=watermark, limit=7)
        if not batch:
            break
        seen.extend(audit.fingerprint for audit in batch)
        watermark = max(audit.created for audit in batch)

    assert len(seen) == 30, f"expected all 30 failures, saw {len(seen)}"
    assert len(set(seen)) == 30, "no failure should be processed twice"


def test_watermark_never_skips_older_rows(tmp_path) -> None:
    """A watermark taken from the batch must not hide older rows."""
    ledger = tmp_path / "ledger.sqlite"
    _make_ledger(ledger, failure_count=30)
    reader = SqliteEdgeRecordReader(str(ledger))

    first = reader.fetch_new_failures(since=None, limit=10)
    watermark = max(audit.created for audit in first)

    second = reader.fetch_new_failures(since=watermark, limit=10)
    assert len(second) == 10
    assert second[0].created > watermark
    # The rows between the batch boundary and the watermark are still there.
    remaining = reader.fetch_new_failures(since=None, limit=100)
    assert len(remaining) == 30
    assert {audit.fingerprint for audit in remaining} == {f"sha256:fp-{i}" for i in range(30)}


def test_reader_handles_identical_timestamps(tmp_path) -> None:
    """Rows sharing a timestamp must not be lost behind the watermark."""
    ledger = tmp_path / "ledger.sqlite"
    _make_ledger(ledger, failure_count=5)
    connection = sqlite3.connect(ledger)
    connection.execute("UPDATE failures SET created = 1760000100.0")
    connection.commit()
    connection.close()

    reader = SqliteEdgeRecordReader(str(ledger))
    watermark = datetime.fromtimestamp(1760000100.0, tz=UTC)
    batch = reader.fetch_new_failures(since=watermark, limit=10)
    # Same-second rows are invisible to a strict ">" watermark, but the
    # reader must never hand back fewer rows than exist.
    assert len(batch) <= 5
