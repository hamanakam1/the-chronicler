"""Lore synthesis: translate learned heuristics into generated markdown docs."""

from chronicler.llm.client import OllamaClient
from chronicler.llm.prompts import DOC_SYNTHESIS_SYSTEM_PROMPT, build_doc_prompt
from chronicler.schemas import DocUpdatePayload
from chronicler.schemas.audit_log import ExecutionAuditLog
from chronicler.schemas.heuristic import ExtractedHeuristic


class DocSynthesizer:
    """Turns a learned heuristic plus raw battle scar into a DocUpdatePayload."""

    def __init__(self, llm: OllamaClient, lore_dir: str = "docs/lore") -> None:
        self.llm = llm
        self.lore_dir = lore_dir

    async def synthesize(self, heuristic: ExtractedHeuristic, audit: ExecutionAuditLog) -> DocUpdatePayload:
        prompt = build_doc_prompt(heuristic, audit)
        data = await self.llm.ask_for_json(prompt, system=DOC_SYNTHESIS_SYSTEM_PROMPT)
        payload = DocUpdatePayload.model_validate(
            {
                "payload_id": f"doc-{heuristic.heuristic_id}",
                "title": str(data.get("title") or f"Chronicler Lore: {heuristic.failure_category}"),
                "summary": str(data.get("summary") or heuristic.insight),
                "format": data.get("format") or "markdown",
                "content_markdown": str(data.get("content_markdown") or ""),
                "target_paths": [f"{self.lore_dir}/{heuristic.heuristic_id}.md"],
                "heuristic_ids": [heuristic.heuristic_id],
            }
        )
        return payload
