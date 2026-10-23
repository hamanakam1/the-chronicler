"""Generated output must not alter an alias, repository metadata, or a partial plan."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

from chronicler.config import ChroniclerConfig
from chronicler.errors import UnsafePathError
from chronicler.gitops.committer import LocalGitCommitter
from conftest import FakeLedgerReader, build_brain


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()


def _repo(path: Path) -> LocalGitCommitter:
    path.mkdir()
    _git(path, "init", "-q")
    _git(path, "config", "user.name", "synthetic-test")
    _git(path, "config", "user.email", "synthetic@localhost")
    return LocalGitCommitter(str(path), push=False)


@pytest.mark.parametrize("alias_kind", ["leaf", "parent", "dangling"])
def test_generated_write_rejects_symlink_aliases(tmp_path: Path, alias_kind: str) -> None:
    repo = tmp_path / "repo"
    committer = _repo(repo)
    actual = repo / "actual" / "generated.md"
    actual.parent.mkdir()
    if alias_kind != "dangling":
        actual.write_text("synthetic original", encoding="utf-8")
    if alias_kind == "parent":
        alias = repo / "alias"
        alias.symlink_to("actual", target_is_directory=True)
        requested = "alias/generated.md"
    else:
        alias = repo / "alias.md"
        alias.symlink_to("actual/generated.md")
        requested = "alias.md"

    with pytest.raises(UnsafePathError, match="symlink"):
        committer.write_text(requested, "synthetic replacement")

    assert alias.is_symlink()
    if alias_kind == "dangling":
        assert not actual.exists()
    else:
        assert actual.read_text(encoding="utf-8") == "synthetic original"


@pytest.mark.parametrize("requested", [".git/config", ".GIT/config", "nested/.git/config"])
def test_generated_write_rejects_git_metadata(tmp_path: Path, requested: str) -> None:
    repo = tmp_path / "repo"
    committer = _repo(repo)
    config = repo / ".git" / "config"
    original = config.read_bytes()

    with pytest.raises(UnsafePathError, match="metadata"):
        committer.write_text(requested, "synthetic replacement")

    assert config.read_bytes() == original
    assert not (repo / "nested").exists()


def test_generated_write_preserves_worktree_git_pointer(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    committer = _repo(repo)
    committer.write_text("baseline.md", "synthetic baseline")
    committer.commit("synthetic baseline", ["baseline.md"])
    worktree = tmp_path / "worktree"
    _git(repo, "worktree", "add", "--detach", str(worktree), "HEAD")
    original = (worktree / ".git").read_bytes()

    with pytest.raises(UnsafePathError, match="metadata"):
        LocalGitCommitter(str(worktree), push=False).write_text(".git", "synthetic replacement")

    assert (worktree / ".git").read_bytes() == original


def test_generated_write_rejects_separate_git_directory_inside_worktree(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    metadata = repo / "repository-metadata"
    _git(repo, "init", "-q", "--separate-git-dir", str(metadata))
    original = (metadata / "config").read_bytes()

    with pytest.raises(UnsafePathError, match="metadata"):
        LocalGitCommitter(str(repo), push=False).write_text("repository-metadata/config", "synthetic replacement")

    assert (metadata / "config").read_bytes() == original


@pytest.mark.parametrize(
    "overrides",
    [
        {"lore_dir": "../outside"},
        {"skills_file": ".git/config"},
        {"skills_file": "RULES.json"},
        {"skills_file": "./RULES.json"},
        {"rules_file": "new-output.md", "skills_file": "NEW-output.md"},
        {"rules_file": "generated", "skills_file": "generated/SKILLS.md"},
        {"skills_file": "docs"},
    ],
    ids=["outside", "metadata", "duplicate", "normalized-duplicate", "case-alias", "ancestor", "directory"],
)
def test_brain_rejects_entire_invalid_plan_before_writes(tmp_path: Path, make_audit, overrides: dict[str, str]) -> None:
    repo = tmp_path / "repo"
    committer = _repo(repo)
    originals = {"RULES.json": "synthetic original rules", "SKILLS.md": "synthetic original skills"}
    for path, content in originals.items():
        committer.write_text(path, content)
    committer.write_text("docs/retained.md", "synthetic retained document")
    baseline = committer.commit("synthetic baseline", [*originals, "docs/retained.md"])
    brain = build_brain(
        FakeLedgerReader([[make_audit()]]),
        committer=committer,
        config=ChroniclerConfig(git_push=False, **overrides),
    )

    report = asyncio.run(brain.run_cycle())

    assert len(report.failed_audits) == 1
    assert report.failed_audits[0]["error_type"] == "UnsafePathError"
    assert report.written_paths == []
    assert report.receipts == []
    assert _git(repo, "rev-parse", "HEAD") == baseline.sha
    assert _git(repo, "status", "--porcelain") == ""
    for path, content in originals.items():
        assert (repo / path).read_text(encoding="utf-8") == content


def test_brain_preflight_preserves_existing_tracked_subtree_replacement(tmp_path: Path, make_audit) -> None:
    repo = tmp_path / "repo"
    committer = _repo(repo)
    committer.write_text("docs/retained.md", "synthetic original")
    baseline = committer.commit("synthetic baseline", ["docs/retained.md"])
    (repo / "docs").rename(repo / "preserved-docs")
    (repo / "docs").write_text("synthetic user replacement", encoding="utf-8")
    before = _git(repo, "status", "--porcelain")
    brain = build_brain(
        FakeLedgerReader([[make_audit()]]),
        committer=committer,
        config=ChroniclerConfig(rules_file="docs", git_push=False),
    )

    report = asyncio.run(brain.run_cycle())

    assert report.written_paths == []
    assert len(report.failed_audits) == 1
    assert (repo / "docs").read_text(encoding="utf-8") == "synthetic user replacement"
    assert _git(repo, "rev-parse", "HEAD") == baseline.sha
    assert _git(repo, "status", "--porcelain") == before


def test_explicit_symlink_deletion_preserves_its_target(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    committer = _repo(repo)
    target = tmp_path / "retained.md"
    target.write_text("synthetic retained target", encoding="utf-8")
    alias = repo / "alias.md"
    alias.symlink_to(target)
    _git(repo, "add", "--", "alias.md")
    _git(repo, "commit", "-q", "-m", "synthetic link baseline")
    alias.unlink()

    receipt = committer.commit("synthetic explicit link deletion", ["alias.md"])

    assert receipt.status == "committed"
    assert _git(repo, "show", "--format=", "--name-status", "HEAD") == "D\talias.md"
    assert target.read_text(encoding="utf-8") == "synthetic retained target"


def test_explicit_symlink_commit_records_link_without_touching_target(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    committer = _repo(repo)
    target = tmp_path / "retained.md"
    target.write_text("synthetic retained target", encoding="utf-8")
    (repo / "alias.md").symlink_to(target)

    receipt = committer.commit("synthetic link", ["alias.md"])

    assert receipt.status == "committed"
    assert _git(repo, "ls-tree", "HEAD", "--", "alias.md").startswith("120000 blob ")
    assert target.read_text(encoding="utf-8") == "synthetic retained target"


def test_brain_preflight_preserves_nested_repository(tmp_path: Path, make_audit) -> None:
    repo = tmp_path / "repo"
    committer = _repo(repo)
    committer.write_text("RULES.json", "synthetic original rules")
    committer.commit("synthetic baseline", ["RULES.json"])
    nested = repo / "nested"
    _repo(nested)
    (nested / "SKILLS.md").write_text("synthetic nested skills", encoding="utf-8")
    before = _git(repo, "status", "--porcelain")
    brain = build_brain(
        FakeLedgerReader([[make_audit()]]),
        committer=committer,
        config=ChroniclerConfig(skills_file="nested/SKILLS.md", git_push=False),
    )

    report = asyncio.run(brain.run_cycle())

    assert report.written_paths == []
    assert report.failed_audits[0]["error_type"] == "UnsafePathError"
    assert (repo / "RULES.json").read_text(encoding="utf-8") == "synthetic original rules"
    assert (nested / "SKILLS.md").read_text(encoding="utf-8") == "synthetic nested skills"
    assert _git(repo, "status", "--porcelain") == before


@pytest.mark.parametrize("staged_deletion", [False, True])
def test_write_rejects_uninitialized_submodule_from_index_or_head(tmp_path: Path, staged_deletion: bool) -> None:
    repo = tmp_path / "repo"
    committer = _repo(repo)
    committer.write_text("baseline.md", "synthetic baseline")
    baseline = committer.commit("synthetic baseline", ["baseline.md"])
    _git(repo, "update-index", "--add", "--cacheinfo", f"160000,{baseline.sha},nested")
    _git(repo, "commit", "-q", "-m", "synthetic gitlink baseline")
    if staged_deletion:
        _git(repo, "update-index", "--force-remove", "nested")
    before = _git(repo, "status", "--porcelain")

    with pytest.raises(UnsafePathError, match="submodule"):
        committer.write_text("nested/generated.md", "synthetic replacement")

    assert not (repo / "nested").exists()
    assert _git(repo, "status", "--porcelain") == before


@pytest.mark.parametrize("requested", ["rules.json", "DOCS/generated.md"])
def test_generated_write_rejects_existing_case_alias(tmp_path: Path, requested: str) -> None:
    repo = tmp_path / "repo"
    committer = _repo(repo)
    committer.write_text("RULES.json", "synthetic original rules")
    committer.write_text("docs/generated.md", "synthetic original document")
    baseline = committer.commit("synthetic baseline", ["RULES.json", "docs/generated.md"])

    with pytest.raises(UnsafePathError, match="alias"):
        committer.write_text(requested, "synthetic replacement")

    assert (repo / "RULES.json").read_text(encoding="utf-8") == "synthetic original rules"
    assert (repo / "docs/generated.md").read_text(encoding="utf-8") == "synthetic original document"
    assert _git(repo, "rev-parse", "HEAD") == baseline.sha
    assert _git(repo, "status", "--porcelain") == ""


def test_ignored_later_output_rejects_entire_plan(tmp_path: Path, make_audit) -> None:
    repo = tmp_path / "repo"
    committer = _repo(repo)
    committer.write_text("RULES.json", "synthetic original rules")
    committer.write_text(".gitignore", "SKILLS.md\n")
    baseline = committer.commit("synthetic baseline", ["RULES.json", ".gitignore"])
    (repo / "SKILLS.md").write_text("synthetic ignored skills", encoding="utf-8")
    brain = build_brain(
        FakeLedgerReader([[make_audit()]]), committer=committer,
        config=ChroniclerConfig(git_push=False),
    )

    report = asyncio.run(brain.run_cycle())

    assert report.written_paths == []
    assert report.failed_audits[0]["error_type"] == "UnsafePathError"
    assert (repo / "RULES.json").read_text(encoding="utf-8") == "synthetic original rules"
    assert (repo / "SKILLS.md").read_text(encoding="utf-8") == "synthetic ignored skills"
    assert _git(repo, "rev-parse", "HEAD") == baseline.sha
    assert _git(repo, "status", "--porcelain") == ""


def test_ignore_rule_does_not_block_an_already_tracked_output(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    committer = _repo(repo)
    committer.write_text("RULES.json", "synthetic original rules")
    committer.commit("synthetic baseline", ["RULES.json"])
    committer.write_text(".gitignore", "RULES.json\n")
    committer.commit("synthetic ignore rule", [".gitignore"])

    committer.write_text("RULES.json", "synthetic replacement")
    receipt = committer.commit("synthetic update", ["RULES.json"])

    assert receipt.status == "committed"
    assert _git(repo, "show", "HEAD:RULES.json") == "synthetic replacement"
