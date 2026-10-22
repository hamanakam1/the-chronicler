"""The Chronicler's headless CLI: run, watch, doctor."""

import argparse
import asyncio
import json
from typing import Sequence

from chronicler.config import ChroniclerConfig
from chronicler.ascii_art import print_banner
from chronicler.docs.synthesizer import DocSynthesizer
from chronicler.gitops.committer import LocalGitCommitter
from chronicler.ledger.reader import SqliteEdgeRecordReader
from chronicler.ledger.watcher import EdgeRecordWatcher
from chronicler.llm.client import OllamaClient
from chronicler.brain.extraction import HeuristicExtractor
from chronicler.brain.orchestrator import ChroniclerBrain
from chronicler.brain.state_store import InMemoryStateStore, JsonStateStore
from chronicler.rules.hardener import RuleHardener


def build_brain(config: ChroniclerConfig) -> ChroniclerBrain:
    reader = SqliteEdgeRecordReader(config.ledger_path)
    watcher = EdgeRecordWatcher(reader, poll_interval=config.poll_interval_seconds)
    llm = OllamaClient(config)
    return ChroniclerBrain(
        reader=reader,
        watcher=watcher,
        llm=llm,
        extractor=HeuristicExtractor(),
        hardener=RuleHardener(),
        synthesizer=DocSynthesizer(llm, lore_dir=config.lore_dir),
        committer=LocalGitCommitter(repo_root=config.repo_root, remote=config.git_remote, push=config.git_push),
        state_store=JsonStateStore(config.state_path),
        config=config,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chronicler", description="The Chronicler — local-first memory core of the AI factory.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a single orchestration cycle.")
    run_parser.add_argument("--once", action="store_true", help="Run exactly one cycle and exit.")

    watch_parser = subparsers.add_parser("watch", help="Run the headless daemon loop.")
    watch_parser.add_argument("--interval", type=float, default=None, help="Override watcher poll interval.")

    doctor_parser = subparsers.add_parser("doctor", help="Run local black-ops health checks.")

    return parser


def _cmd_run(brain: ChroniclerBrain, once: bool) -> int:
    if once:
        report = asyncio.run(brain.run_cycle())

        def _default(obj):
            if hasattr(obj, "isoformat"):
                return obj.isoformat()
            return str(obj)

        print(json.dumps(report.model_dump(mode="json"), indent=2, default=str))
        return 0
    return asyncio.run(brain.run_forever())


def _cmd_doctor(config: ChroniclerConfig) -> int:
    import httpx

    checks: dict[str, object] = {}

    async def _run_checks() -> dict[str, object]:
        client = OllamaClient(config)
        checks["ollama"] = await client.ping()
        await client.close()
        reader = SqliteEdgeRecordReader(config.ledger_path)
        try:
            audits = reader.fetch_new_failures(since=None, limit=1)
            checks["ledger"] = {"readable": True, "sample_audits": len(audits)}
        except Exception as exc:  # noqa: BLE001
            checks["ledger"] = {"readable": False, "error": str(exc)}
        committer = LocalGitCommitter(repo_root=config.repo_root, push=False)
        checks["git"] = {"repo": committer.is_repo()}
        return checks

    checks = asyncio.run(_run_checks())
    healthy = bool(checks.get("ollama")) and checks.get("ledger", {}).get("readable") and checks.get("git", {}).get("repo")
    print(json.dumps(checks, indent=2, default=str))
    return 0 if healthy else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = ChroniclerConfig()
    print_banner()
    if args.command == "run":
        return _cmd_run(build_brain(config), once=args.once)
    if args.command == "watch":
        return asyncio.run(build_brain(config).run_forever(poll_interval=args.interval))
    if args.command == "doctor":
        return _cmd_doctor(config)
    parser.print_help()
    return 2
