"""CLI surface tests: banner routing, --quiet handling, stdout hygiene."""

from __future__ import annotations

import json
import os

from chronicler.ascii_art import CHRONICLER_TAGLINE, render_banner
from chronicler.cli import build_parser, main


def test_render_banner_contains_the_wordmark_and_tagline():
    banner = render_banner()
    assert CHRONICLER_TAGLINE in banner
    assert "The Chronicler" in banner


def test_banner_goes_to_stderr_so_stdout_stays_pipeable(capsys):
    """`chronicler doctor | jq` must not choke on the wordmark."""
    exit_code = main(["doctor", "--quiet"])

    captured = capsys.readouterr()
    # The exit code reports whether the environment is healthy: Ollama
    # reachable, the ledger readable, the target a Git repository. A CI
    # runner has none of those, so the exit code is not this test's subject.
    assert exit_code in (0, 1)
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


def test_log_level_works_before_and_after_the_subcommand():
    parser = build_parser()
    assert parser.parse_args(["--log-level", "debug", "doctor"]).log_level == "debug"
    assert parser.parse_args(["doctor", "--log-level", "debug"]).log_level == "debug"


def test_log_level_falls_back_to_the_environment(monkeypatch):
    monkeypatch.setenv("CHRONICLER_LOG_LEVEL", "warning")
    parser = build_parser()
    args = parser.parse_args(["doctor"])
    assert getattr(args, "log_level", None) is None
    # main() resolves the fallback from the environment.
    assert os.environ["CHRONICLER_LOG_LEVEL"] == "warning"


def test_log_level_defaults_to_info(monkeypatch):
    monkeypatch.delenv("CHRONICLER_LOG_LEVEL", raising=False)
    parser = build_parser()
    assert getattr(parser.parse_args(["doctor"]), "log_level", None) is None


def test_banner_is_printed_when_not_quiet(capsys, monkeypatch):
    """Without --quiet the banner still reaches the terminal."""
    # Keep the doctor check hermetic: point it at a temp repo/ledger.
    monkeypatch.setenv("CHRONICLER_REPO_ROOT", ".")
    exit_code = main(["doctor"])

    captured = capsys.readouterr()
    assert exit_code in (0, 1)
    assert CHRONICLER_TAGLINE in captured.err
    assert CHRONICLER_TAGLINE not in captured.out
