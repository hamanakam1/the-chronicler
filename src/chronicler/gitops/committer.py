"""Local Git & file-system ninja module for The Chronicler."""

from __future__ import annotations

import subprocess
import tempfile
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
        temporary_path: Path | None = None
        try:
            # A fixed temporary name could overwrite another writer's file.
            # Keeping this file beside the target still permits atomic replace.
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=target.parent,
                prefix=f".{target.name}.", suffix=".tmp", delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(content)
            temporary_path.replace(target)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        return target

    def commit(self, message: str, paths: list[str]) -> CommitReceipt:
        """Stage, commit, and (optionally) push the given files. Zero human intervention.

        Writing the same bytes twice is not an error: the receipt comes back
        with status ``unchanged`` and the daemon carries on. Git itself exits
        non-zero with an empty message in that case, so the check is made
        against the index before the commit is attempted.
        Only the requested literal files participate: another caller's staged
        changes must remain staged, including when these files are unchanged.
        """
        if not paths:
            return CommitReceipt(message=message, files=[], status="empty")
        # Validate the complete request before staging anything. A directory
        # would implicitly select files the caller never explicitly requested.
        for path in paths:
            target = self._resolve(path)
            if target == self.repo_root or target.is_dir():
                raise UnsafePathError(f"commit requires an explicit file path: {path}")
            tracked_file = self._is_tracked_file(path)
            if not target.exists() and not tracked_file:
                raise UnsafePathError(f"commit requires an explicit file path: {path}")
        deleted = subprocess.run(
            ["git", "--literal-pathspecs", "diff", "--cached", "--name-only", "--diff-filter=D", "-z", "--", *paths],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if deleted.returncode != 0:
            raise CommitError(f"git diff failed: {deleted.stderr.strip()}")
        staged_deletions = set(deleted.stdout.split("\0"))
        to_add = [
            path for path in paths
            if (self.repo_root / path).exists() or Path(path).as_posix() not in staged_deletions
        ]
        # A staged deletion is already absent from both the index and disk;
        # asking git add for it again would fail before the commit can record it.
        if to_add:
            add = subprocess.run(
                ["git", "--literal-pathspecs", "add", "--", *to_add],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
            if add.returncode != 0:
                raise CommitError(f"git add failed: {add.stderr.strip()}")

        if self._nothing_staged(paths):
            return CommitReceipt(
                message=message,
                files=list(paths),
                sha=self._head_sha(),
                pushed=False,
                status="unchanged",
            )

        commit = subprocess.run(
            [
                "git", "--literal-pathspecs",
                "-c", "user.name=chronicler", "-c", "user.email=chronicler@localhost",
                "commit", "--only", "-m", message, "--", *paths,
            ],
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

    def _is_tracked_file(self, path: str) -> bool:
        """Reject tracked subtrees even if the worktree replaces one with a file."""
        normalized = Path(path).as_posix()
        commands = [["ls-files", "--stage", "-z", "--", path]]
        found = False
        if self._head_sha() is not None:
            # Staged deletions have left the index but still name a file in HEAD.
            commands.append(["ls-tree", "-z", "HEAD", "--", path])
        for args in commands:
            result = subprocess.run(
                ["git", "--literal-pathspecs", *args],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                raise CommitError(f"git path inspection failed: {result.stderr.strip()}")
            for entry in result.stdout.split("\0"):
                metadata, _, name = entry.partition("\t")
                mode = metadata.split(" ", 1)[0]
                if name.startswith(normalized + "/") or (
                    name == normalized and mode in {"040000", "160000"}
                ):
                    raise UnsafePathError(f"commit requires an explicit file, not a tracked directory: {path}")
                if name == normalized and mode in {"100644", "100755", "120000"}:
                    found = True
        return found

    def _nothing_staged(self, paths: list[str]) -> bool:
        """Ignore unrelated staged work when deciding whether a commit is needed."""
        result = subprocess.run(
            ["git", "--literal-pathspecs", "diff", "--cached", "--quiet", "--", *paths],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode not in (0, 1):
            raise CommitError(f"git diff failed: {result.stderr.strip()}")
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
