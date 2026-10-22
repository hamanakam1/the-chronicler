"""Local Git & file-system ninja module for The Chronicler."""

import subprocess
from pathlib import Path

from pydantic import BaseModel, Field

from chronicler.errors import CommitError, UnsafePathError


class CommitReceipt(BaseModel):
    """Result of a local git commit (and optional push) performed by the committer."""

    message: str
    files: list[str] = Field(default_factory=list)
    sha: str | None = None
    pushed: bool = False
    status: str = "committed"


class LocalGitCommitter:
    """Safely writes files into the target repo and commits + pushes with zero human intervention."""

    def __init__(self, repo_root: str, remote: str = "origin", push: bool = True) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.remote = remote
        self.push = push

    def is_repo(self) -> bool:
        """Return True when the target path is a usable git work tree."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
            return result.returncode == 0 and result.stdout.strip() == "true"
        except OSError:
            return False

    def _resolve(self, path: str) -> Path:
        candidate = Path(path)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise UnsafePathError(f"refusing unsafe path outside target repo: {path}")
        resolved = (self.repo_root / candidate).resolve()
        root = self.repo_root.resolve()
        if resolved != root and root not in resolved.parents:
            raise UnsafePathError(f"refusing unsafe path outside target repo: {path}")
        return resolved

    def write_text(self, path: str, content: str) -> Path:
        """Atomically write LLM-generated content into the target repo."""
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = target.with_name(f".{target.name}.tmp")
        tmp_path.write_text(content, encoding="utf-8")
        tmp_path.replace(target)
        return target

    def commit(self, message: str, paths: list[str]) -> CommitReceipt:
        """Stage, commit, and (optionally) push the given files. Zero human intervention.

        Writing the same bytes twice is not an error: the receipt comes back
        with status ``unchanged`` and the daemon carries on. Git itself exits
        non-zero with an empty message in that case, so the check is made
        against the index before the commit is attempted.
        """
        if not paths:
            return CommitReceipt(message=message, files=[], status="empty")
        add = subprocess.run(
            ["git", "add", "--", *paths],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if add.returncode != 0:
            raise CommitError(f"git add failed: {add.stderr.strip()}")

        if self._nothing_staged():
            return CommitReceipt(
                message=message,
                files=list(paths),
                sha=self._head_sha(),
                pushed=False,
                status="unchanged",
            )

        commit = subprocess.run(
            ["git", "-c", "user.name=chronicler", "-c", "user.email=chronicler@localhost", "commit", "-m", message],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if commit.returncode != 0:
            raise CommitError(f"git commit failed: {commit.stderr.strip()}")
        sha = self._head_sha()
        pushed = False
        if self.push:
            push_result = subprocess.run(
                ["git", "push", self.remote, "HEAD"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
            pushed = push_result.returncode == 0
            if push_result.returncode != 0:
                raise CommitError(f"git push failed: {push_result.stderr.strip()}")
        return CommitReceipt(message=message, files=list(paths), sha=sha, pushed=pushed, status="committed")

    def _nothing_staged(self) -> bool:
        """True when the index holds no changes relative to HEAD."""
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0

    def _head_sha(self) -> str | None:
        """The current HEAD commit sha, or None on an empty repository."""
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None
