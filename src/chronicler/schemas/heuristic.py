"""ExtractedHeuristic — the 'Aha!' moment data contract."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class HeuristicStatus(StrEnum):
    """Lifecycle state of a learned heuristic."""

    DRAFT = "draft"
    PROMOTED = "promoted"


class ExtractedHeuristic(BaseModel):
    """A newly learned architectural rule distilled from messy failure data."""

    model_config = ConfigDict(frozen=True)

    heuristic_id: str = Field(..., description="Deterministic id, e.g. 'heur-<12 hex>'")
    source_fingerprint: str = Field(..., description="Fingerprint of the originating failure")
    task_id: str = Field(..., description="Task where the failure surfaced")
    failure_category: str = Field(..., description="Category of the failure")
    insight: str = Field(..., description="Why the bot failed (the root cause)")
    generalized_rule: str = Field(..., description="The golden, generalized rule to encode")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="Model confidence in the heuristic")
    status: HeuristicStatus = Field(default=HeuristicStatus.DRAFT, description="Draft vs promoted")

    @property
    def fingerprint(self) -> str:
        """Alias mirroring the source failure fingerprint."""
        return self.source_fingerprint
