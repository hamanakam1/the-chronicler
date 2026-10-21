"""Local LLM brain for The Chronicler."""

from chronicler.llm.client import OllamaClient
from chronicler.llm.prompts import DOC_SYNTHESIS_SYSTEM_PROMPT, EXTRACTION_SYSTEM_PROMPT, THE_PERMANENT_FIX_QUESTION, build_doc_prompt, build_extraction_prompt

__all__ = [
    "DOC_SYNTHESIS_SYSTEM_PROMPT",
    "EXTRACTION_SYSTEM_PROMPT",
    "OllamaClient",
    "THE_PERMANENT_FIX_QUESTION",
    "build_doc_prompt",
    "build_extraction_prompt",
]
