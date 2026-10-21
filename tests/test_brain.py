"""Tests for The Chronicler's meta-learning brain orchestration loop."""

import asyncio

from chronicler.brain.extraction import heuristic_id_for
from chronicler.brain.orchestrator import ChroniclerBrain, CycleReport
from chronicler.brain.state_store import InMemoryStateStore
from chronicler.docs.synthesizer import DocSynthesizer
from chronicler.gitops.committer import CommitReceipt, LocalGitCommitter
from chronicler.ledger.reader import EdgeRecordReader, SqliteEdgeRecordReader
from chronicler.ledger.watcher import EdgeRecordWatcher
from chronicler.llm.client import OllamaClient
from chronicler.llm.prompts import THE_PERMANENT_FIX_QUESTION
from chronicler.rules.hardener import RuleHardener
from chronicler.schemas import DocUpdatePayload

from conftest import FakeCommitter, FakeLLM, FakeLedgerReader, FakeWatcher, build_brain


def test_run_cycle_ingests_extracts_hardens_and_commits(make_audit) -> None:
    audit = make_audit()
    reader = FakeLedgerReader(batches=[[audit]])
    llm = FakeLLM()
    committer = FakeCommitter()
    brain = build_brain(reader, llm=llm, committer=committer)

    result = asyncio.run(brain.run_cycle())
    assert isinstance(result, CycleReport)
    assert len(result.audits) == 1
    assert len(result.heuristics) == 1
    heuristic = result.heuristics[0]
    assert heuristic.heuristic_id == heuristic_id_for(audit.fingerprint, audit.category)
    assert heuristic.insight == llm.heuristic_payload["insight"]
    assert heuristic.generalized_rule == llm.heuristic_payload["generalized_rule"]

    assert len(result.doc_payloads) == 1
    assert result.doc_payloads[0].heuristic_ids == [heuristic.heuristic_id]
    assert result.doc_payloads[0].target_paths == [f"docs/lore/{heuristic.heuristic_id}.md"]

    assert len(result.receipts) == 1
    assert result.receipts[0].status == "committed"
    assert result.receipts[0].sha == "deadbeef"

    # writes: hardened RULES.json + SKILLS.md markdown, then the lore doc
    assert [path for path, _content in committer.writes] == [
        "RULES.json",
        "SKILLS.md",
        f"docs/lore/{heuristic.heuristic_id}.md",
    ]
    assert committer.commit_calls[0][0].startswith("chore(chronicler): harden")

    state_store = brain.state_store
    assert state_store.state.processed_heuristic_ids == [heuristic.heuristic_id]
    assert state_store.state.last_watermark == audit.created
    assert brain.hardener.is_known(heuristic.heuristic_id)


def test_run_cycle_skips_known_heuristics(make_audit) -> None:
    audit = make_audit()
    reader = FakeLedgerReader(batches=[[audit], [audit]])
    committer = FakeCommitter()
    brain = build_brain(reader, committer=committer)

    first = asyncio.run(brain.run_cycle())
    second = asyncio.run(brain.run_cycle())

    assert len(first.heuristics) == 1
    assert second.skipped_known_heuristics == 1
    # the re-scanned failure is recognized as already-hardened, so no new commit happens
    assert second.written_paths == []
    assert second.receipts == []
    assert len(second.heuristics) == 1


def test_run_cycle_empty_batch_is_clean(make_audit) -> None:
    reader = FakeLedgerReader(batches=[[]])
    brain = build_brain(reader)

    report = asyncio.run(brain.run_cycle())
    assert report.audits == []
    assert report.heuristics == []
    assert report.written_paths == []
    assert report.error is None


def test_run_cycle_uses_canonical_llm_question(make_audit) -> None:
    audit = make_audit()
    reader = FakeLedgerReader(batches=[[audit]])
    llm = FakeLLM()
    brain = build_brain(reader, llm=llm)

    asyncio.run(brain.run_cycle())

    assert llm.json_calls, "expected the brain to fire at least one LLM call"
    extraction_prompt, extraction_system = llm.json_calls[0]
    assert "What did the bots mess up, and what's the permanent fix?" in extraction_system
    assert audit.task_id in extraction_prompt
