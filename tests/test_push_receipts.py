"""A delivery failure cannot erase a local commit that already completed."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import Any

import pytest

from chronicler.brain.state_store import JsonStateStore
from chronicler.config import ChroniclerConfig
from chronicler.errors import CommitError
from chronicler.gitops.committer import LocalGitCommitter
from conftest import FakeLedgerReader, build_brain


def _repo(path: Path) -> None:
    path.mkdir()
    subprocess.run(["git", "init", "-q", str(path)], check=True)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()


def _intercept_push(monkeypatch: pytest.MonkeyPatch, *, spawn_error: bool = False) -> list[list[str]]:
    original_run = subprocess.run
    calls: list[list[str]] = []

    def intercepted_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "push"]:
            calls.append(args)
            if spawn_error:
                raise OSError("synthetic push spawn failure")
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="synthetic remote unavailable")
        return original_run(args, **kwargs)

    monkeypatch.setattr(subprocess, "run", intercepted_run)
    return calls


@pytest.mark.parametrize("spawn_error", [False, True], ids=["nonzero-exit", "spawn-error"])
def test_push_failure_returns_completed_local_commit_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, spawn_error: bool
) -> None:
    repo = tmp_path / "repo"
    _repo(repo)
    committer = LocalGitCommitter(str(repo), push=True)
    pushes = _intercept_push(monkeypatch, spawn_error=spawn_error)
    committer.write_text("generated.md", "synthetic generated content")

    receipt = committer.commit("synthetic generated commit", ["generated.md"])

    assert receipt.status == "committed"
    assert receipt.sha == _git(repo, "rev-parse", "HEAD")
    assert receipt.files == ["generated.md"]
    assert receipt.pushed is False
    assert receipt.push_error is not None
    assert "synthetic" in receipt.push_error
    assert _git(repo, "show", "HEAD:generated.md") == "synthetic generated content"
    assert _git(repo, "status", "--porcelain") == ""
    assert len(pushes) == 1


def test_brain_persists_local_success_and_dedupes_after_failed_push(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_audit
) -> None:
    repo = tmp_path / "repo"
    _repo(repo)
    audit = make_audit()
    state_path = tmp_path / "state.json"
    committer = LocalGitCommitter(str(repo), push=True)
    pushes = _intercept_push(monkeypatch)
    brain = build_brain(
        FakeLedgerReader([[audit]]), committer=committer,
        state_store=JsonStateStore(str(state_path)), config=ChroniclerConfig(git_push=True),
    )

    report = asyncio.run(brain.run_cycle())

    assert report.failed_audits == []
    assert len(report.receipts) == 1
    receipt = report.receipts[0]
    assert receipt.push_error is not None
    assert receipt.pushed is False
    saved = JsonStateStore(str(state_path)).load()
    assert saved.last_commit_sha == receipt.sha == _git(repo, "rev-parse", "HEAD")
    assert saved.processed_heuristic_ids == [report.heuristics[0].heuristic_id]
    assert saved.last_watermark == audit.created

    restarted = build_brain(
        FakeLedgerReader([[audit]]), committer=committer,
        state_store=JsonStateStore(str(state_path)), config=ChroniclerConfig(git_push=True),
    )
    repeated = asyncio.run(restarted.run_cycle())

    assert repeated.skipped_known_heuristics == 1
    assert repeated.receipts == []
    assert len(pushes) == 1
    assert _git(repo, "rev-list", "--count", "HEAD") == "1"


def test_local_commit_failure_still_raises_and_never_attempts_push(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    _repo(repo)
    committer = LocalGitCommitter(str(repo), push=True)
    committer.write_text("generated.md", "synthetic generated content")
    original_run = subprocess.run
    pushes: list[list[str]] = []

    def intercepted_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "push"]:
            pushes.append(args)
            raise AssertionError("push must not be attempted after local commit failure")
        if args[0] == "git" and "commit" in args:
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="synthetic local commit failure")
        return original_run(args, **kwargs)

    monkeypatch.setattr(subprocess, "run", intercepted_run)

    with pytest.raises(CommitError, match="synthetic local commit failure"):
        committer.commit("synthetic commit", ["generated.md"])

    assert pushes == []
    assert subprocess.run(["git", "rev-parse", "--verify", "HEAD"], cwd=repo, capture_output=True).returncode != 0
