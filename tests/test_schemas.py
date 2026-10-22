"""Data contract tests for The Chronicler's Pydantic schemas."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from chronicler.schemas import DocFormat, DocUpdatePayload, ExecutionAuditLog, ExtractedHeuristic, HeuristicStatus


def test_execution_audit_log_requires_core_fields() -> None:
    with pytest.raises(ValueError):
        ExecutionAuditLog(task_id="task-1", category="network_config", fingerprint="sha256:x", summary="boom")


def test_execution_audit_log_defaults_and_excerpt() -> None:
    audit = ExecutionAuditLog(
        audit_id="audit-1",
        task_id="task-1",
        category="network_config",
        fingerprint="sha256:x",
        summary="boom",
        created=datetime.now(UTC),
    )
    assert audit.resolution is None
    assert audit.source == "failures"
    assert audit.error_excerpt == "boom"


def test_extracted_heuristic_lifecycle_defaults() -> None:
    heuristic = ExtractedHeuristic(
        heuristic_id="heur-abc123",
        source_fingerprint="sha256:x",
        task_id="task-1",
        failure_category="network_config",
        insight="The bot guessed the gateway.",
        generalized_rule="Always resolve the gateway from the compose file.",
    )
    assert heuristic.confidence == 0.5
    assert heuristic.status is HeuristicStatus.DRAFT
    assert heuristic.fingerprint == "sha256:x"


def test_extracted_heuristic_confidence_is_bounded() -> None:
    base = {
        "heuristic_id": "heur-abc123",
        "source_fingerprint": "sha256:x",
        "task_id": "task-1",
        "failure_category": "network_config",
        "insight": "The bot guessed the gateway.",
        "generalized_rule": "Always resolve the gateway from the compose file.",
    }
    assert ExtractedHeuristic(**base, confidence=1.0).confidence == 1.0
    with pytest.raises(ValidationError):
        ExtractedHeuristic(**base, confidence=1.5)  # type: ignore[arg-type]


def test_doc_update_payload_targets_default_to_lore_path() -> None:
    payload = DocUpdatePayload(
        payload_id="doc-heur-abc123",
        title="Chronicler Lore: network_config",
        summary="The bot guessed the gateway.",
        content_markdown="# Lore",
    )
    assert payload.format is DocFormat.MARKDOWN
    assert payload.target_paths == ["docs/lore/doc-heur-abc123.md"]
    assert payload.markdown_by_path == {"docs/lore/doc-heur-abc123.md": "# Lore"}


def test_doc_update_payload_explicit_targets_are_respected() -> None:
    payload = DocUpdatePayload(
        payload_id="doc-heur-abc123",
        title="Chronicler Lore: network_config",
        summary="The bot guessed the gateway.",
        content_markdown="# Lore",
        target_paths=["RULES.json"],
        heuristic_ids=["heur-abc123"],
    )
    assert payload.markdown_by_path == {"RULES.json": "# Lore"}
    assert payload.heuristic_ids == ["heur-abc123"]
