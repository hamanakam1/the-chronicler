"""The Chronicler's headless CLI: run, watch, doctor."""

import argparse
import asyncio
import json
import logging
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from chronicler.ascii_art import print_banner
from chronicler.brain.extraction import HeuristicExtractor
from chronicler.brain.orchestrator import ChroniclerBrain
from chronicler.brain.state_store import JsonStateStore
from chronicler.config import ChroniclerConfig
from chronicler.docs.synthesizer import DocSynthesizer
from chronicler.gitops.committer import LocalGitCommitter
from chronicler.ledger.reader import SqliteEdgeRecordReader
from chronicler.ledger.watcher import EdgeRecordWatcher
from chronicler.llm.client import OllamaClient
from chronicler.rules.hardener import RuleHardener


def _execution_repo_root(config: ChroniclerConfig) -> str:
    """Validate the explicit write target before constructing runtime dependencies."""
    root = config.repo_root
    if root is None or not root.strip():
        raise ValueError("Set CHRONICLER_REPO_ROOT to the Git work tree that should receive generated files.")
    if not Path(root).is_dir():
        raise ValueError("CHRONICLER_REPO_ROOT must name an existing Git work tree.")
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=root, capture_output=True, text=True, check=False,
        )
    except OSError as exc:
        raise ValueError("Unable to validate CHRONICLER_REPO_ROOT as a Git work tree.") from exc
    if result.returncode != 0 or result.stdout.strip() != "true":
        raise ValueError("CHRONICLER_REPO_ROOT must name an existing Git work tree.")
    return root


def build_brain(config: ChroniclerConfig) -> ChroniclerBrain:
    repo_root = _execution_repo_root(config)
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
        committer=LocalGitCommitter(repo_root=repo_root, remote=config.git_remote, push=config.git_push),
        state_store=JsonStateStore(config.state_path),
        config=config,
    )


def build_parser() -> argparse.ArgumentParser:
    # Shared parent so --quiet works both before and after the subcommand:
    #   chronicler --quiet doctor
    #   chronicler doctor --quiet
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Suppress the ASCII banner. The banner goes to stderr either way, so stdout stays pipeable.",
    )
    common.add_argument(
        "--log-level",
        choices=["debug", "info", "warning", "error", "critical"],
        default="info",
        help="Verbosity of the daemon log on stderr (default: info).",
    )

    parser = argparse.ArgumentParser(
        prog="chronicler",
        description="The Chronicler — local-first memory core of the AI factory.",
        parents=[common],
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a single orchestration cycle.", parents=[common])
    run_parser.add_argument("--once", action="store_true", help="Run exactly one cycle and exit.")

    watch_parser = subparsers.add_parser("watch", help="Run the headless daemon loop.", parents=[common])
    watch_parser.add_argument("--interval", type=float, default=None, help="Override watcher poll interval.")

    subparsers.add_parser("doctor", help="Run local black-ops health checks.", parents=[common])

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
    asyncio.run(brain.run_forever())
    return 0


def _cmd_doctor(config: ChroniclerConfig) -> int:
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
        if config.repo_root is None:
            checks["git"] = {"configured": False, "repo": False, "error": "Set CHRONICLER_REPO_ROOT."}
        else:
            committer = LocalGitCommitter(repo_root=config.repo_root, push=False)
            checks["git"] = {"configured": True, "repo": committer.is_repo()}
        return checks

    checks = asyncio.run(_run_checks())
    ledger = checks.get("ledger")
    git = checks.get("git")
    healthy = (
        bool(checks.get("ollama"))
        and isinstance(ledger, dict)
        and bool(ledger.get("readable"))
        and isinstance(git, dict)
        and bool(git.get("repo"))
    )
    print(json.dumps(checks, indent=2, default=str))
    return 0 if healthy else 1


def configure_logging(level: str) -> None:
    """Send the daemon log to stderr so stdout stays machine readable."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stderr,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = ChroniclerConfig()
    except ValueError as exc:
        parser.error(str(exc))
    configure_logging(getattr(args, "log_level", "info"))
    if not getattr(args, "quiet", False):
        print_banner()
    if args.command in {"run", "watch"}:
        try:
            brain = build_brain(config)
        except ValueError as exc:
            parser.error(str(exc))
        if args.command == "run":
            return _cmd_run(brain, once=args.once)
        asyncio.run(brain.run_forever(poll_interval=args.interval))
        return 0
    if args.command == "doctor":
        return _cmd_doctor(config)
    parser.print_help()
    return 2
