"""Shared fakes and factories for The Chronicler test suite."""

from datetime import UTC, datetime
from typing import Any

import pytest

from chronicler.brain.extraction import HeuristicExtractor
from chronicler.brain.orchestrator import ChroniclerBrain
from chronicler.brain.state_store import InMemoryStateStore
from chronicler.config import ChroniclerConfig
from chronicler.docs.synthesizer import DocSynthesizer
from chronicler.gitops.committer import CommitReceipt
from chronicler.rules.hardener import RuleHardener
from chronicler.schemas import DocUpdatePayload, ExecutionAuditLog, ExtractedHeuristic

DEFAULT_HEURISTIC_PAYLOAD: dict = {
    "insight": "The bot assumed a gateway host that was not routable.",
    "generalized_rule": "Resolve the gateway host from the compose file before retrying.",
    "confidence": 0.85,
}


class FakeLedgerReader:
    """Scripted EdgeRecord reader used by brain tests."""

    def __init__(self, batches: list[list[ExecutionAuditLog]] | None = None) -> None:
        self.batches: list[list[ExecutionAuditLog]] = [list(batch) for batch in (batches or [])]
        self.calls: list[tuple[Any, int | None]] = []

    def fetch_new_failures(
        self, since: Any, limit: int | None = None, *, after_failure_id: int | None = None
    ) -> list[ExecutionAuditLog]:
        self.calls.append((since, limit))
        if self.batches:
            return list(self.batches.pop(0))
        return []


class FakeWatcher:
    """Async watcher backed by a fake ledger reader."""

    def __init__(self, reader: Any) -> None:
        self.reader = reader

    async def poll_once(self, since: Any = None, limit: int | None = None, *, after_failure_id: int | None = None):
        return self.reader.fetch_new_failures(since, limit if limit is not None else 25, after_failure_id=after_failure_id)


class FakeLLM:
    """Fake local LLM that returns scripted heuristic JSON + doc payloads."""

    def __init__(self, heuristic_payload: dict | None = None, doc_payload: DocUpdatePayload | None = None) -> None:
        self.heuristic_payload = dict(heuristic_payload or DEFAULT_HEURISTIC_PAYLOAD)
        self.doc_payload = doc_payload
        self.last_prompt: str | None = None
        self.last_system: str | None = None
        self.json_calls: list[tuple[str, str | None]] = []

    async def ask_for_json(self, prompt, system=None):
        self.last_prompt = prompt
        self.last_system = system
        self.last_json_prompt = prompt
        self.last_json_system = system
        self.json_calls.append((prompt, system))
        return dict(self.heuristic_payload)

    async def synthesize_document(self, heuristic: ExtractedHeuristic, audit: ExecutionAuditLog) -> DocUpdatePayload:
        if self.doc_payload is None:
            self.doc_payload = DocUpdatePayload(
                payload_id=f"doc-{heuristic.heuristic_id}",
                title=f"Chronicler Lore: {heuristic.failure_category}",
                summary=heuristic.insight,
                content_markdown=f"# Chronicler Lore: {heuristic.failure_category}\n\n{heuristic.generalized_rule}",
                target_paths=[f"docs/lore/{heuristic.heuristic_id}.md"],
                heuristic_ids=[heuristic.heuristic_id],
            )
        return self.doc_payload


class FakeCommitter:
    """Fake git ninja used by brain tests."""

    def __init__(self) -> None:
        self.writes: list[tuple[str, str]] = []
        self.commit_calls: list[tuple[str, list[str]]] = []

    def write_text(self, path: str, content: str):
        self.writes.append((path, content))
        return type("P", (), {"__str__": lambda self: path})()

    def commit(self, message: str, paths: list[str]) -> CommitReceipt:
        self.commit_calls.append((message, list(paths)))
        return CommitReceipt(message=message, files=list(paths), sha="deadbeef", status="committed")

    def is_repo(self) -> bool:
        return True


def build_brain(
    reader: Any,
    llm: Any = None,
    committer: Any = None,
    state_store: Any = None,
    config: Any = None,
) -> ChroniclerBrain:
    config = config or ChroniclerConfig()
    llm_client = llm or FakeLLM()
    return ChroniclerBrain(
        reader=reader,
        watcher=FakeWatcher(reader),
        llm=llm_client,
        extractor=HeuristicExtractor(),
        hardener=RuleHardener(),
        synthesizer=DocSynthesizer(llm_client, lore_dir=config.lore_dir),
        committer=committer or FakeCommitter(),
        state_store=state_store or InMemoryStateStore(),
        config=config,
    )


@pytest.fixture
def config() -> ChroniclerConfig:
    return ChroniclerConfig()


@pytest.fixture
def make_audit():
    def _make(**overrides) -> ExecutionAuditLog:
        defaults = {
            "audit_id": "audit-1",
            "task_id": "task-1",
            "session_id": "sess-1",
            "category": "network_config",
            "fingerprint": "sha256:deadbeef",
            "summary": "Could not resolve host gateway",
            "resolution": "Set the gateway manually",
            "source": "failures",
            "created": datetime(2026, 10, 21, 10, 0, 0, tzinfo=UTC),
        }
        defaults.update(overrides)
        return ExecutionAuditLog(**defaults)

    return _make
