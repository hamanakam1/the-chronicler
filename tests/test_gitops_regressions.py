"""Regression tests for the local Git committer's failure modes."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from chronicler.errors import UnsafePathError
from chronicler.gitops.committer import LocalGitCommitter


def _init_repo(path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=str(path), check=True)
    subprocess.run(["git", "config", "user.email", "test@localhost"], cwd=str(path), check=True)


def test_commit_with_identical_content_is_a_noop(tmp_path) -> None:
    """Re-writing the same bytes must not raise: there is simply nothing to commit."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    committer = LocalGitCommitter(str(repo), push=False)

    path = "docs/lore/heur-abc123.md"
    committer.write_text(path, "# Chronicler Lore")
    first = committer.commit("chore(chronicler): harden", [path])
    assert first.status == "committed"

    committer.write_text(path, "# Chronicler Lore")
    second = committer.commit("chore(chronicler): harden", [path])
    assert second.status == "unchanged"
    assert second.sha == first.sha
    assert second.pushed is False


def test_commit_with_no_paths_is_empty(tmp_path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    committer = LocalGitCommitter(str(repo), push=False)

    receipt = committer.commit("chore(chronicler): nothing", [])
    assert receipt.status == "empty"
    assert receipt.sha is None


def test_write_text_is_atomic_and_leaves_no_temp_files(tmp_path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    committer = LocalGitCommitter(str(repo), push=False)

    committer.write_text("RULES.json", '{"a": 1}')
    leftovers = [p.name for p in repo.iterdir() if p.name.startswith(".") and ".tmp" in p.name]
    assert leftovers == []


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.mark.parametrize("initial_commit", [True, False])
def test_commit_preserves_unrelated_staged_and_unstaged_work(
    tmp_path: Path, initial_commit: bool
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    committer = LocalGitCommitter(str(repo), push=False)
    if not initial_commit:
        committer.write_text("generated.md", "original")
        committer.write_text("unrelated.md", "original")
        committer.commit("baseline", ["generated.md", "unrelated.md"])

    committer.write_text("unrelated.md", "staged user work")
    _git(repo, "add", "--", "unrelated.md")
    committer.write_text("unrelated.md", "unstaged user work")
    committer.write_text("generated.md", "generated content")

    receipt = committer.commit("generated update", ["generated.md"])

    assert receipt.status == "committed"
    assert _git(repo, "show", "--format=", "--name-only", "HEAD") == "generated.md"
    assert _git(repo, "diff", "--cached", "--name-only") == "unrelated.md"
    assert _git(repo, "show", ":unrelated.md") == "staged user work"
    assert (repo / "unrelated.md").read_text() == "unstaged user work"


def test_unchanged_target_does_not_commit_unrelated_staged_work(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    committer = LocalGitCommitter(str(repo), push=False)
    committer.write_text("generated.md", "generated content")
    first = committer.commit("baseline", ["generated.md"])
    committer.write_text("unrelated.md", "staged user work")
    _git(repo, "add", "--", "unrelated.md")

    receipt = committer.commit("unchanged generated content", ["generated.md"])

    assert receipt.status == "unchanged"
    assert receipt.sha == first.sha
    assert _git(repo, "rev-parse", "HEAD") == first.sha
    assert _git(repo, "diff", "--cached", "--name-only") == "unrelated.md"


@pytest.mark.parametrize("filename", ["generated[1].md", ":(glob)*", "-generated.md"])
def test_commit_treats_paths_as_literal_filenames(tmp_path: Path, filename: str) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    committer = LocalGitCommitter(str(repo), push=False)
    committer.write_text("generated1.md", "unrelated content")
    committer.write_text(filename, "generated content")

    receipt = committer.commit("generated update", [filename])

    assert receipt.status == "committed"
    assert _git(repo, "show", "--format=", "--name-only", "HEAD") == filename
    assert _git(repo, "status", "--porcelain") == "?? generated1.md"


@pytest.mark.parametrize("path", [".", "", "docs", "../outside.md", "/outside.md"])
def test_commit_validates_all_paths_before_staging(tmp_path: Path, path: str) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    committer = LocalGitCommitter(str(repo), push=False)
    committer.write_text("generated.md", "generated content")
    committer.write_text("docs/unrelated.md", "user work")

    with pytest.raises(UnsafePathError):
        committer.commit("unsafe path", ["generated.md", path])

    assert _git(repo, "diff", "--cached", "--name-only") == ""


def test_missing_directory_cannot_select_multiple_deleted_files(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    committer = LocalGitCommitter(str(repo), push=False)
    for path in ["docs/generated.md", "docs/unrelated.md"]:
        committer.write_text(path, "original")
    first = committer.commit("baseline", ["docs/generated.md", "docs/unrelated.md"])
    (repo / "docs/generated.md").unlink()
    (repo / "docs/unrelated.md").unlink()
    (repo / "docs").rmdir()

    with pytest.raises(UnsafePathError, match="explicit file"):
        committer.commit("unsafe subtree selection", ["docs"])

    assert _git(repo, "rev-parse", "HEAD") == first.sha
    assert _git(repo, "diff", "--cached", "--name-only") == ""


@pytest.mark.parametrize("staged", [False, True], ids=["unstaged-delete", "staged-delete"])
def test_explicit_deleted_file_can_be_committed(tmp_path: Path, staged: bool) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    committer = LocalGitCommitter(str(repo), push=False)
    committer.write_text("generated[1].md", "original")
    committer.commit("baseline", ["generated[1].md"])
    (repo / "generated[1].md").unlink()
    if staged:
        _git(repo, "--literal-pathspecs", "add", "--", "generated[1].md")
    committer.write_text("unrelated.md", "staged user work")
    _git(repo, "add", "--", "unrelated.md")

    receipt = committer.commit("delete generated file", ["generated[1].md"])

    assert receipt.status == "committed"
    assert _git(repo, "show", "--format=", "--name-only", "HEAD") == "generated[1].md"
    assert _git(repo, "diff", "--cached", "--name-only") == "unrelated.md"
