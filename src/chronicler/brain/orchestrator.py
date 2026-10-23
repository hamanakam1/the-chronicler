"""The Chronicler's meta-learning brain: core orchestration loop."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from chronicler.brain.extraction import HeuristicExtractor
from chronicler.brain.state import ChroniclerState
from chronicler.brain.state_store import StateStore
from chronicler.config import ChroniclerConfig
from chronicler.docs.synthesizer import DocSynthesizer
from chronicler.gitops.committer import CommitReceipt, LocalGitCommitter
from chronicler.ledger.reader import EdgeRecordReader, failure_id_for
from chronicler.ledger.watcher import EdgeRecordWatcher
from chronicler.llm.client import OllamaClient
from chronicler.llm.prompts import EXTRACTION_SYSTEM_PROMPT, build_extraction_prompt
from chronicler.rules.hardener import RuleHardener
from chronicler.schemas import DocUpdatePayload, ExecutionAuditLog, ExtractedHeuristic

logger = logging.getLogger("chronicler")


class CycleReport(BaseModel):
    """Outcome of a single Chronicler orchestration cycle."""

    audits: list[ExecutionAuditLog] = Field(default_factory=list)
    heuristics: list[ExtractedHeuristic] = Field(default_factory=list)
    doc_payloads: list[DocUpdatePayload] = Field(default_factory=list)
    written_paths: list[str] = Field(default_factory=list)
    receipts: list[CommitReceipt] = Field(default_factory=list)
    skipped_known_heuristics: int = 0
    failed_audits: list[dict] = Field(default_factory=list)
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

        audits = await self.watcher.poll_once(
            since=state.last_watermark,
            limit=self.config.audit_batch_limit,
            after_failure_id=state.last_watermark_failure_id,
        )
        report.audits = audits
        if not audits:
            state.cycles_completed += 1
            self.state_store.save(state)
            logger.info("cycle %d: no new failures", state.cycles_completed)
            return report

        state.audits_seen += len(audits)
        logger.info("cycle %d: ingesting %d failure(s)", state.cycles_completed + 1, len(audits))

        for audit in audits:
            try:
                await self._process_audit(audit, report, state)
            except Exception as exc:  # noqa: BLE001 - one bad audit must not stop the batch
                logger.warning(
                    "chronicler could not learn from failure %s: %s",
                    audit.fingerprint,
                    exc,
                )
                report.failed_audits.append(
                    {
                        "fingerprint": audit.fingerprint,
                        "audit_id": audit.audit_id,
                        "task_id": audit.task_id,
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                    }
                )

        # Reader ordering includes the numeric ID tie breaker. Taking its last
        # row also preserves ordering when distinct REAL timestamps round alike.
        state.last_watermark = audits[-1].created
        state.last_watermark_failure_id = failure_id_for(audits[-1])
        state.cycles_completed += 1
        self.state_store.save(state)
        logger.info(
            "cycle %d: learned %d heuristic(s), wrote %d file(s), committed %d, skipped %d known, failed %d",
            state.cycles_completed,
            len(report.heuristics),
            len(report.written_paths),
            len(report.receipts),
            report.skipped_known_heuristics,
            len(report.failed_audits),
        )
        return report

    async def _process_audit(self, audit: ExecutionAuditLog, report: CycleReport, state: ChroniclerState) -> None:
        """Ingest one battle scar: extract, harden, document, commit."""
        raw_payload = await self.llm.ask_for_json(build_extraction_prompt(audit), system=EXTRACTION_SYSTEM_PROMPT)
        heuristic = self.extractor.extract(audit, raw_payload)
        report.heuristics.append(heuristic)

        if self.hardener.is_known(heuristic.heuristic_id):
            report.skipped_known_heuristics += 1
            return

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
        self.committer.validate_write_paths(paths)
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
        state.last_commit_at = datetime.now(UTC)

    async def run_forever(self, poll_interval: float | None = None) -> None:
        """Headless daemon loop: poll, think, write, commit, repeat."""
        interval = poll_interval if poll_interval is not None else self.config.poll_interval_seconds
        while True:
            try:
                await self.run_cycle()
            except Exception:  # noqa: BLE001 - daemon must survive transient LLM/git failures
                logger.exception("Chronicler cycle failed; retrying after cooldown")
            await asyncio.sleep(interval)
