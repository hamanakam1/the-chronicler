"""Tests for the runtime configuration defaults.

The defaults used to be absolute paths under one developer's home directory.
That breaks for every other user and inside the container image, where the
path does not exist and is not writable. The defaults must be relative to
the *current* user's home directory, and ``~`` must expand in any value
supplied through the environment.
"""

from __future__ import annotations

import os
from pathlib import Path

from chronicler.config import ChroniclerConfig


def test_defaults_are_not_hardcoded_to_a_single_users_home(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("CHRONICLER_LEDGER_PATH", raising=False)
    monkeypatch.delenv("CHRONICLER_REPO_ROOT", raising=False)
    monkeypatch.delenv("CHRONICLER_STATE_PATH", raising=False)

    config = ChroniclerConfig()

    # No default may point into one particular developer's home directory.
    assert not config.ledger_path.startswith("/Users/")
    assert not config.state_path.startswith("/Users/")
    # repo_root tracks the cwd rather than a baked-in absolute path.
    assert config.repo_root == str(Path.cwd().resolve())


def test_state_path_defaults_under_the_users_home(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("CHRONICLER_STATE_PATH", raising=False)

    config = ChroniclerConfig()

    assert config.state_path == str(tmp_path / ".chronicler" / "state.json")


def test_ledger_path_defaults_under_the_users_home(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("CHRONICLER_LEDGER_PATH", raising=False)

    config = ChroniclerConfig()

    assert config.ledger_path == str(tmp_path / ".taskrivet" / "ledger.sqlite")


def test_repo_root_defaults_to_the_current_checkout(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("CHRONICLER_REPO_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)

    config = ChroniclerConfig()

    assert config.repo_root == str(tmp_path.resolve())


def test_tilde_is_expanded_in_supplied_paths(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CHRONICLER_LEDGER_PATH", "~/somewhere/ledger.sqlite")
    monkeypatch.setenv("CHRONICLER_STATE_PATH", "~/state.json")

    config = ChroniclerConfig()

    assert config.ledger_path == str(tmp_path / "somewhere" / "ledger.sqlite")
    assert config.state_path == str(tmp_path / "state.json")


def test_absolute_paths_are_left_alone(monkeypatch, tmp_path) -> None:
    target = tmp_path / "ledger.sqlite"
    monkeypatch.setenv("CHRONICLER_LEDGER_PATH", str(target))

    config = ChroniclerConfig()

    assert config.ledger_path == str(target)


def test_relative_paths_are_kept_relative(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("CHRONICLER_RULES_FILE", raising=False)
    monkeypatch.setenv("CHRONICLER_RULES_FILE", "RULES.json")

    config = ChroniclerConfig()

    assert config.rules_file == "RULES.json"


def test_container_paths_are_writable(monkeypatch, tmp_path) -> None:
    """The container image runs as a non-root user with a writable data volume."""
    data_dir = tmp_path / "chronicler-data"
    data_dir.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CHRONICLER_STATE_PATH", str(data_dir / "state.json"))

    config = ChroniclerConfig()
    target = Path(config.state_path)

    assert target.parent.exists()
    assert os.access(target.parent, os.W_OK)
