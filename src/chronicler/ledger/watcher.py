"""Async watcher that polls the EdgeRecord ledger for new failure batches."""

from __future__ import annotations

import asyncio
from datetime import datetime

from chronicler.ledger.reader import EdgeRecordReader
from chronicler.schemas import ExecutionAuditLog


class EdgeRecordWatcher:
    """Continuously polls the EdgeRecord ledger and yields failure batches."""

    def __init__(self, reader: EdgeRecordReader, poll_interval: float = 30.0) -> None:
        self.reader = reader
        self.poll_interval = poll_interval

    async def poll_once(
        self, since: datetime | None = None, limit: int | None = None, *, after_failure_id: int | None = None
    ) -> list[ExecutionAuditLog]:
        """Scoop the latest batch of failure audits newer than the watermark."""
        effective_limit = limit if limit is not None else 25
        if after_failure_id is None:
            return await asyncio.to_thread(self.reader.fetch_new_failures, since, effective_limit)
        return await asyncio.to_thread(
            self.reader.fetch_new_failures, since, effective_limit, after_failure_id=after_failure_id
        )

    async def watch(self, since: datetime | None = None):
        """Infinite async iterator over failure batches; yields only non-empty batches."""
        while True:
            batch = await self.poll_once(since=since, limit=None)
            if batch:
                yield batch
            await asyncio.sleep(self.poll_interval)
