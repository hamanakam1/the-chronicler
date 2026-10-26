"""Tests for The Chronicler's local Git & file-system ninja module."""

import subprocess

import pytest

from chronicler.errors import UnsafePathError
from chronicler.gitops.committer import LocalGitCommitter


def _init_repo(path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=str(path), check=True)
    subprocess.run(["git", "config", "user.email", "test@localhost"], cwd=str(path), check=True)


def test_write_text_and_commit(tmp_path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    committer = LocalGitCommitter(str(repo))

    target = committer.write_text("docs/lore/heur-abc123.md", "# Chronicler Lore")
    assert str(target).endswith("docs/lore/heur-abc123.md")
    assert target.exists()

    receipt = committer.commit("chore(chronicler): harden", ["docs/lore/heur-abc123.md"])
    assert receipt.status == "committed"
    assert receipt.sha
    assert receipt.files == ["docs/lore/heur-abc123.md"]
    assert receipt.pushed is False


def test_write_text_rejects_path_traversal(tmp_path) -> None:
    committer = LocalGitCommitter(str(tmp_path), push=False)
    with pytest.raises(UnsafePathError):
        committer.write_text("docs/../../etc/passwd", "boom")


def test_write_text_rejects_absolute_paths(tmp_path) -> None:
    committer = LocalGitCommitter(str(tmp_path), push=False)
    with pytest.raises(UnsafePathError):
        committer.write_text("/etc/passwd", "boom")


def test_is_repo_false_outside_git(tmp_path) -> None:
    committer = LocalGitCommitter(str(tmp_path / "not-a-repo"), push=False)
    assert committer.is_repo() is False


def test_push_still_works_when_explicitly_enabled(tmp_path, monkeypatch) -> None:
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 1 if "diff" in argv else 0, stdout="example-sha", stderr="")

    monkeypatch.setattr(subprocess, "run", run)
    receipt = LocalGitCommitter(str(tmp_path), push=True).commit("example commit", ["RULES.json"])
    assert receipt.pushed is True
    assert ["git", "push", "origin", "HEAD"] in calls


def test_direct_committer_expands_home_path(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    committer = LocalGitCommitter("~/example-repo")
    assert committer.repo_root == (tmp_path / "example-repo").resolve()


@pytest.mark.parametrize("root", ["", " \t"])
def test_direct_committer_does_not_guess_current_directory(root) -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        LocalGitCommitter(root)
