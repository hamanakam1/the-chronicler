"""Dynamic rule hardening: drafts new architectural rules from learned heuristics."""

from pydantic import BaseModel, Field


class RuleDraft(BaseModel):
    """A freshly drafted rule ready to be written into the target repo."""

    rule_id: str
    heuristic_id: str
    title: str
    rationale: str
    rule: str
    content_markdown: str
    content_json: dict


class RuleHardener:
    """Keeps the set of known heuristics and drafts new rules from them."""

    def __init__(self, processed_heuristic_ids: list[str] | None = None) -> None:
        self._known_ids = set(processed_heuristic_ids or [])

    def is_known(self, heuristic_id: str) -> bool:
        return heuristic_id in self._known_ids

    def register(self, heuristic_id: str) -> None:
        self._known_ids.add(heuristic_id)

    def draft(self, heuristic) -> RuleDraft:
        """Draft a hardened rule (markdown + JSON payloads) from a learned heuristic."""
        rule_id = f"rule-{heuristic.heuristic_id}"
        title = f"Chronicler Rule: {heuristic.failure_category}"
        content_markdown = (
            f"# {title}\n\n"
            f"**Insight:** {heuristic.insight}\n\n"
            f"**The Golden Rule:** {heuristic.generalized_rule}\n\n"
            f"**Source:** failure `{heuristic.source_fingerprint}` on task `{heuristic.task_id}`.\n"
        )
        content_json = {
            "id": rule_id,
            "heuristic_id": heuristic.heuristic_id,
            "failure_category": heuristic.failure_category,
            "insight": heuristic.insight,
            "rule": heuristic.generalized_rule,
            "confidence": heuristic.confidence,
        }
        return RuleDraft(
            rule_id=rule_id,
            heuristic_id=heuristic.heuristic_id,
            title=title,
            rationale="Auto-drafted by The Chronicler from a recurring execution failure.",
            rule=heuristic.generalized_rule,
            content_markdown=content_markdown,
            content_json=content_json,
        )
