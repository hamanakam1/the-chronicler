"""Regression tests for the local Git committer's failure modes."""

from __future__ import annotations

import subprocess

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
