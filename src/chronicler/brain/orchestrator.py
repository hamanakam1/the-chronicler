"""The Chronicler's meta-learning brain: core orchestration loop."""

import asyncio
import json
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from chronicler.brain.extraction import HeuristicExtractor
from chronicler.brain.state import ChroniclerState
from chronicler.brain.state_store import StateStore
from chronicler.config import ChroniclerConfig
from chronicler.docs.synthesizer import DocSynthesizer
from chronicler.gitops.committer import CommitReceipt, LocalGitCommitter
from chronicler.ledger.reader import EdgeRecordReader
from chronicler.ledger.watcher import EdgeRecordWatcher
from chronicler.llm.client import OllamaClient
from chronicler.llm.prompts import EXTRACTION_SYSTEM_PROMPT, build_extraction_prompt
from chronicler.rules.hardener import RuleHardener
from chronicler.schemas import DocUpdatePayload, ExecutionAuditLog, ExtractedHeuristic

import logging

logger = logging.getLogger("chronicler")


class CycleReport(BaseModel):
    """Outcome of a single Chronicler orchestration cycle."""

    audits: list[ExecutionAuditLog] = Field(default_factory=list)
    heuristics: list[ExtractedHeuristic] = Field(default_factory=list)
    doc_payloads: list[DocUpdatePayload] = Field(default_factory=list)
    written_paths: list[str] = Field(default_factory=list)
    receipts: list[CommitReceipt] = Field(default_factory=list)
    skipped_known_heuristics: int = 0
    error: str | None = None


class ChroniclerBrain:
    """Watches EdgeRecord failures, asks the local LLM for permanent fixes, commits hardened rules + lore."""

    def __init__(
        self,
        reader: EdgeRecordReader,
        watcher: EdgeRecordWatcher,
        llm: OllamaClient,
        extractor: HeuristicExtractor,
        hardener: RuleHardener,
        synthesizer: DocSynthesizer,
        committer: LocalGitCommitter,
        state_store: StateStore,
        config: ChroniclerConfig,
        state: ChroniclerState | None = None,
    ) -> None:
        self.reader = reader
        self.watcher = watcher
        self.llm = llm
        self.extractor = extractor
        self.hardener = hardener
        self.synthesizer = synthesizer
        self.committer = committer
        self.state_store = state_store
        self.config = config
        self._state_override = state

    def _current_state(self) -> ChroniclerState:
        if self._state_override is not None:
            return self._state_override
        return self.state_store.load()

    async def run_cycle(self) -> CycleReport:
        """One orchestration pass: ingest -> extract -> harden -> document -> commit."""
        state = self._current_state()
        report = CycleReport()

        for processed_id in state.processed_heuristic_ids:
            self.hardener.register(processed_id)

        audits = await self.watcher.poll_once(since=state.last_watermark, limit=self.config.audit_batch_limit)
        report.audits = audits
        if not audits:
            state.cycles_completed += 1
            self.state_store.save(state)
            return report

        state.audits_seen += len(audits)

        for audit in audits:
            raw_payload = await self.llm.ask_for_json(build_extraction_prompt(audit), system=EXTRACTION_SYSTEM_PROMPT)
            heuristic = self.extractor.extract(audit, raw_payload)
            report.heuristics.append(heuristic)

            if self.hardener.is_known(heuristic.heuristic_id):
                report.skipped_known_heuristics += 1
                continue

            draft = self.hardener.draft(heuristic)
            doc_payload = await self.synthesizer.synthesize(heuristic, audit)
            report.doc_payloads.append(doc_payload)

            writes: list[tuple[str, str]] = [
                (self.config.rules_file, json.dumps(draft.content_json, indent=2, sort_keys=True) + "\n"),
                (self.config.skills_file, draft.content_markdown),
            ]
            for path, content in doc_payload.markdown_by_path.items():
                writes.append((path, content))

            paths = [path for path, _content in writes]
            for path, content in writes:
                written = self.committer.write_text(path, content)
                report.written_paths.append(str(written))
            receipt = self.committer.commit(
                message=f"chore(chronicler): harden {draft.rule_id} from failure {heuristic.source_fingerprint}",
                paths=paths,
            )
            report.receipts.append(receipt)

            self.hardener.register(heuristic.heuristic_id)
            state.processed_heuristic_ids.append(heuristic.heuristic_id)
            state.last_commit_sha = receipt.sha
            state.last_commit_message = receipt.message
            state.last_commit_at = datetime.now(timezone.utc)

        state.last_watermark = max((audit.created for audit in audits), default=state.last_watermark)
        state.cycles_completed += 1
        self.state_store.save(state)
        return report

    async def run_forever(self, poll_interval: float | None = None) -> None:
        """Headless daemon loop: poll, think, write, commit, repeat."""
        interval = poll_interval if poll_interval is not None else self.config.poll_interval_seconds
        while True:
            try:
                await self.run_cycle()
            except Exception:  # noqa: BLE001 - daemon must survive transient LLM/git failures
                logger.exception("Chronicler cycle failed; retrying after cooldown")
            await asyncio.sleep(interval)
