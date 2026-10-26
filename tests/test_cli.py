"""CLI surface tests: banner routing, --quiet handling, stdout hygiene."""

from __future__ import annotations

import json
import os
import subprocess

import pytest

from chronicler import cli
from chronicler.ascii_art import CHRONICLER_TAGLINE, render_banner
from chronicler.cli import build_parser, main
from chronicler.config import ChroniclerConfig


@pytest.fixture(autouse=True)
def isolated_health_checks(monkeypatch, tmp_path):
    for key in os.environ:
        if key.startswith("CHRONICLER_"):
            monkeypatch.delenv(key)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    class OfflineClient:
        def __init__(self, config):
            pass

        async def ping(self):
            return False

        async def close(self):
            pass

    class EmptyReader:
        def __init__(self, path):
            self.path = path

        def fetch_new_failures(self, since, limit):
            return []

    class FakeCommitter:
        def __init__(self, repo_root, remote="origin", push=False):
            self.repo_root = repo_root
            self.remote = remote
            self.push = push

        def is_repo(self):
            return True

    monkeypatch.setattr(cli, "OllamaClient", OfflineClient)
    monkeypatch.setattr(cli, "SqliteEdgeRecordReader", EmptyReader)
    monkeypatch.setattr(cli, "LocalGitCommitter", FakeCommitter)


def test_render_banner_contains_the_wordmark_and_tagline():
    banner = render_banner()
    assert CHRONICLER_TAGLINE in banner
    assert "The Chronicler" in banner


def test_banner_goes_to_stderr_so_stdout_stays_pipeable(capsys):
    """`chronicler doctor | jq` must not choke on the wordmark."""
    exit_code = main(["doctor", "--quiet"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert CHRONICLER_TAGLINE not in captured.out
    # stdout is pure JSON and parses.
    payload = json.loads(captured.out)
    assert set(payload) == {"ollama", "ledger", "git"}


def test_quiet_is_accepted_before_the_subcommand():
    parser = build_parser()
    assert parser.parse_args(["--quiet", "doctor"]).quiet is True
    assert parser.parse_args(["doctor", "--quiet"]).quiet is True
    assert parser.parse_args(["-q", "doctor"]).quiet is True


def test_quiet_defaults_to_false_when_absent():
    parser = build_parser()
    assert getattr(parser.parse_args(["doctor"]), "quiet", False) is False


def test_banner_is_printed_when_not_quiet(capsys, monkeypatch):
    """Without --quiet the banner still reaches the terminal."""
    # Doctor dependencies are fakes, and the working directory is temporary.
    monkeypatch.setenv("CHRONICLER_REPO_ROOT", ".")
    exit_code = main(["doctor"])

    captured = capsys.readouterr()
    assert exit_code in (0, 1)
    assert CHRONICLER_TAGLINE in captured.err
    assert CHRONICLER_TAGLINE not in captured.out


def test_doctor_reports_an_unconfigured_target_without_constructing_committer(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail("doctor must not guess a repository")

    monkeypatch.setattr(cli, "LocalGitCommitter", forbidden)
    assert main(["doctor", "--quiet"]) == 1
    checks = json.loads(capsys.readouterr().out)
    assert set(checks) == {"ollama", "ledger", "git"}
    assert checks["git"] == {"configured": False, "repo": False, "error": "Set CHRONICLER_REPO_ROOT."}


@pytest.mark.parametrize("command", [["run", "--once"], ["watch"]])
@pytest.mark.parametrize("target", [None, "", " \t", "missing-repo", "."])
def test_execution_rejects_missing_or_invalid_target_before_dependencies(
    command, target, monkeypatch, capsys, tmp_path,
):
    if target is not None:
        monkeypatch.setenv("CHRONICLER_REPO_ROOT", target)

    def forbidden(*args, **kwargs):
        pytest.fail("execution dependencies must not be constructed for an invalid target")

    for name in ("SqliteEdgeRecordReader", "OllamaClient", "JsonStateStore", "LocalGitCommitter"):
        monkeypatch.setattr(cli, name, forbidden)
    with pytest.raises(SystemExit) as error:
        main([*command, "--quiet"])
    assert error.value.code == 2
    captured = capsys.readouterr()
    assert "CHRONICLER_REPO_ROOT" in captured.err or "repo_root" in captured.err
    assert "Traceback" not in captured.err
    assert captured.out == ""
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("push", [False, True])
def test_explicit_git_target_is_validated_and_passed_to_runtime(push, tmp_path):
    repo = tmp_path / "example-repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    config = ChroniclerConfig(repo_root="example-repo", git_push=push)
    brain = cli.build_brain(config)
    assert brain.committer.repo_root == "example-repo"
    assert brain.committer.push is push
    assert brain.reader.path == config.ledger_path
    assert not (tmp_path / "home").exists()
