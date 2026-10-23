"""EdgeRecord append-only ledger reader protocol + SQLite implementation."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from chronicler.errors import LedgerError
from chronicler.schemas import ExecutionAuditLog

RESOLUTION_EVENT_TYPES = frozenset(
    {
        "failure_resolved",
        "failures_resolved",
        "resolved",
        "failure_fixed",
        "failures_fixed",
        "fixed",
        "retry_resolved",
        "correction_applied",
    }
)


@runtime_checkable
class EdgeRecordReader(Protocol):
    """Reads new friction entries out of the append-only ledger."""

    def fetch_new_failures(
        self, since: datetime | None, limit: int, *, after_failure_id: int | None = None
    ) -> list[ExecutionAuditLog]:
        """Return audits after the timestamp/ID cursor, ordered by timestamp then numeric ID."""
        ...


def failure_id_for(audit: ExecutionAuditLog) -> int | None:
    """Decode SQLite's audit identifier without assuming other readers use numeric IDs."""
    if audit.source != "failures" or not audit.audit_id.startswith("audit-"):
        return None
    try:
        failure_id = int(audit.audit_id.removeprefix("audit-"))
    except ValueError:
        return None
    return failure_id if audit.audit_id == f"audit-{failure_id}" else None


class SqliteEdgeRecordReader:
    """SQLite-backed reader for the Taskrivet EdgeRecord ledger."""

    def __init__(self, path: str) -> None:
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, timeout=10.0)
        connection.row_factory = sqlite3.Row
        return connection

    def fetch_new_failures(
        self, since: datetime | None, limit: int, *, after_failure_id: int | None = None
    ) -> list[ExecutionAuditLog]:
        """Scoop failure audits newer than `since`, joining task context for the LLM brain.

        Rows are returned **oldest first**. The daemon advances a watermark to
        the newest row it processed, so handing back the newest N rows would
        hide every older row behind the watermark and skip it forever.
        An ID resumes within the boundary timestamp; timestamp-only callers
        keep the original strictly-newer semantics.
        """
        effective_limit = max(1, limit)
        connection = None
        try:
            connection = self._connect()
            since_ts = since.timestamp() if since is not None else None
            if since is not None and after_failure_id is not None:
                boundary = connection.execute(
                    "SELECT created FROM failures WHERE id = ?", (after_failure_id,)
                ).fetchone()
                # Datetime JSON rounds to microseconds; the append-only row retains
                # the original REAL timestamp needed for exact SQL comparisons.
                if boundary is not None and self._as_datetime(boundary["created"]).timestamp() == since_ts:
                    since_ts = boundary["created"]
            rows = connection.execute(
                """
                SELECT f.id AS failure_id, f.task_id AS task_id, f.session_id AS session_id,
                       f.category AS category, f.fingerprint AS fingerprint, f.summary AS summary,
                       f.created AS created
                FROM failures f
                LEFT JOIN tasks t ON t.id = f.task_id
                WHERE (? IS NULL OR f.created > ?
                       OR (? IS NOT NULL AND f.created = ? AND f.id > ?))
                ORDER BY f.created ASC, f.id ASC
                LIMIT ?
                """,
                (since_ts, since_ts, after_failure_id, since_ts, after_failure_id, effective_limit),
            ).fetchall()

            audits: list[ExecutionAuditLog] = []
            for row in rows:
                task_id = row["task_id"]
                created = self._as_datetime(row["created"])
                audits.append(
                    ExecutionAuditLog(
                        audit_id=f"audit-{row['failure_id']}",
                        task_id=task_id,
                        session_id=row["session_id"],
                        category=row["category"],
                        fingerprint=row["fingerprint"],
                        summary=row["summary"],
                        resolution=self._find_resolution(connection, task_id=task_id, after=created),
                        source="failures",
                        created=created,
                    )
                )
            return audits
        except sqlite3.Error as exc:
            raise LedgerError(f"failed to read EdgeRecord ledger at {self.path}: {exc}") from exc
        finally:
            if connection is not None:
                connection.close()

    def _find_resolution(self, connection: sqlite3.Connection, task_id: str, after: datetime) -> str | None:
        """Look for the correction that eventually resolved a failure via the events stream."""
        after_ts = after.timestamp()
        rows = connection.execute(
            """
            SELECT seq, type, data, created
            FROM events
            WHERE task_id = ? AND created > ?
            ORDER BY seq DESC
            LIMIT 25
            """,
            (task_id, after_ts),
        ).fetchall()
        for row in rows:
            event_type = (row["type"] or "").lower()
            if not (
                event_type in RESOLUTION_EVENT_TYPES or event_type.endswith("_resolved") or event_type.endswith("_fixed")
            ):
                continue
            payload = self._event_payload(row)
            for key in ("resolution", "fix", "fix_summary", "correction", "resolution_summary", "error_fix"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            if isinstance(payload.get("summary"), str) and payload["summary"].strip():
                return payload["summary"].strip()
        return None

    @staticmethod
    def _event_payload(row: sqlite3.Row) -> dict:
        try:
            parsed = json.loads(row["data"]) if row["data"] else {}
        except (ValueError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _as_datetime(value: object) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=UTC)
        return datetime.fromisoformat(str(value))
