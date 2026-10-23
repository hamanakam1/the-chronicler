"""Bounded batches must preserve every row at a timestamp boundary, even after restart."""

from __future__ import annotations

import asyncio
import json
import math
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from chronicler.brain.state_store import JsonStateStore
from chronicler.config import ChroniclerConfig
from chronicler.ledger.reader import SqliteEdgeRecordReader
from chronicler.ledger.watcher import EdgeRecordWatcher
from conftest import build_brain


def _make_ledger(path: Path, timestamp: float) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE tasks (id TEXT PRIMARY KEY);
            CREATE TABLE failures (
                id INTEGER PRIMARY KEY, task_id TEXT, session_id TEXT, category TEXT,
                fingerprint TEXT, summary TEXT, created REAL
            );
            CREATE TABLE events (seq INTEGER PRIMARY KEY, type TEXT, task_id TEXT, data TEXT, created REAL);
            INSERT INTO tasks VALUES ('synthetic-task');
            """
        )
        for failure_id, created in [
            (40, timestamp - 1),
            *((failure_id, timestamp) for failure_id in [2, 3, 9, 10, 11, 12, 20]),
            *((failure_id, timestamp + 1) for failure_id in [1, 5, 6]),
        ]:
            connection.execute(
                "INSERT INTO failures VALUES (?, 'synthetic-task', NULL, 'synthetic-category', ?, ?, ?)",
                (failure_id, f"synthetic-fingerprint-{failure_id}", "synthetic failure", created),
            )


def test_cursor_resumes_in_numeric_failure_id_order(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite"
    timestamp = 1760000100.0
    _make_ledger(path, timestamp)
    reader = SqliteEdgeRecordReader(str(path))

    batch = reader.fetch_new_failures(
        since=datetime.fromtimestamp(timestamp, tz=UTC), limit=3, after_failure_id=9
    )

    assert [audit.audit_id for audit in batch] == ["audit-10", "audit-11", "audit-12"]


@pytest.mark.parametrize("timestamp", [1760000100.0, 1760000100.1234567, 1760000100.1234562])
def test_brain_drains_equal_timestamps_with_strict_limit_across_restarts(
    tmp_path: Path, timestamp: float
) -> None:
    ledger_path = tmp_path / "ledger.sqlite"
    state_path = tmp_path / "state.json"
    _make_ledger(ledger_path, timestamp)
    config = ChroniclerConfig(audit_batch_limit=3, git_push=False)
    seen: list[str] = []

    for _ in range(8):
        reader = SqliteEdgeRecordReader(str(ledger_path))
        store = JsonStateStore(str(state_path))
        brain = build_brain(reader, state_store=store, config=config)
        brain.watcher = EdgeRecordWatcher(reader)
        report = asyncio.run(brain.run_cycle())
        assert report.failed_audits == []
        assert len(report.audits) <= config.audit_batch_limit
        if not report.audits:
            break
        seen.extend(audit.audit_id for audit in report.audits)

    assert seen == [f"audit-{failure_id}" for failure_id in [40, 2, 3, 9, 10, 11, 12, 20, 1, 5, 6]]
    saved = JsonStateStore(str(state_path)).load()
    assert saved.last_watermark_failure_id == 6
    assert saved.last_watermark == datetime.fromtimestamp(timestamp + 1, tz=UTC)
    assert len(saved.processed_heuristic_ids) == len(seen)


def test_distinct_real_timestamps_that_round_alike_keep_ledger_order(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.sqlite"
    timestamp = 1760000100.123456
    next_timestamp = math.nextafter(timestamp, math.inf)
    assert datetime.fromtimestamp(timestamp, tz=UTC) == datetime.fromtimestamp(next_timestamp, tz=UTC)
    _make_ledger(ledger_path, timestamp + 5)
    with sqlite3.connect(ledger_path) as connection:
        connection.execute("UPDATE failures SET created = ? WHERE id = 20", (timestamp,))
        connection.execute("UPDATE failures SET created = ? WHERE id = 2", (next_timestamp,))
    reader = SqliteEdgeRecordReader(str(ledger_path))
    brain = build_brain(reader, config=ChroniclerConfig(audit_batch_limit=1, git_push=False))
    brain.watcher = EdgeRecordWatcher(reader)

    first = asyncio.run(brain.run_cycle())
    second = asyncio.run(brain.run_cycle())
    third = asyncio.run(brain.run_cycle())

    assert [audit.audit_id for audit in first.audits] == ["audit-20"]
    assert [audit.audit_id for audit in second.audits] == ["audit-2"]
    assert [audit.audit_id for audit in third.audits] == ["audit-40"]


def test_legacy_timestamp_only_state_keeps_strict_timestamp_semantics(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.sqlite"
    state_path = tmp_path / "state.json"
    timestamp = 1760000100.0
    _make_ledger(ledger_path, timestamp)
    state_path.write_text(
        json.dumps({"last_watermark": datetime.fromtimestamp(timestamp, tz=UTC).isoformat()}), encoding="utf-8"
    )
    store = JsonStateStore(str(state_path))
    assert store.load().last_watermark_failure_id is None
    reader = SqliteEdgeRecordReader(str(ledger_path))
    brain = build_brain(reader, state_store=store, config=ChroniclerConfig(audit_batch_limit=2, git_push=False))
    brain.watcher = EdgeRecordWatcher(reader)

    first = asyncio.run(brain.run_cycle())
    second = asyncio.run(brain.run_cycle())

    assert [audit.audit_id for audit in first.audits] == ["audit-1", "audit-5"]
    assert [audit.audit_id for audit in second.audits] == ["audit-6"]


def test_reader_returns_timezone_aware_watermarks(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.sqlite"
    timestamp = 1760000100.0
    _make_ledger(ledger_path, timestamp)

    audit = SqliteEdgeRecordReader(str(ledger_path)).fetch_new_failures(since=None, limit=1)[0]

    assert audit.created == datetime.fromtimestamp(timestamp - 1, tz=UTC)
    assert audit.created.tzinfo is UTC
