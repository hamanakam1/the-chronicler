"""Prompt builders + system prompts for The Chronicler's local LLM brain."""

from chronicler.schemas import DocFormat
from chronicler.schemas.audit_log import ExecutionAuditLog
from chronicler.schemas.heuristic import ExtractedHeuristic

THE_PERMANENT_FIX_QUESTION = "What did the bots mess up, and what's the permanent fix?"

EXTRACTION_SYSTEM_PROMPT = f"""You are the meta-learning brain of an autonomous AI software factory, codenamed The Chronicler.

Your job is to analyze execution failures and distill durable, generalized lessons.

Answer the question: "{THE_PERMANENT_FIX_QUESTION}"

Respond with a single JSON object with exactly these keys:
- "insight": why the execution bot failed (root cause, in one or two sentences).
- "generalized_rule": the golden permanent fix/rule to encode so the bot never repeats this mistake (one or two sentences, imperative tone).
- "confidence": a float between 0.0 and 1.0 for how certain you are in the heuristic.

No prose outside the JSON object."""

EXTRACTION_USER_PROMPT = """Analyze the following execution failure and report the permanent fix.

Battle scar:
- Task: {task_id}
- Category: {category}
- Fingerprint: {fingerprint}
- Error: {summary}
- Recorded resolution: {resolution}

What did the bots mess up, and what's the permanent fix?"""


DOC_SYNTHESIS_SYSTEM_PROMPT = """You are the lore synthesis engine of The Chronicler.

You translate a learned failure heuristic into a beautiful, human-readable markdown lore document.

Respond with a single JSON object with exactly these keys:
- "title": the doc title.
- "summary": one-paragraph abstract of the lesson.
- "format": one of "markdown", "api_map", "system_state".
- "content_markdown": the full markdown body of the document.
- "heuristic_ids": list of source heuristic ids.

No prose outside the JSON object."""


def build_extraction_prompt(audit: ExecutionAuditLog) -> str:
    return EXTRACTION_USER_PROMPT.format(
        task_id=audit.task_id,
        category=audit.category,
        fingerprint=audit.fingerprint,
        summary=audit.error_excerpt,
        resolution=audit.resolution or "none recorded",
    )


def build_doc_prompt(heuristic: ExtractedHeuristic, audit: ExecutionAuditLog) -> str:
    return f"""Synthesize a lore document from the following learned heuristic.

Heuristic insight: {heuristic.insight}
Generalized rule: {heuristic.generalized_rule}
Failure category: {heuristic.failure_category}
Source task: {heuristic.task_id}

Battle scar: {audit.error_excerpt}

Write the markdown doc now. Target format: {DocFormat.MARKDOWN.value}."""
