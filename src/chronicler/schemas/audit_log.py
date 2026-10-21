"""ExecutionAuditLog — the raw friction data contract pulled from EdgeRecord."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ExecutionAuditLog(BaseModel):
    """A single "battle scar" scooped from the append-only EdgeRecord ledger."""

    model_config = ConfigDict(frozen=True)

    audit_id: str = Field(..., description="Unique ledger audit identifier")
    task_id: str = Field(..., description="Task the failure belonged to")
    session_id: str | None = Field(default=None, description="Owning session, when known")
    category: str = Field(..., description="Failure category, e.g. network_config, build, auth")
    fingerprint: str = Field(..., description="Stable hash/signature of the error")
    summary: str = Field(..., description="Raw error text, stack trace, or failure note")
    resolution: str | None = Field(default=None, description="Correction that eventually fixed it")
    source: str = Field(default="failures", description="Ledger table the audit was scooped from")
    created: datetime = Field(..., description="Ledger timestamp of the failure")

    @property
    def error_excerpt(self) -> str:
        """Truncated summary safe for LLM context windows and logs."""
        return self.summary[:2000]
