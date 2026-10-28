"""Regression tests: one bad audit must not block the whole pipeline.

If a single failure produces an unusable LLM response, the cycle used to
raise before the watermark was saved. The daemon would then re-read the same
poison entry on every poll, forever, and never process the healthy audits
behind it.
"""

from __future__ import annotations

import pytest
from conftest import FakeCommitter, FakeLedgerReader, FakeLLM

from chronicler.brain.orchestrator import ChroniclerBrain
from chronicler.brain.state_store import InMemoryStateStore
from chronicler.errors import OllamaError
from chronicler.schemas import DocUpdatePayload, ExecutionAuditLog, ExtractedHeuristic


class PoisonLLM(FakeLLM):
    """An LLM that fails for one specific fingerprint and works for the rest."""

    def __init__(self, poison: str) -> None:
        super().__init__()
        self.poison = poison
        self.calls: list[str] = []

    async def ask_for_json(self, prompt, system=None):
        if self.poison in prompt:
            raise OllamaError("local LLM returned non-JSON output: not json at all")
        return await super().ask_for_json(prompt, system=system)


def _brain(reader, llm, state_store) -> ChroniclerBrain:
    from chronicler.brain.extraction import HeuristicExtractor
    from chronicler.config import ChroniclerConfig
    from chronicler.docs.synthesizer import DocSynthesizer
    from chronicler.ledger.watcher import EdgeRecordWatcher
    from chronicler.rules.hardener import RuleHardener

    config = ChroniclerConfig()
    return ChroniclerBrain(
        reader=reader,
        watcher=EdgeRecordWatcher(reader),
        llm=llm,
        extractor=HeuristicExtractor(),
        hardener=RuleHardener(),
        synthesizer=DocSynthesizer(llm, lore_dir=config.lore_dir),
        committer=FakeCommitter(),
        state_store=state_store,
        config=config,
    )


def _audit(fingerprint: str, created) -> ExecutionAuditLog:
    return ExecutionAuditLog(
        audit_id=f"audit-{fingerprint}",
        task_id="task-1",
        session_id="sess-1",
        category="network_config",
        fingerprint=fingerprint,
        summary="Could not resolve host gateway",
        resolution="Set the gateway manually",
        source="failures",
        created=created,
    )


@pytest.mark.asyncio
async def test_one_bad_audit_does_not_block_the_rest() -> None:
    from datetime import UTC, datetime

    base = datetime(2026, 10, 21, 10, 0, 0, tzinfo=UTC)
    audits = [
        _audit("sha256:poison", base),
        _audit("sha256:good-1", base.replace(minute=1)),
        _audit("sha256:good-2", base.replace(minute=2)),
    ]
    reader = FakeLedgerReader([audits])
    llm = PoisonLLM(poison="sha256:poison")
    state_store = InMemoryStateStore()

    brain = _brain(reader, llm, state_store)
    report = await brain.run_cycle()

    # The healthy audits still made it through.
    assert len(report.heuristics) == 2
    assert {h.source_fingerprint for h in report.heuristics} == {"sha256:good-1", "sha256:good-2"}
    # The poison audit is reported, not raised.
    assert len(report.failed_audits) == 1
    assert report.failed_audits[0]["fingerprint"] == "sha256:poison"
    assert report.failed_audits[0]["error"]
    # And the cycle completed rather than blowing up.
    assert report.error is None


@pytest.mark.asyncio
async def test_watermark_advances_past_a_failed_audit() -> None:
    """The daemon must not re-read a poison entry on every single poll."""
    from datetime import UTC, datetime

    base = datetime(2026, 10, 21, 10, 0, 0, tzinfo=UTC)
    audits = [
        _audit("sha256:poison", base),
        _audit("sha256:good-1", base.replace(minute=1)),
    ]
    reader = FakeLedgerReader([audits])
    llm = PoisonLLM(poison="sha256:poison")
    state_store = InMemoryStateStore()

    brain = _brain(reader, llm, state_store)
    await brain.run_cycle()

    saved = state_store.load()
    assert saved.last_watermark is not None
    assert saved.last_watermark == base.replace(minute=1)
    assert saved.cycles_completed == 1


@pytest.mark.asyncio
async def test_healthy_cycle_reports_no_failures() -> None:
    from datetime import UTC, datetime

    base = datetime(2026, 10, 21, 10, 0, 0, tzinfo=UTC)
    reader = FakeLedgerReader([[_audit("sha256:good", base)]])
    state_store = InMemoryStateStore()

    brain = _brain(reader, FakeLLM(), state_store)
    report = await brain.run_cycle()

    assert report.failed_audits == []
    assert report.error is None
    assert len(report.heuristics) == 1


@pytest.mark.asyncio
async def test_doc_synthesis_failure_is_isolated() -> None:
    """A failure during doc synthesis must not lose the extracted heuristic."""
    from datetime import UTC, datetime

    base = datetime(2026, 10, 21, 10, 0, 0, tzinfo=UTC)

    class BadDocLLM(FakeLLM):
        async def ask_for_json(self, prompt, system=None):
            if "Synthesize a lore document" in prompt:
                raise OllamaError("doc synthesis blew up")
            return await super().ask_for_json(prompt, system=system)

    reader = FakeLedgerReader([[_audit("sha256:bad-doc", base)]])
    state_store = InMemoryStateStore()

    brain = _brain(reader, BadDocLLM(), state_store)
    report = await brain.run_cycle()

    assert len(report.failed_audits) == 1
    assert report.failed_audits[0]["fingerprint"] == "sha256:bad-doc"
    # The heuristic was still extracted and recorded.
    assert len(report.heuristics) == 1
    assert report.doc_payloads == []


def test_doc_update_payload_is_still_constructible() -> None:
    """Guard the contract the synthesizer depends on."""
    payload = DocUpdatePayload(
        payload_id="doc-1",
        title="t",
        summary="s",
        content_markdown="# x",
        target_paths=["docs/lore/1.md"],
        heuristic_ids=["heur-1"],
    )
    assert payload.markdown_by_path == {"docs/lore/1.md": "# x"}
    assert isinstance(payload, DocUpdatePayload)
    assert ExtractedHeuristic is not None
