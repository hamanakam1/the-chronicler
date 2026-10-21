"""Chronicler brain state: ledger watermark, dedupe ids, and commit memory."""

from datetime import datetime

from pydantic import BaseModel, Field


class ChroniclerState(BaseModel):
    """Daemon-level memory: ledger watermark, processed heuristics, commit receipts."""

    last_watermark: datetime | None = None
    processed_heuristic_ids: list[str] = Field(default_factory=list)
    last_commit_sha: str | None = None
    last_commit_message: str | None = None
    cycles_completed: int = 0
    audits_seen: int = 0
    last_commit_at: datetime | None = None
