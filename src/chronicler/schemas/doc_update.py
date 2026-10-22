"""DocUpdatePayload — the generated-markdown-to-target-paths data contract."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DocFormat(StrEnum):
    """Format of a generated lore document."""

    MARKDOWN = "markdown"
    API_MAP = "api_map"
    SYSTEM_STATE = "system_state"


class DocUpdatePayload(BaseModel):
    """Structured map of generated markdown pointing at target file paths."""

    model_config = ConfigDict(frozen=True)

    payload_id: str = Field(..., description="Lore payload identifier, e.g. 'doc-<heuristic-id>'")
    title: str = Field(..., description="Human-readable title of the generated doc")
    summary: str = Field(..., description="One-paragraph abstract of the lesson")
    format: DocFormat = Field(default=DocFormat.MARKDOWN, description="Output format of the markdown")
    content_markdown: str = Field(default="", description="Generated markdown body")
    target_paths: list[str] = Field(
        default_factory=list,
        description="Target file paths inside the repo the markdown should be written to",
    )
    heuristic_ids: list[str] = Field(
        default_factory=list,
        description="Source heuristic ids this doc synthesizes",
    )

    @model_validator(mode="before")
    @classmethod
    def _apply_defaults(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        payload = dict(data)
        if not payload.get("target_paths"):
            payload["target_paths"] = [f"docs/lore/{payload.get('payload_id') or 'doc'}.md"]
        return payload

    @property
    def markdown_by_path(self) -> dict[str, str]:
        """Map of target path -> generated markdown content."""
        paths = self.target_paths or [f"docs/lore/{self.payload_id}.md"]
        return dict.fromkeys(paths, self.content_markdown)
