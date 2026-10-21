"""Heuristics extraction: map raw LLM JSON payloads onto the ExtractedHeuristic contract."""

import hashlib

from chronicler.schemas import ExtractedHeuristic
from chronicler.schemas.audit_log import ExecutionAuditLog


def heuristic_id_for(fingerprint: str, failure_category: str) -> str:
    """Deterministic heuristic id derived from the failure signature + category."""
    digest = hashlib.sha1(f"{failure_category}:{fingerprint}".encode("utf-8")).hexdigest()[:12]
    return f"heur-{digest}"


class HeuristicExtractor:
    """Turns local-LLM JSON responses into typed, dedupe-friendly heuristics."""

    def extract(self, audit: ExecutionAuditLog, raw_payload: dict) -> ExtractedHeuristic:
        heuristic_id = heuristic_id_for(audit.fingerprint, audit.category)
        return ExtractedHeuristic(
            heuristic_id=heuristic_id,
            source_fingerprint=audit.fingerprint,
            task_id=audit.task_id,
            failure_category=audit.category,
            insight=str(raw_payload.get("insight") or raw_payload.get("root_cause") or ""),
            generalized_rule=str(raw_payload.get("generalized_rule") or raw_payload.get("permanent_fix") or ""),
            confidence=float(raw_payload.get("confidence") or 0.5),
        )
