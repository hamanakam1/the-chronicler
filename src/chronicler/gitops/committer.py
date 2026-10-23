"""Local Git & file-system ninja module for The Chronicler."""

from __future__ import annotations

import logging
import subprocess
import tempfile
import unicodedata
from pathlib import Path

from pydantic import BaseModel, Field

from chronicler.errors import CommitError, UnsafePathError

logger = logging.getLogger("chronicler")


class CommitReceipt(BaseModel):
    """Result of a local git commit (and optional push) performed by the committer."""

    message: str
    files: list[str] = Field(default_factory=list)
    sha: str | None = None
    pushed: bool = False
    push_error: str | None = None
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

    def _resolve(self, path: str, *, allow_leaf_symlink: bool = False) -> Path:
        candidate = Path(path)
        if candidate.is_absolute() or ".." in candidate.parts or "\0" in path:
            raise UnsafePathError(f"refusing unsafe path outside target repo: {path}")
        if any(part.casefold() == ".git" for part in candidate.parts):
            raise UnsafePathError(f"refusing Git metadata path: {path}")
        if not candidate.parts:
            raise UnsafePathError(f"output requires an explicit file path: {path}")
        target = self.repo_root
        for index, part in enumerate(candidate.parts):
            if target.is_dir():
                key = unicodedata.normalize("NFC", part).casefold()
                for entry in target.iterdir():
                    if entry.name != part and unicodedata.normalize("NFC", entry.name).casefold() == key:
                        # Git's literal path selection can differ from the
                        # filesystem's case-insensitive lookup of the same file.
                        raise UnsafePathError(f"output path aliases existing entry {entry.name}: {path}")
            target = target / part
            is_leaf = index == len(candidate.parts) - 1
            if target.is_symlink():
                if is_leaf and allow_leaf_symlink:
                    continue
                raise UnsafePathError(f"refusing symlink in output path: {path}")
            if not is_leaf and target.exists() and not target.is_dir():
                raise UnsafePathError(f"output parent is not a directory: {path}")
            if not is_leaf and ((target / ".git").exists() or (target / ".git").is_symlink()):
                raise UnsafePathError(f"refusing nested Git repository in output path: {path}")
        return target

    def _git_metadata_paths(self) -> list[Path]:
        """Separate Git directories need protection even when they are not named .git."""
        metadata_paths: list[Path] = []
        for option in ("--absolute-git-dir", "--git-common-dir"):
            result = subprocess.run(
                ["git", "rev-parse", option], cwd=self.repo_root,
                capture_output=True, text=True, check=False,
            )
            if result.returncode != 0:
                raise CommitError(f"git path inspection failed: {result.stderr.strip()}")
            metadata_paths.append((self.repo_root / result.stdout.removesuffix("\n")).resolve())
        return metadata_paths

    def _reject_git_metadata(self, target: Path, metadata_paths: list[Path]) -> None:
        for metadata in metadata_paths:
            if target == metadata or metadata in target.parents:
                raise UnsafePathError(f"refusing Git metadata path: {target}")
            # samefile also recognizes case/Unicode aliases on Mac filesystems.
            for ancestor in (target, *target.parents):
                if ancestor == self.repo_root.parent:
                    break
                if ancestor.exists() and metadata.exists() and ancestor.samefile(metadata):
                    raise UnsafePathError(f"refusing Git metadata path: {target}")

    def _reject_gitlink_ancestors(self, paths: list[str]) -> None:
        """An uninitialized or deleted submodule still belongs to a different repository."""
        ancestors = sorted({str(parent) for path in paths for parent in Path(path).parents if parent != Path(".")})
        if not ancestors:
            return
        commands = [["ls-files", "--stage", "-z", "--", *ancestors]]
        if self._head_sha() is not None:
            commands.append(["ls-tree", "-r", "-z", "HEAD", "--", *ancestors])
        normalized_paths = [str(Path(path)).casefold() for path in paths]
        for args in commands:
            result = subprocess.run(
                ["git", "--literal-pathspecs", *args], cwd=self.repo_root,
                capture_output=True, text=True, check=False,
            )
            if result.returncode != 0:
                raise CommitError(f"git path inspection failed: {result.stderr.strip()}")
            for entry in result.stdout.split("\0"):
                metadata, _, name = entry.partition("\t")
                if metadata.split(" ", 1)[0] == "160000" and any(
                    path.startswith(name.casefold() + "/") for path in normalized_paths
                ):
                    raise UnsafePathError(f"refusing output inside tracked submodule: {name}")

    def validate_write_paths(self, paths: list[str], *, require_repository: bool = True) -> list[Path]:
        """Reject the complete output plan before any existing content is replaced."""
        targets = [self._resolve(path) for path in paths]
        keys: list[tuple[str, ...]] = []
        for path, target in zip(paths, targets, strict=True):
            # Conservative portability: case/Unicode-only distinctions are not
            # independent output files on common Mac filesystems.
            key = tuple(unicodedata.normalize("NFC", part).casefold() for part in target.relative_to(self.repo_root).parts)
            for previous in keys:
                if key == previous or key[: len(previous)] == previous or previous[: len(key)] == key:
                    raise UnsafePathError(f"duplicate or overlapping output paths: {path}")
            keys.append(key)
            if target.exists() and not target.is_file():
                raise UnsafePathError(f"output requires an explicit regular file path: {path}")
        in_repository = self.is_repo() if targets else False
        if targets and not in_repository and (require_repository or (self.repo_root / ".git").exists()):
            raise CommitError("generated output plan requires a usable Git worktree")
        metadata_paths = self._git_metadata_paths() if in_repository else []
        if in_repository:
            self._reject_gitlink_ancestors(paths)
            self._reject_ignored_paths(paths)
        for path, target in zip(paths, targets, strict=True):
            self._reject_git_metadata(target, metadata_paths)
            if in_repository:
                self._is_tracked_file(path)
        return targets

    def _reject_ignored_paths(self, paths: list[str]) -> None:
        """Ignored output would be replaced but could not enter the generated commit."""
        # check-ignore rejects all pathspec magic, including --literal-pathspecs.
        # A relative prefix keeps colon-prefixed filenames out of that parser.
        literal_paths = [f"./{Path(path).as_posix()}" for path in paths]
        result = subprocess.run(
            ["git", "check-ignore", "--stdin", "-z"], cwd=self.repo_root,
            input="\0".join(literal_paths) + "\0", capture_output=True, text=True, check=False,
        )
        if result.returncode == 0:
            ignored_path = result.stdout.split("\0", 1)[0]
            raise UnsafePathError(f"generated output is ignored by Git: {ignored_path}")
        if result.returncode != 1:
            raise CommitError(f"git ignore inspection failed: {result.stderr.strip()}")

    def write_text(self, path: str, content: str) -> Path:
        """Atomically write LLM-generated content into the target repo."""
        target = self.validate_write_paths([path], require_repository=False)[0]
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
        targets = [self._resolve(path, allow_leaf_symlink=True) for path in paths]
        metadata_paths = self._git_metadata_paths()
        self._reject_gitlink_ancestors(paths)
        for path, target in zip(paths, targets, strict=True):
            self._reject_git_metadata(target, metadata_paths)
            if target.is_dir() and not target.is_symlink():
                raise UnsafePathError(f"commit requires an explicit file path: {path}")
            tracked_file = self._is_tracked_file(path)
            if not target.exists() and not target.is_symlink() and not tracked_file:
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
        push_error = None
        if self.push:
            try:
                push_result = subprocess.run(
                    ["git", "push", self.remote, "HEAD"],
                    cwd=self.repo_root,
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except OSError as exc:
                push_error = f"git push failed: {exc}"
            else:
                pushed = push_result.returncode == 0
                if not pushed:
                    detail = push_result.stderr.strip() or push_result.stdout.strip() or f"exit code {push_result.returncode}"
                    push_error = f"git push failed: {detail}"
            if push_error is not None:
                # Local success must remain checkpointable even when delivery fails.
                logger.warning("local commit %s completed; %s", sha, push_error)
        return CommitReceipt(
            message=message, files=list(paths), sha=sha, pushed=pushed,
            push_error=push_error, status="committed",
        )

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
